from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable

import akshare as ak
import pandas as pd

from .features import latest_snapshot


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


def fetch_spot_universe(limit: int = 30) -> list[tuple[str, str]]:
    try:
        spot = ak.stock_zh_a_spot_em()
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
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
    )
    if df.empty:
        raise ValueError(f"{symbol} 没有返回历史数据")
    return df


def build_market_samples(symbol_pairs: list[tuple[str, str]], start_date: str, end_date: str) -> tuple[list[dict], list[dict]]:
    snapshots: list[dict] = []
    failures: list[dict] = []
    for symbol, name in symbol_pairs:
        try:
            hist = fetch_daily_history(symbol, start_date, end_date)
            snapshots.append(latest_snapshot(symbol, name, hist))
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
