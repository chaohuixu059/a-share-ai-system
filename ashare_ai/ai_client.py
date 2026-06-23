from __future__ import annotations

from typing import Any

from openai import OpenAI


def _build_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def _extract_text(response: Any) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    if hasattr(response, "choices"):
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message and getattr(message, "content", None):
            return message.content

    return str(response)


def generate_report(api_key: str, model: str, market_summary: dict, feature_table: list[dict], backtest_summary: dict | None = None) -> str | None:
    client = _build_client(api_key)

    system_prompt = (
        "你是顶级A股量化研究员和晚间复盘分析师。"
        "请根据给定的数据生成一份中文复盘报告，要求简洁、专业、可执行。"
        "严格遵守A股规则：T+1、涨跌停限制、不能使用未来函数、不要假设美股式T+0。"
    )
    user_prompt = {
        "market_summary": market_summary,
        "feature_table": feature_table[:10],
        "backtest_summary": backtest_summary or {},
        "output_requirements": [
            "输出 Markdown。",
            "包含三个部分：今日结论、明日关注池、风险提示。",
            "如果有明显的强势标的，请给出前3个观察池。",
        ],
    }

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_prompt)},
            ],
        )
        return _extract_text(response)
    except Exception:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": str(user_prompt)},
                ],
            )
            return _extract_text(response)
        except Exception:
            return None


def generate_strategy_code(api_key: str, model: str, feature_table: list[dict], backtest_summary: dict | None = None) -> str | None:
    client = _build_client(api_key)

    system_prompt = (
        "你是资深A股量化工程师。"
        "请用 Python 输出一个可运行的 Backtrader 策略代码，严格遵守A股规则：T+1、涨跌停限制、不能使用未来函数。"
        "只输出完整代码，不要解释，不要 Markdown 说明。"
    )
    user_prompt = {
        "feature_table": feature_table[:10],
        "backtest_summary": backtest_summary or {},
        "strategy_hint": "优先使用均线、成交量放大、止损止盈、过滤ST股和高风险信号。",
        "required_sections": ["imports", "strategy class", "cerebro setup", "data loading example"],
    }

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_prompt)},
            ],
        )
        return _extract_text(response)
    except Exception:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": str(user_prompt)},
                ],
            )
            return _extract_text(response)
        except Exception:
            return None
