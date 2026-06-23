from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


def normalize_hist_frame(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "日期": "date",
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
    out = out.sort_values("date").reset_index(drop=True)
    return out


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def calc_macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    diff = ema12 - ema26
    dea = diff.ewm(span=9, adjust=False).mean()
    hist = (diff - dea) * 2
    return diff, dea, hist


def enrich_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = out["close"].rolling(5).mean()
    out["ma10"] = out["close"].rolling(10).mean()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ret_1d"] = out["close"].pct_change()
    out["ret_5d"] = out["close"].pct_change(5)
    out["ret_20d"] = out["close"].pct_change(20)
    out["vol_ma5"] = out["volume"].rolling(5).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma5"]
    out["rsi14"] = calc_rsi(out["close"])
    macd, signal, hist = calc_macd(out["close"])
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist
    return out


def latest_snapshot(symbol: str, name: str, df: pd.DataFrame) -> dict[str, Any]:
    frame = enrich_indicators(normalize_hist_frame(df))
    latest = frame.iloc[-1]
    close = float(latest["close"])
    ret_5d = float(latest.get("ret_5d", 0.0) or 0.0)
    ret_20d = float(latest.get("ret_20d", 0.0) or 0.0)
    trend_gap = float((latest.get("ma5", close) - latest.get("ma20", close)) / close) if close else 0.0
    raw_volume_ratio = latest.get("vol_ratio", 1.0)
    volume_ratio = float(raw_volume_ratio) if pd.notna(raw_volume_ratio) else 1.0
    if not volume_ratio or volume_ratio != volume_ratio:
        volume_ratio = 1.0
    rsi = float(latest.get("rsi14", 50.0) or 50.0)
    score = round((ret_5d * 100) * 0.35 + (ret_20d * 100) * 0.25 + trend_gap * 100 * 0.25 + (volume_ratio - 1) * 10 * 0.15, 4)
    return {
        "symbol": symbol,
        "name": name,
        "date": latest["date"].strftime("%Y-%m-%d"),
        "close": round(close, 4),
        "ret_1d": round(float(latest.get("ret_1d", 0.0) or 0.0), 4),
        "ret_5d": round(ret_5d, 4),
        "ret_20d": round(ret_20d, 4),
        "ma5": round(float(latest.get("ma5", close) or close), 4),
        "ma10": round(float(latest.get("ma10", close) or close), 4),
        "ma20": round(float(latest.get("ma20", close) or close), 4),
        "vol_ratio": round(volume_ratio, 4),
        "rsi14": round(rsi, 2),
        "macd_hist": round(float(latest.get("macd_hist", 0.0) or 0.0), 4),
        "score": score,
    }


def build_feature_table(samples: list[dict[str, Any]]) -> pd.DataFrame:
    if not samples:
        return pd.DataFrame()
    df = pd.DataFrame(samples)
    return df.sort_values("score", ascending=False).reset_index(drop=True)
