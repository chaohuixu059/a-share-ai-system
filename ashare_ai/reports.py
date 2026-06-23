from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


def ensure_day_dir(output_dir: Path, day_str: str) -> Path:
    path = output_dir / day_str
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    def _default(value: Any) -> Any:
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        return str(value)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def build_summary_block(feature_table: list[dict]) -> str:
    if not feature_table:
        return "暂无可用标的。"

    lines = ["## 观察池", ""]
    for item in feature_table[:10]:
        data_source = item.get("data_source", "unknown")
        vol_ratio = item.get("vol_ratio", 1.0)
        if vol_ratio is None or (isinstance(vol_ratio, float) and math.isnan(vol_ratio)):
            vol_ratio = 1.0
        lines.append(
            f"- {item['symbol']} {item['name']} | 收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | "
            f"20日 {item['ret_20d']:.2%} | 量比 {float(vol_ratio):.2f} | RSI {item['rsi14']} | 源 {data_source}"
        )
    return "\n".join(lines)


def build_local_report(market_summary: dict, feature_table: list[dict], backtest_summary: dict | None = None, failures: list[dict] | None = None) -> str:
    failures = failures or []
    backtest_summary = backtest_summary or {}
    top = feature_table[:5]

    lines = [
        "# A股每日复盘",
        "",
        "## 今日结论",
        "",
        f"- 本次共抓取 {market_summary.get('success_count', 0)} 只标的，失败 {market_summary.get('failure_count', 0)} 只。",
        "- 当前环境下若外部数据源或 OpenAI 超时，系统会自动回退到本地模板，保证日报可输出。",
        "",
        "## 明日关注池",
        "",
    ]

    if top:
        for item in top:
            vol_ratio = item.get("vol_ratio", 1.0)
            if vol_ratio is None or (isinstance(vol_ratio, float) and math.isnan(vol_ratio)):
                vol_ratio = 1.0
            lines.append(
                f"- {item['symbol']} {item['name']} | 收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | "
                f"20日 {item['ret_20d']:.2%} | 量比 {float(vol_ratio):.2f} | 源 {item.get('data_source', 'unknown')}"
            )
    else:
        lines.append("- 暂无可用标的。")

    lines.extend(
        [
            "",
            "## 风险提示",
            "",
            "- A股执行遵循 T+1 和涨跌停约束。",
            "- 任何 AI 生成内容都只用于研究，不应直接用于实盘自动交易。",
        ]
    )

    if backtest_summary:
        lines.extend(
            [
                "",
                "## 回测摘要",
                "",
                f"- {json.dumps(backtest_summary, ensure_ascii=False)}",
            ]
        )

    if failures:
        lines.extend(
            [
                "",
                "## 数据降级说明",
                "",
                f"- 有 {len(failures)} 个标的抓取失败，已自动跳过。",
            ]
        )

    return "\n".join(lines)


def build_pick_report(picked_stocks: list[dict]) -> str:
    if not picked_stocks:
        return "暂无符合条件的选股结果。"

    lines = ["## 选股结果", ""]
    for item in picked_stocks:
        reasons = "、".join(item.get("picker_reasons", []))
        risk_tags = "、".join(item.get("risk_tags", []))
        lines.append(
            f"- {item['symbol']} {item['name']} | 评分 {item.get('picker_score', 0):.2f} | "
            f"收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | 20日 {item['ret_20d']:.2%} | "
            f"风险：{risk_tags} | 理由：{reasons}"
        )
    return "\n".join(lines)


