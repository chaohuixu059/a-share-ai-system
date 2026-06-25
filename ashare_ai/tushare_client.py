from __future__ import annotations

import datetime as dt
import logging
import os
from functools import lru_cache
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


class TusharePermissionError(RuntimeError):
    pass


_TUSHARE_UNAVAILABLE = False
_TUSHARE_UNAVAILABLE_REASON = ""


def mark_tushare_unavailable(reason: str | None = None) -> None:
    global _TUSHARE_UNAVAILABLE, _TUSHARE_UNAVAILABLE_REASON
    _TUSHARE_UNAVAILABLE = True
    if reason:
        _TUSHARE_UNAVAILABLE_REASON = str(reason).strip()
        logger.warning("Tushare 已因权限或配置问题暂时禁用: %s", _TUSHARE_UNAVAILABLE_REASON)


def is_tushare_unavailable() -> bool:
    return _TUSHARE_UNAVAILABLE


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    if number != number:
        return default
    return number


def _normalize_symbol(value: object) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace(".SH", "").replace(".SZ", "")
    text = text.replace("SH", "").replace("SZ", "") if len(text) > 2 and text[:2] in {"SH", "SZ"} else text
    return text


def _get_token(api_key: str | None = None) -> str:
    token = (api_key or os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("缺少 TUSHARE_TOKEN")
    return token


def _is_permission_error(exc: Exception) -> bool:
    text = str(exc)
    keywords = [
        "没有接口",
        "访问权限",
        "无权限",
        "permission",
        "权限",
        "doc_id=108",
    ]
    return any(keyword in text.lower() or keyword in text for keyword in keywords)


@lru_cache(maxsize=4)
def _get_pro_by_token(token: str):
    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"Tushare 未安装: {exc}") from exc

    ts.set_token(token)
    return ts.pro_api()


def get_pro(api_key: str | None = None):
    token = _get_token(api_key)
    return _get_pro_by_token(token)


