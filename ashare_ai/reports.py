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
        lines.append(
            f"- {item['symbol']} {item['name']} | 收盘 {item['close']} | 5日 {item['ret_5d']:.2%} | "
            f"20日 {item['ret_20d']:.2%} | 量比 {item['vol_ratio']:.2f} | RSI {item['rsi14']}"
        )
    return "\n".join(lines)

