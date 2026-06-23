from __future__ import annotations

import pandas as pd


def score_stock(snapshot: dict) -> float:
    ret_5d = float(snapshot.get("ret_5d", 0.0) or 0.0)
    ret_20d = float(snapshot.get("ret_20d", 0.0) or 0.0)
    vol_ratio = float(snapshot.get("vol_ratio", 1.0) or 1.0)
    rsi = float(snapshot.get("rsi14", 50.0) or 50.0)
    ma5 = float(snapshot.get("ma5", 0.0) or 0.0)
    ma10 = float(snapshot.get("ma10", 0.0) or 0.0)
    ma20 = float(snapshot.get("ma20", 0.0) or 0.0)
    close = float(snapshot.get("close", 0.0) or 0.0)

    trend_bonus = 0.0
    if close > 0:
        trend_bonus += 15.0 if ma5 > ma10 > ma20 else 0.0
        trend_bonus += 8.0 if ma5 > ma20 else 0.0

    momentum = ret_5d * 100 * 0.5 + ret_20d * 100 * 0.3
    volume_bonus = max(min((vol_ratio - 1.0) * 12.0, 15.0), -10.0)
    rsi_bonus = 6.0 if 45 <= rsi <= 70 else -6.0 if rsi > 80 or rsi < 35 else 0.0
    pullback_bonus = 4.0 if ret_5d < 0 < ret_20d else 0.0

    return round(momentum + volume_bonus + trend_bonus + rsi_bonus + pullback_bonus, 4)


def explain_stock(snapshot: dict) -> list[str]:
    reasons: list[str] = []
    if snapshot.get("ma5", 0) > snapshot.get("ma10", 0) > snapshot.get("ma20", 0):
        reasons.append("均线多头排列")
    if float(snapshot.get("vol_ratio", 1.0) or 1.0) > 1.2:
        reasons.append("成交量放大")
    if 45 <= float(snapshot.get("rsi14", 50.0) or 50.0) <= 70:
        reasons.append("RSI处于健康区间")
    if float(snapshot.get("ret_20d", 0.0) or 0.0) > 0 and float(snapshot.get("ret_5d", 0.0) or 0.0) < 0:
        reasons.append("中期趋势尚可，短线回撤")
    if not reasons:
        reasons.append("综合评分居前")
    return reasons


def pick_stocks(feature_table: list[dict], top_n: int = 5) -> list[dict]:
    if not feature_table:
        return []

    rows = []
    for item in feature_table:
        enriched = dict(item)
        enriched["picker_score"] = score_stock(item)
        enriched["picker_reasons"] = explain_stock(item)
        rows.append(enriched)

    ranked = sorted(rows, key=lambda item: item["picker_score"], reverse=True)
    return ranked[:top_n]


def pick_stocks_frame(feature_table: list[dict], top_n: int = 5) -> pd.DataFrame:
    picked = pick_stocks(feature_table, top_n=top_n)
    if not picked:
        return pd.DataFrame()
    return pd.DataFrame(picked)
