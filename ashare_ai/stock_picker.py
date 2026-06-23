from __future__ import annotations

from pathlib import Path

import pandas as pd


def _contains_sector_keyword(snapshot: dict, keywords: list[str]) -> bool:
    text = " ".join(
        str(snapshot.get(key, "") or "")
        for key in ["name", "name", "symbol", "data_source", "sector", "industry"]
    )
    return any(keyword and keyword in text for keyword in keywords)


def _matched_sector_keywords(snapshot: dict, keywords: list[str]) -> list[str]:
    text = " ".join(
        str(snapshot.get(key, "") or "")
        for key in ["name", "symbol", "data_source", "sector", "industry"]
    )
    return [keyword for keyword in keywords if keyword and keyword in text]


def _matched_sector_groups(snapshot: dict, sector_keyword_aliases: dict[str, list[str]] | None) -> list[str]:
    if not sector_keyword_aliases:
        return []
    text = " ".join(
        str(snapshot.get(key, "") or "")
        for key in ["name", "symbol", "data_source", "sector", "industry"]
    )
    matched: list[str] = []
    for group, aliases in sector_keyword_aliases.items():
        if any(alias and alias in text for alias in aliases):
            matched.append(group)
    return matched


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    if number != number:  # NaN
        return default
    return number


def score_stock(
    snapshot: dict,
    sector_keywords: list[str] | None = None,
    sector_boost: float = 0.0,
    sector_keyword_weights: dict[str, float] | None = None,
    sector_keyword_aliases: dict[str, list[str]] | None = None,
    sector_group_weights: dict[str, float] | None = None,
) -> float:
    ret_5d = _safe_float(snapshot.get("ret_5d", 0.0), 0.0)
    ret_20d = _safe_float(snapshot.get("ret_20d", 0.0), 0.0)
    vol_ratio = _safe_float(snapshot.get("vol_ratio", 1.0), 1.0)
    rsi = _safe_float(snapshot.get("rsi14", 50.0), 50.0)
    ma5 = _safe_float(snapshot.get("ma5", 0.0), 0.0)
    ma10 = _safe_float(snapshot.get("ma10", 0.0), 0.0)
    ma20 = _safe_float(snapshot.get("ma20", 0.0), 0.0)
    close = _safe_float(snapshot.get("close", 0.0), 0.0)

    trend_bonus = 0.0
    if close > 0:
        trend_bonus += 15.0 if ma5 > ma10 > ma20 else 0.0
        trend_bonus += 8.0 if ma5 > ma20 else 0.0

    momentum = ret_5d * 100 * 0.5 + ret_20d * 100 * 0.3
    volume_bonus = max(min((vol_ratio - 1.0) * 12.0, 15.0), -10.0)
    rsi_bonus = 6.0 if 45 <= rsi <= 70 else -6.0 if rsi > 80 or rsi < 35 else 0.0
    pullback_bonus = 4.0 if ret_5d < 0 < ret_20d else 0.0
    sector_bonus = 0.0
    if sector_keywords and _contains_sector_keyword(snapshot, sector_keywords):
        sector_bonus = sector_boost
    if sector_keyword_weights:
        matched_keywords = _matched_sector_keywords(snapshot, list(sector_keyword_weights.keys()))
        if matched_keywords:
            sector_bonus += max(sector_keyword_weights[keyword] for keyword in matched_keywords)
    if sector_keyword_aliases:
        matched_groups = _matched_sector_groups(snapshot, sector_keyword_aliases)
        if matched_groups:
            sector_bonus += max(
                0.0,
                max((sector_group_weights or {}).get(group, 4.0) for group in matched_groups),
            )

    return round(momentum + volume_bonus + trend_bonus + rsi_bonus + pullback_bonus + sector_bonus, 4)


def explain_stock(
    snapshot: dict,
    sector_keywords: list[str] | None = None,
    sector_keyword_weights: dict[str, float] | None = None,
    sector_keyword_aliases: dict[str, list[str]] | None = None,
    sector_group_weights: dict[str, float] | None = None,
) -> list[str]:
    reasons: list[str] = []
    if snapshot.get("ma5", 0) > snapshot.get("ma10", 0) > snapshot.get("ma20", 0):
        reasons.append("均线多头排列")
    if float(snapshot.get("vol_ratio", 1.0) or 1.0) > 1.2:
        reasons.append("成交量放大")
    if 45 <= float(snapshot.get("rsi14", 50.0) or 50.0) <= 70:
        reasons.append("RSI处于健康区间")
    if float(snapshot.get("ret_20d", 0.0) or 0.0) > 0 and float(snapshot.get("ret_5d", 0.0) or 0.0) < 0:
        reasons.append("中期趋势尚可，短线回撤")
    if sector_keywords and _contains_sector_keyword(snapshot, sector_keywords):
        reasons.append("命中科技/偏好板块")
    if sector_keyword_weights:
        matched_keywords = _matched_sector_keywords(snapshot, list(sector_keyword_weights.keys()))
        if matched_keywords:
            reasons.append(f"细分赛道加分：{'/'.join(matched_keywords)}")
    if sector_keyword_aliases:
        matched_groups = _matched_sector_groups(snapshot, sector_keyword_aliases)
        if matched_groups:
            reasons.append(f"赛道聚焦：{'/'.join(matched_groups)}")
    if not reasons:
        reasons.append("综合评分居前")
    return reasons