def _normalize_history_frame(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "日期": "date",
        "时间": "date",
        "trade_date": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "vol": "volume",
        "成交额": "amount",
        "amount": "amount",
        "换手率": "turnover",
    }
    out = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()
    if "date" not in out.columns:
        raise ValueError("历史行情缺少日期列")

    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out[out["date"].notna()].copy()
    for col in ["open", "close", "high", "low", "volume", "amount", "turnover"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "volume" not in out.columns:
        out["volume"] = pd.NA

    volume = pd.to_numeric(out["volume"], errors="coerce")
    amount = pd.to_numeric(out["amount"], errors="coerce") if "amount" in out.columns else pd.Series(index=out.index, dtype="float64")
    close = pd.to_numeric(out["close"], errors="coerce") if "close" in out.columns else pd.Series(index=out.index, dtype="float64")
    if not amount.empty and not close.empty:
        proxy_volume = amount / close.replace(0, pd.NA)
        fill_mask = volume.isna() | (volume <= 0)
        if fill_mask.any():
            volume = volume.where(~fill_mask, proxy_volume)
    out["volume"] = pd.to_numeric(volume, errors="coerce").fillna(0.0)
    return out.sort_values("date").reset_index(drop=True)


def _ensure_daily_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    frame = df.copy()
    if "ts_code" in frame.columns and "symbol" not in frame.columns:
        frame["symbol"] = frame["ts_code"].map(_normalize_symbol)
    return _normalize_history_frame(frame)


def _try_pro_daily(pro, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        frame = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    except Exception as exc:
        if _is_permission_error(exc):
            raise TusharePermissionError(str(exc)) from exc
        raise
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame


def _try_pro_bar(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"Tushare 未安装: {exc}") from exc

    try:
        frame = ts.pro_bar(ts_code=ts_code, adj="qfq", start_date=start_date, end_date=end_date, freq="D")
    except Exception as exc:
        if _is_permission_error(exc):
            raise TusharePermissionError(str(exc)) from exc
        raise
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame


def load_daily_history(symbol: str, start_date: str, end_date: str, api_key: str | None = None) -> pd.DataFrame:
    if is_tushare_unavailable():
        reason = _TUSHARE_UNAVAILABLE_REASON or "Tushare 已被本进程禁用"
        raise TusharePermissionError(reason)

    pro = get_pro(api_key)
    ts_code = _normalize_symbol(symbol)
    if not ts_code:
        raise ValueError("Tushare 历史行情缺少有效股票代码")

    ts_code_full = f"{ts_code}.SH" if ts_code.startswith("6") else f"{ts_code}.SZ"
    loaders = [
        lambda: _try_pro_daily(pro, ts_code_full, start_date, end_date),
        lambda: _try_pro_bar(ts_code_full, start_date, end_date),
    ]
    last_error: Exception | None = None
    for loader in loaders:
        try:
            frame = loader()
            if frame is None or frame.empty:
                continue
            normalized = _ensure_daily_frame(frame)
            if not normalized.empty:
                normalized.attrs["data_source"] = "tushare"
                normalized.attrs["symbol"] = ts_code
                return normalized
        except Exception as exc:
            last_error = exc
            if _is_permission_error(exc):
                mark_tushare_unavailable(str(exc))
                raise TusharePermissionError(str(exc)) from exc
            logger.warning("%s Tushare 历史行情失败: %s", ts_code, exc)

    raise RuntimeError(f"{ts_code} Tushare 历史行情失败: {last_error}")


def load_stock_basic_frame(api_key: str | None = None) -> pd.DataFrame:
    if is_tushare_unavailable():
        reason = _TUSHARE_UNAVAILABLE_REASON or "Tushare 已被本进程禁用"
        raise TusharePermissionError(reason)

    pro = get_pro(api_key)
    try:
        frame = pro.stock_basic(
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,industry,market,list_date",
        )
    except Exception as exc:
        if _is_permission_error(exc):
            mark_tushare_unavailable(str(exc))
            raise TusharePermissionError(str(exc)) from exc
        raise
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["ts_code"] = out["ts_code"].astype(str).str.strip()
    out["symbol"] = out["symbol"].astype(str).map(_normalize_symbol)
    out["name"] = out["name"].astype(str).str.strip()
    out = out[(out["symbol"] != "") & ~out["name"].str.contains("ST|退市", regex=True, na=False)]
    return out.reset_index(drop=True)


def load_symbol_name_map(api_key: str | None = None) -> dict[str, str]:
    frame = load_stock_basic_frame(api_key=api_key)
    if frame.empty:
        return {}
    mapping: dict[str, str] = {}
    for symbol, name in frame[["symbol", "name"]].itertuples(index=False, name=None):
        symbol_text = str(symbol or "").strip()
        name_text = str(name or "").strip()
        if symbol_text and name_text and symbol_text not in mapping:
            mapping[symbol_text] = name_text
    return mapping


def _latest_trade_date(pro, lookback_days: int = 20) -> str:
    today = dt.date.today()
    start_date = (today - dt.timedelta(days=lookback_days)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")
    try:
        cal = pro.trade_cal(exchange="", start_date=start_date, end_date=end_date, is_open="1", fields="cal_date,is_open")
        if cal is not None and not cal.empty and "cal_date" in cal.columns:
            cal["cal_date"] = pd.to_datetime(cal["cal_date"], format="%Y%m%d", errors="coerce")
            cal = cal[cal["cal_date"].notna()].copy()
            if not cal.empty:
                return cal.sort_values("cal_date").iloc[-1]["cal_date"].strftime("%Y%m%d")
    except Exception:
        pass

    for offset in range(1, lookback_days + 1):
        candidate = (today - dt.timedelta(days=offset)).strftime("%Y%m%d")
        try:
            frame = pro.daily_basic(trade_date=candidate, fields="ts_code")
            if frame is not None and not frame.empty:
                return candidate
        except Exception:
            continue
    return today.strftime("%Y%m%d")


def load_spot_universe_frame(limit: int = 300, api_key: str | None = None) -> pd.DataFrame:
    pro = get_pro(api_key)
    stock_basic = load_stock_basic_frame(api_key=api_key)
    if stock_basic.empty:
        return pd.DataFrame()

    trade_date = _latest_trade_date(pro)
    try:
        daily_basic = pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,turnover_rate,volume_ratio,total_mv,circ_mv",
        )
    except Exception as exc:
        if _is_permission_error(exc):
            raise TusharePermissionError(str(exc)) from exc
        logger.warning("Tushare daily_basic 失败，回退到 stock_basic: %s", exc)
        daily_basic = pd.DataFrame()

    if daily_basic is None or daily_basic.empty:
        out = stock_basic.copy()
        out["trade_date"] = trade_date
        out["turnover_rate"] = pd.NA
        out["volume_ratio"] = pd.NA
        out["total_mv"] = pd.NA
        out["circ_mv"] = pd.NA
        out["data_source"] = "tushare-stock_basic"
        out = out.sort_values(["list_date", "symbol"], ascending=[False, True])
        return out.head(limit).reset_index(drop=True)

    daily = daily_basic.copy()
    daily["ts_code"] = daily["ts_code"].astype(str).str.strip()
    daily = daily.merge(stock_basic[["ts_code", "symbol", "name"]], on="ts_code", how="left", suffixes=("", "_basic"))
    daily["symbol"] = daily["symbol"].fillna(daily["ts_code"].map(_normalize_symbol))
    daily["name"] = daily["name"].fillna(daily["symbol"])
    daily["symbol"] = daily["symbol"].astype(str).map(_normalize_symbol)
    daily["name"] = daily["name"].astype(str).str.strip()
    daily = daily[(daily["symbol"] != "") & ~daily["name"].str.contains("ST|退市", regex=True, na=False)]

    for col in ["turnover_rate", "volume_ratio", "total_mv", "circ_mv"]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")

    sort_cols: list[str] = []
    for candidate in ["turnover_rate", "volume_ratio", "circ_mv", "total_mv"]:
        if candidate in daily.columns:
            sort_cols.append(candidate)
            break
    if sort_cols:
        daily = daily.sort_values(sort_cols[0], ascending=False, na_position="last")
    else:
        daily = daily.sort_values(["trade_date", "symbol"], ascending=[False, True])

    daily["data_source"] = "tushare"
    return daily.head(limit).reset_index(drop=True)
