from __future__ import annotations

import datetime as dt
import hashlib
import logging
import random
import time
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd

from .features import latest_snapshot
from .tushare_client import TusharePermissionError
from .tushare_client import is_tushare_unavailable, mark_tushare_unavailable
from .tushare_client import load_daily_history as load_tushare_daily_history
from .tushare_client import load_spot_universe_frame, load_symbol_name_map as load_tushare_symbol_name_map


logger = logging.getLogger(__name__)


def yyyymmdd(value: dt.date) -> str:
    return value.strftime("%Y%m%d")


def load_watchlist(path: Path, fallback: list[str]) -> list[str]:
    if path.exists():
        items = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if items:
            return items
    return fallback


def _cache_key(prefix: str, *parts: str) -> str:
    payload = "|".join((prefix, *parts))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest


def _cache_path(cache_dir: Path, prefix: str, *parts: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{prefix}_{_cache_key(prefix, *parts)}.csv"


def _read_cache(cache_path: Path) -> pd.DataFrame | None:
    if not cache_path.exists():
        return None
    df = pd.read_csv(cache_path)
    if df.empty:
        return None
    return df


def _write_cache(cache_path: Path, df: pd.DataFrame) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False)


def _retry_sleep(min_seconds: float, max_seconds: float) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def _safe_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _normalize_history_frame(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "日期": "date",
        "时间": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "vol": "volume",
        "成交额": "amount",
        "换手率": "turnover",
    }
    out = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()
    if "date" not in out.columns:
        raise ValueError("历史行情缺少日期列")
    out["date"] = pd.to_datetime(out["date"])
    for col in ["open", "close", "high", "low", "volume", "amount", "turnover"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    volume = pd.to_numeric(out["volume"], errors="coerce")
    amount = pd.to_numeric(out["amount"], errors="coerce") if "amount" in out.columns else pd.Series(index=out.index, dtype="float64")
    close = pd.to_numeric(out["close"], errors="coerce") if "close" in out.columns else pd.Series(index=out.index, dtype="float64")
    if not amount.empty and not close.empty:
        close = close.replace(0, pd.NA)
        proxy_volume = amount / close
        fill_mask = volume.isna() | (volume <= 0)
        if fill_mask.any():
            volume = volume.where(~fill_mask, proxy_volume)
    out["volume"] = pd.to_numeric(volume, errors="coerce").fillna(0.0)
    return out.sort_values("date").reset_index(drop=True)


def _normalize_baostock_code(symbol: str) -> str:
    clean = symbol.strip().lower().replace(".", "")
    if clean.startswith("sh") or clean.startswith("sz"):
        clean = clean[2:]
    market = "sh" if clean.startswith("6") else "sz"
    return f"{market}.{clean}"


def _normalize_tx_symbol(symbol: str) -> str:
    clean = _normalize_symbol(symbol)
    if not clean:
        return symbol.strip()
    market = "sh" if clean.startswith("6") else "sz"
    return f"{market}{clean}"


def _safe_fund_flow_loader(loader: Callable[[], pd.DataFrame]) -> pd.DataFrame | None:
    try:
        df = loader()
        if df is None or df.empty:
            return None
        return df
    except Exception as exc:
        logger.warning("资金流接口失败: %s", exc)
        return None


def build_flow_snapshot() -> dict:
    snapshot: dict[str, object] = {
        "market_flow": [],
        "industry_flow": [],
        "concept_flow": [],
        "northbound_flow": None,
        "main_fund_flow": [],
    }

    market_df = _safe_fund_flow_loader(lambda: ak.stock_market_fund_flow())
    if market_df is not None:
        snapshot["market_flow"] = market_df.head(5).fillna("").to_dict(orient="records")

    industry_df = _safe_fund_flow_loader(lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流"))
    if industry_df is not None:
        snapshot["industry_flow"] = industry_df.head(8).fillna("").to_dict(orient="records")

    concept_df = _safe_fund_flow_loader(lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流"))
    if concept_df is not None:
        snapshot["concept_flow"] = concept_df.head(8).fillna("").to_dict(orient="records")

    northbound_df = _safe_fund_flow_loader(lambda: ak.stock_hsgt_fund_flow_summary_em())
    if northbound_df is not None:
        snapshot["northbound_flow"] = northbound_df.fillna("").to_dict(orient="records")

    main_flow_df = _safe_fund_flow_loader(lambda: ak.stock_main_fund_flow(symbol="全部股票"))
    if main_flow_df is not None:
        snapshot["main_fund_flow"] = main_flow_df.head(10).fillna("").to_dict(orient="records")

    return snapshot


def _with_fallbacks(label: str, loaders: list[tuple[str, Callable[[], pd.DataFrame]]]) -> tuple[pd.DataFrame, str]:
    last_error: Exception | None = None
    for source_name, loader in loaders:
        try:
            df = loader()
            if df is None or df.empty:
                raise ValueError(f"{source_name} 返回空数据")
            logger.info("%s 使用数据源 %s", label, source_name)
            return df, source_name
        except Exception as exc:
            last_error = exc
            logger.warning("%s 数据源 %s 失败: %s", label, source_name, exc)
    raise RuntimeError(f"{label} 所有数据源都失败: {last_error}")


def _load_daily_history_from_baostock(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import baostock as bs
    except Exception as exc:
        raise RuntimeError(f"BaoStock 未安装: {exc}") from exc

    login_result = bs.login()
    if getattr(login_result, "error_code", "1") != "0":
        raise RuntimeError(f"BaoStock 登录失败: {getattr(login_result, 'error_msg', 'unknown')}")
    try:
        bs_code = _normalize_baostock_code(symbol)
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount",
            start_date=start_date[:4] + "-" + start_date[4:6] + "-" + start_date[6:],
            end_date=end_date[:4] + "-" + end_date[4:6] + "-" + end_date[6:],
            frequency="d",
            adjustflag="3",
        )
        if rs.error_code != "0":
            raise RuntimeError(rs.error_msg)

        data_list = []
        while (rs.error_code == "0") and rs.next():
            data_list.append(rs.get_row_data())
        if not data_list:
            raise ValueError("BaoStock 返回空数据")

        df = pd.DataFrame(data_list, columns=rs.fields)
        return df
    finally:
        bs.logout()


def _normalize_symbol(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace(".SH", "").replace(".SZ", "").replace(".sh", "").replace(".sz", "")
    text = text.replace("sh", "").replace("sz", "") if len(text) > 2 and text[:2].lower() in {"sh", "sz"} else text
    return text


def _load_symbol_name_map() -> dict[str, str]:
    loaders = [
        ("stock_info_a_code_name", lambda: ak.stock_info_a_code_name()),
        ("stock_zh_a_spot_em", lambda: ak.stock_zh_a_spot_em()),
        ("stock_zh_a_spot", lambda: ak.stock_zh_a_spot()),
    ]
    for _, loader in loaders:
        try:
            df = loader()
            if df is None or df.empty:
                continue
            code_col = _safe_column(df, ["代码", "证券代码", "symbol"])
            name_col = _safe_column(df, ["名称", "证券简称", "name"])
            if not code_col or not name_col:
                continue
            out: dict[str, str] = {}
            for code, name in df[[code_col, name_col]].itertuples(index=False, name=None):
                norm = _normalize_symbol(code)
                clean_name = str(name).strip()
                if norm and clean_name and norm not in out:
                    out[norm] = clean_name
            if out:
                return out
        except Exception:
            continue
    return {}


def _load_symbol_name_map_tushare() -> dict[str, str]:
    try:
        return load_tushare_symbol_name_map()
    except Exception as exc:
        logger.warning("Tushare 名称映射加载失败: %s", exc)
        return {}


def _resolve_symbol_name(symbol: str, fallback_name: str | None = None, name_map: dict[str, str] | None = None) -> str:
    name_map = name_map or {}
    clean_symbol = _normalize_symbol(symbol)
    candidates = [fallback_name, name_map.get(clean_symbol)]
    if clean_symbol.isdigit() and len(clean_symbol) == 6:
        candidates.append(name_map.get(clean_symbol.zfill(6)))
    if fallback_name and fallback_name != clean_symbol and not str(fallback_name).isdigit():
        candidates.insert(0, fallback_name)
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text and text != clean_symbol and not text.isdigit():
            return text
    return clean_symbol or str(fallback_name or symbol)


def fetch_spot_universe(limit: int = 30) -> list[tuple[str, str]]:
    loaders = [
        ("stock_zh_a_spot_em", lambda: ak.stock_zh_a_spot_em()),
        ("stock_zh_a_spot", lambda: ak.stock_zh_a_spot()),
    ]

    try:
        spot, _ = _with_fallbacks("A股全市场行情", loaders)
    except Exception:
        spot = pd.DataFrame()

    if spot is not None and not spot.empty:
        symbol_col = _safe_column(spot, ["代码", "symbol"])
        name_col = _safe_column(spot, ["名称", "name"])
        volume_col = _safe_column(spot, ["成交额", "成交量", "amount", "volume"])
        if symbol_col:
            name_map = _load_symbol_name_map()
            columns = [symbol_col] + ([name_col] if name_col else []) + ([volume_col] if volume_col else [])
            out = spot[columns].copy()
            out = out.rename(columns={symbol_col: "symbol"})
            if name_col:
                out = out.rename(columns={name_col: "name"})
            else:
                out["name"] = ""
            out["symbol"] = out["symbol"].astype(str).map(_normalize_symbol)
            out["name"] = [
                _resolve_symbol_name(symbol, name if name_col else None, name_map)
                for symbol, name in zip(out["symbol"], out["name"])
            ]
            out = out[(out["symbol"] != "") & ~out["name"].astype(str).str.contains("ST|退市", regex=True, na=False)]

            if volume_col:
                out[volume_col] = pd.to_numeric(out[volume_col], errors="coerce").fillna(0)
                out = out.sort_values(volume_col, ascending=False)

            out = out.head(limit)
            return list(out[["symbol", "name"]].itertuples(index=False, name=None))

    try:
        tushare_universe = load_spot_universe_frame(limit=limit)
    except Exception as exc:
        if isinstance(exc, TusharePermissionError):
            mark_tushare_unavailable(str(exc))
        logger.warning("Tushare 全市场股票池失败: %s", exc)
        tushare_universe = pd.DataFrame()

    if tushare_universe is not None and not tushare_universe.empty:
        symbol_col = _safe_column(tushare_universe, ["symbol", "ts_code", "代码"])
        name_col = _safe_column(tushare_universe, ["name", "名称", "股票简称"])
        if symbol_col and name_col:
            out = tushare_universe[[symbol_col, name_col]].copy()
            out = out.rename(columns={symbol_col: "symbol", name_col: "name"})
            out["symbol"] = out["symbol"].astype(str).map(_normalize_symbol)
            out["name"] = out["name"].astype(str).str.strip()
            out = out[(out["symbol"] != "") & ~out["name"].astype(str).str.contains("ST|退市", regex=True, na=False)]
            out = out.head(limit)
            return list(out[["symbol", "name"]].itertuples(index=False, name=None))

    return []


def build_symbol_name_lookup(limit: int = 5000) -> dict[str, str]:
    lookup = _load_symbol_name_map()
    if lookup:
        return lookup

    tushare_lookup = _load_symbol_name_map_tushare()
    if tushare_lookup:
        return tushare_lookup

    universe = fetch_spot_universe(limit=limit)
    return {symbol: name for symbol, name in universe if symbol and name}


def enrich_symbol_names(symbol_pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not symbol_pairs:
        return []
    lookup = build_symbol_name_lookup()
    enriched: list[tuple[str, str]] = []
    for symbol, name in symbol_pairs:
        resolved_name = _resolve_symbol_name(symbol, name, lookup)
        enriched.append((_normalize_symbol(symbol), resolved_name))
    return enriched


def fetch_daily_history(
    symbol: str,
    start_date: str,
    end_date: str,
    cache_dir: Path | None = None,
    max_retries: int = 5,
    retry_min_seconds: float = 2,
    retry_max_seconds: float = 5,
    use_baostock: bool = True,
    use_tushare: bool = True,
) -> pd.DataFrame:
    symbol = _normalize_symbol(symbol) or symbol.strip()
    cache_path = None
    if cache_dir is not None:
        cache_path = _cache_path(cache_dir, "daily_history", symbol, start_date, end_date)
        cached = _read_cache(cache_path)
        if cached is not None:
            logger.info("%s 使用本地缓存 %s", symbol, cache_path)
            normalized = _normalize_history_frame(cached)
            normalized.attrs["data_source"] = "cache"
            normalized.attrs["symbol"] = symbol
            return normalized

    loaders: list[tuple[str, Callable[[], pd.DataFrame]]] = [
        (
            "stock_zh_a_hist",
            lambda: ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            ),
        ),
        (
            "stock_zh_a_hist_tx",
            lambda: ak.stock_zh_a_hist_tx(
                symbol=_normalize_tx_symbol(symbol),
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            ),
        ),
    ]

    if use_baostock:
        loaders.append(("baostock", lambda: _load_daily_history_from_baostock(symbol, start_date, end_date)))

    if use_tushare:
        loaders.append(("tushare", lambda: load_tushare_daily_history(symbol, start_date, end_date)))

    if is_tushare_unavailable():
        loaders = [item for item in loaders if item[0] != "tushare"]

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            df, source_name = _with_fallbacks(f"{symbol} 历史行情", loaders)
            normalized = _normalize_history_frame(df)
            normalized.attrs["data_source"] = source_name
            normalized.attrs["symbol"] = symbol
            if cache_path is not None:
                _write_cache(cache_path, normalized)
            return normalized
        except Exception as exc:
            last_error = exc
            if isinstance(exc, TusharePermissionError):
                use_tushare = False
                mark_tushare_unavailable(str(exc))
            logger.warning("%s 第 %s/%s 次获取失败: %s", symbol, attempt, max_retries, exc)
            if attempt < max_retries:
                _retry_sleep(retry_min_seconds, retry_max_seconds)

    raise RuntimeError(f"{symbol} 历史行情所有数据源都失败: {last_error}")


def build_market_samples(
    symbol_pairs: list[tuple[str, str]],
    start_date: str,
    end_date: str,
    cache_dir: Path | None = None,
    max_retries: int = 5,
    retry_min_seconds: float = 2,
    retry_max_seconds: float = 5,
    use_baostock: bool = True,
    use_tushare: bool = True,
) -> tuple[list[dict], list[dict]]:
    snapshots: list[dict] = []
    failures: list[dict] = []
    for symbol, name in enrich_symbol_names(symbol_pairs):
        try:
            hist = fetch_daily_history(
                symbol,
                start_date,
                end_date,
                cache_dir=cache_dir,
                max_retries=max_retries,
                retry_min_seconds=retry_min_seconds,
                retry_max_seconds=retry_max_seconds,
                use_baostock=use_baostock,
                use_tushare=use_tushare,
            )
            snapshot = latest_snapshot(symbol, name, hist)
            snapshot["data_source"] = hist.attrs.get("data_source", "unknown")
            snapshots.append(snapshot)
        except Exception as exc:
            failures.append({"symbol": symbol, "name": name, "error": str(exc)})
    return snapshots, failures


def select_symbols(watchlist: list[str], limit: int) -> list[tuple[str, str]]:
    limit = max(1, int(limit or 1))
    fallback = [
        ("600519", "贵州茅台"),
        ("000001", "平安银行"),
        ("300750", "宁德时代"),
        ("601318", "中国平安"),
        ("600036", "招商银行"),
        ("601166", "兴业银行"),
        ("000858", "五粮液"),
        ("002594", "比亚迪"),
        ("601398", "工商银行"),
        ("002475", "立讯精密"),
    ]
    if watchlist:
        resolved = enrich_symbol_names([(symbol, symbol) for symbol in watchlist])
        if resolved:
            return resolved[:limit]
        return fallback[:limit]

    universe = fetch_spot_universe(limit=max(limit, 300))
    if universe:
        return universe[:limit]

    return fallback[:limit]