def build_action_plan_block(market_summary: dict, picked_stocks: list[dict]) -> str:
    top = picked_stocks[:6]
    sector_counts: dict[str, int] = {}
    for item in picked_stocks:
        for group in item.get("sector_groups", []) or []:
            sector_counts[group] = sector_counts.get(group, 0) + 1
    ranked_sectors = sorted(sector_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    focus = ", ".join(group for group, _ in ranked_sectors[:3]) if ranked_sectors else "暂无"

    lines = [
        "## 行动区",
        "",
        f"- 当前最强赛道：{focus}",
        "- 当前环境偏弱，优先右侧确认，不做左侧抄底。",
        "- 单票初始仓位不超过 10%，只加仓真正走强的票。",
        "- 如果指数继续弱，优先保留现金，不强行交易。",
        "",
        "## 仓位模板",
        "",
        "- 40% 现金",
        "- 25% 第一梯队趋势票",
        "- 20% 第二梯队观察票",
        "- 15% 机动仓",
        "",
        "## 核心规则",
        "",
        "- 放量突破、板块共振、趋势确认后才考虑介入。",
        "- 跌破纪律位先撤，不在弱势中硬扛。",
        "- 只做当前最强主线，不把资金摊到太多题材里。",
    ]

    if top:
        lines.extend(["", "## 当前前排样本", ""])
        for item in top:
            groups = " / ".join(item.get("sector_groups", []) or []) or "未识别"
            lines.append(
                f"- {item['symbol']} {item['name']} | 评分 {item.get('picker_score', 0):.2f} | "
                f"{groups} | 5日 {item['ret_5d']:.2%} | 20日 {item['ret_20d']:.2%}"
            )

    lines.extend(
        [
            "",
            "## 风险提示",
            "",
            "- 以上仅用于研究，不构成投资建议。",
            "- A股有 T+1 和涨跌停约束，任何高收益目标都不能视为保证。",
        ]
    )
    return "\n".join(lines)


def _top_sector_groups(picked_stocks: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in picked_stocks:
        for group in item.get("sector_groups", []) or []:
            counts[group] = counts.get(group, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return ranked[:5]


def _feature_heatmap(feature_table: list[dict]) -> list[dict[str, Any]]:
    buckets = [
        ("强势", lambda item: float(item.get("ret_5d", 0) or 0) > 0.05),
        ("中性", lambda item: -0.02 <= float(item.get("ret_5d", 0) or 0) <= 0.05),
        ("偏弱", lambda item: float(item.get("ret_5d", 0) or 0) < -0.02),
    ]
    output: list[dict[str, Any]] = []
    for name, predicate in buckets:
        output.append({"label": name, "count": sum(1 for item in feature_table if predicate(item))})
    return output


def build_dashboard_report(
    market_summary: dict,
    feature_table: list[dict],
    picked_stocks: list[dict],
    backtest_summary: dict | None = None,
    failures: list[dict] | None = None,
    output_path: Path | None = None,
) -> str:
    failures = failures or []
    backtest_summary = backtest_summary or {}
    top5 = picked_stocks[:5]
    sector_lines = _top_sector_groups(picked_stocks)
    top_snapshot = feature_table[:3]
    heatmap = _feature_heatmap(feature_table)
    heatmap_summary = ", ".join(f"{item['label']} {item['count']}" for item in heatmap)

    lines = [
        "# A股每日仪表盘",
        "",
        "## 一眼结论",
        "",
        f"- 观察池：{market_summary.get('success_count', 0)} 只，失败 {market_summary.get('failure_count', 0)} 只。",
        f"- 当前最强赛道：{', '.join(group for group, _ in sector_lines[:3]) if sector_lines else '暂无明显聚焦'}。",
        f"- 候选股已导出：{market_summary.get('pick_export_csv', '')}",
        f"- 赛道热度：{heatmap_summary}",
        "",
        "## 今日前排",
        "",
    ]

    if top5:
        for item in top5:
            groups = "、".join(item.get("sector_groups", [])) or "未识别"
            reasons = "；".join(item.get("picker_reasons", [])[:2])
            lines.append(
                f"- {item['symbol']} {item['name']} | 评分 {item.get('picker_score', 0):.2f} | "
                f"{groups} | {reasons}"
            )
    else:
        lines.append("- 暂无前排候选。")

    lines.extend(["", "## 细分赛道", ""])
    if sector_lines:
        for group, count in sector_lines:
            lines.append(f"- {group}：{count} 只")
    else:
        lines.append("- 暂无可识别赛道聚焦。")

    lines.extend(["", "## 观察池快照", ""])
    if top_snapshot:
        for item in top_snapshot:
            lines.append(
                f"- {item['symbol']} {item['name']} | 5日 {item['ret_5d']:.2%} | 20日 {item['ret_20d']:.2%} | "
                f"量比 {float(item.get('vol_ratio', 1.0) or 1.0):.2f}"
            )
    else:
        lines.append("- 暂无快照。")

    lines.extend(
        [
            "",
            "## 风险提示",
            "",
            "- 本系统只做研究与观察，不构成投资建议。",
            "- A股执行遵循 T+1 和涨跌停约束。",
        ]
    )

    if backtest_summary:
        lines.extend(["", "## 回测摘要", "", f"- {json.dumps(backtest_summary, ensure_ascii=False)}"])

    if failures:
        lines.extend(["", "## 降级说明", "", f"- 已自动跳过 {len(failures)} 个失败标的。"])

    report = "\n".join(lines)
    if output_path is not None:
        write_text(output_path, report)
    return report
