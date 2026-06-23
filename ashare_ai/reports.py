from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_day_dir(output_dir: Path, day_str: str) -> Path:
    path = output_dir / day_str
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def build_summary_block(feature_table: list[dict]) -> str:
    if not feature_table:
        return "暂无可用标的。"

    lines = ["## 观察池", ""]
    for item in feature_table[:10]:
        data_source = item.get("data_source", "unknown")
        lines.append(
            f"- {item['symbol']} {item['name']} | 收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | "
            f"20日 {item['ret_20d']:.2%} | 量比 {item['vol_ratio']:.2f} | RSI {item['rsi14']} | 源 {data_source}"
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
            lines.append(
                f"- {item['symbol']} {item['name']} | 收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | "
                f"20日 {item['ret_20d']:.2%} | 量比 {item['vol_ratio']:.2f} | 源 {item.get('data_source', 'unknown')}"
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