def pick_stocks(
    feature_table: list[dict],
    top_n: int = 5,
    sector_keywords: list[str] | None = None,
    sector_boost: float = 0.0,
    sector_keyword_weights: dict[str, float] | None = None,
    sector_keyword_aliases: dict[str, list[str]] | None = None,
    sector_group_weights: dict[str, float] | None = None,
) -> list[dict]:
    if not feature_table:
        return []

    rows = []
    for item in feature_table:
        enriched = dict(item)
        enriched["picker_score"] = score_stock(
            item,
            sector_keywords=sector_keywords,
            sector_boost=sector_boost,
            sector_keyword_weights=sector_keyword_weights,
            sector_keyword_aliases=sector_keyword_aliases,
            sector_group_weights=sector_group_weights,
        )
        enriched["picker_reasons"] = explain_stock(
            item,
            sector_keywords=sector_keywords,
            sector_keyword_weights=sector_keyword_weights,
            sector_keyword_aliases=sector_keyword_aliases,
            sector_group_weights=sector_group_weights,
        )
        enriched["sector_hit"] = bool(sector_keywords and _contains_sector_keyword(item, sector_keywords))
        enriched["risk_tags"] = build_risk_tags(item)
        if sector_keyword_weights:
            enriched["sector_matches"] = _matched_sector_keywords(item, list(sector_keyword_weights.keys()))
        if sector_keyword_aliases:
            enriched["sector_groups"] = _matched_sector_groups(item, sector_keyword_aliases)
        rows.append(enriched)

    ranked = sorted(rows, key=lambda item: item["picker_score"], reverse=True)
    return ranked[:top_n]


def pick_stocks_frame(
    feature_table: list[dict],
    top_n: int = 5,
    sector_keywords: list[str] | None = None,
    sector_boost: float = 0.0,
    sector_keyword_weights: dict[str, float] | None = None,
    sector_keyword_aliases: dict[str, list[str]] | None = None,
    sector_group_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    picked = pick_stocks(
        feature_table,
        top_n=top_n,
        sector_keywords=sector_keywords,
        sector_boost=sector_boost,
        sector_keyword_weights=sector_keyword_weights,
        sector_keyword_aliases=sector_keyword_aliases,
        sector_group_weights=sector_group_weights,
    )
    if not picked:
        return pd.DataFrame()
    return pd.DataFrame(picked)


def export_picks_csv(picked_stocks: list[dict], output_path: Path) -> None:
    if not picked_stocks:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False)
        return

    frame = pd.DataFrame(picked_stocks).copy()
    if "picker_reasons" in frame.columns:
        frame["picker_reasons"] = frame["picker_reasons"].apply(lambda values: "、".join(values) if isinstance(values, list) else str(values))
    if "risk_tags" in frame.columns:
        frame["risk_tags"] = frame["risk_tags"].apply(lambda values: "、".join(values) if isinstance(values, list) else str(values))
    if "sector_matches" in frame.columns:
        frame["sector_matches"] = frame["sector_matches"].apply(lambda values: "、".join(values) if isinstance(values, list) else str(values))
    if "sector_groups" in frame.columns:
        frame["sector_groups"] = frame["sector_groups"].apply(lambda values: "、".join(values) if isinstance(values, list) else str(values))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")


def build_risk_tags(snapshot: dict) -> list[str]:
    tags: list[str] = []
    ret_5d = _safe_float(snapshot.get("ret_5d", 0.0), 0.0)
    ret_20d = _safe_float(snapshot.get("ret_20d", 0.0), 0.0)
    rsi = _safe_float(snapshot.get("rsi14", 50.0), 50.0)
    vol_ratio = _safe_float(snapshot.get("vol_ratio", 1.0), 1.0)

    if ret_5d < -0.05:
        tags.append("短线偏弱")
    if ret_20d < -0.08:
        tags.append("中期偏弱")
    if rsi > 80:
        tags.append("超买")
    if rsi < 35:
        tags.append("超跌")
    if vol_ratio < 0.8:
        tags.append("缩量")
    if not tags:
        tags.append("常规")
    return tags
