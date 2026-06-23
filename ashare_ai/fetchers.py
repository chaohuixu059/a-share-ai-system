from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Iterable, Callable, Any

import akshare as ak
import pandas as pd

from .features import latest_snapshot


logger = logging.getLogger(__name__)


def yyyymmdd(value: dt.date) -> str:
    return value.strftime("%Y%m%d")


def load_watchlist(path: Path, fallback: list[str]) -> list[str]:
    if path.exists():
        items = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if items:
            return items
    return fallback


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
    return out.sort_values("date").reset_index(drop=True)


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


def fetch_spot_universe(limit: int = 30) -> list[tuple[str, str]]:
    loaders = [
        ("stock_zh_a_spot_em", lambda: ak.stock_zh_a_spot_em()),
        ("stock_zh_a_spot", lambda: ak.stock_zh_a_spot()),
    ]

    try:
        spot, _ = _with_fallbacks("A股全市场行情", loaders)
    except Exception:
        return []

    symbol_col = _safe_column(spot, ["代码", "symbol"])
    name_col = _safe_column(spot, ["名称", "name"])
    volume_col = _safe_column(spot, ["成交额", "成交量", "amount", "volume"])
    if not symbol_col or not name_col:
        return []

    out = spot[[symbol_col, name_col] + ([volume_col] if volume_col else [])].copy()
    out = out.rename(columns={symbol_col: "symbol", name_col: "name"})
    out["name"] = out["name"].astype(str)
    out = out[~out["name"].str.contains("ST|退市", regex=True, na=False)]

    if volume_col:
        out[volume_col] = pd.to_numeric(out[volume_col], errors="coerce").fillna(0)
        out = out.sort_values(volume_col, ascending=False)

    out = out.head(limit)
    return list(out[["symbol", "name"]].itertuples(index=False, name=None))


def fetch_daily_history(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
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
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            ),
        ),
    ]

    df, source_name = _with_fallbacks(f"{symbol} 历史行情", loaders)
    normalized = _normalize_history_frame(df)
    normalized.attrs["data_source"] = source_name
    normalized.attrs["symbol"] = symbol
    return normalized


def build_market_samples(symbol_pairs: list[tuple[str, str]], start_date: str, end_date: str) -> tuple[list[dict], list[dict]]:
    snapshots: list[dict] = []
    failures: list[dict] = []
    for symbol, name in symbol_pairs:
        try:
            hist = fetch_daily_history(symbol, start_date, end_date)
            snapshot = latest_snapshot(symbol, name, hist)
            snapshot["data_source"] = hist.attrs.get("data_source", "unknown")
            snapshots.append(snapshot)
        except Exception as exc:
            failures.append({"symbol": symbol, "name": name, "error": str(exc)})
    return snapshots, failures


def select_symbols(watchlist: list[str], limit: int) -> list[tuple[str, str]]:
    if watchlist:
        return [(symbol, symbol) for symbol in watchlist[:limit]]

    universe = fetch_spot_universe(limit=limit)
    if universe:
        return universe

    return [("600519", "600519"), ("000001", "000001"), ("300750", "300750")]
