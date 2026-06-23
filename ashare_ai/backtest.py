from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .features import enrich_indicators, normalize_hist_frame


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    return_pct: float


def backtest_ma_volume_strategy(df: pd.DataFrame) -> dict:
    frame = enrich_indicators(normalize_hist_frame(df)).reset_index(drop=True)
    if len(frame) < 30:
        return {
            "trades": [],
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_return": 0.0,
            "note": "数据太少，无法回测",
        }

    trades: list[Trade] = []
    position = False
    entry_price = 0.0
    entry_idx = -1

    for i in range(20, len(frame) - 1):
        prev = frame.iloc[i - 1]
        prev_prev = frame.iloc[i - 2] if i >= 2 else prev
        next_day = frame.iloc[i]

        cross_up = bool(
            prev["ma5"] > prev["ma20"]
            and prev_prev["ma5"] <= prev_prev["ma20"]
        )
        vol_expand = bool(prev["volume"] > 2 * prev["vol_ma5"]) if pd.notna(prev["vol_ma5"]) else False

        if not position and cross_up and vol_expand:
            position = True
            entry_price = float(next_day["open"])
            entry_idx = i
            entry_date = next_day["date"].strftime("%Y-%m-%d")
            continue

        if position:
            profit_pct = float(prev["close"] / entry_price - 1.0)
            exit_signal = bool(prev["close"] < prev["ma10"] or profit_pct >= 0.15)
            if exit_signal:
                exit_price = float(next_day["open"])
                exit_date = next_day["date"].strftime("%Y-%m-%d")
                trade_return = exit_price / entry_price - 1.0
                trades.append(
                    Trade(
                        entry_date=entry_date,
                        exit_date=exit_date,
                        entry_price=round(entry_price, 4),
                        exit_price=round(exit_price, 4),
                        return_pct=round(trade_return, 4),
                    )
                )
                position = False
                entry_price = 0.0
                entry_idx = -1

    if position and entry_idx >= 0:
        last = frame.iloc[-1]
        trade_return = float(last["close"] / entry_price - 1.0)
        trades.append(
            Trade(
                entry_date=frame.iloc[entry_idx]["date"].strftime("%Y-%m-%d"),
                exit_date=last["date"].strftime("%Y-%m-%d"),
                entry_price=round(entry_price, 4),
                exit_price=round(float(last["close"]), 4),
                return_pct=round(trade_return, 4),
            )
        )

    returns = [trade.return_pct for trade in trades]
    total_return = 1.0
    for value in returns:
        total_return *= 1 + value
    win_trades = [value for value in returns if value > 0]
    loss_trades = [value for value in returns if value <= 0]
    profit_factor = (sum(win_trades) / abs(sum(loss_trades))) if loss_trades and sum(loss_trades) != 0 else float("inf") if win_trades else 0.0

    return {
        "trades": [trade.__dict__ for trade in trades],
        "trade_count": len(trades),
        "win_rate": round(len(win_trades) / len(trades), 4) if trades else 0.0,
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
        "total_return": round(total_return - 1.0, 4),
        "note": "回测执行的是次日开盘价，不包含实时撮合和滑点模型",
    }
