from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    watchlist: list[str]
    watchlist_file: Path
    output_dir: Path
    notify_provider: str
    notify_webhook_url: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_to: str
    universe_limit: int
    lookback_days: int
    report_mode: str
    data_cache_dir: Path
    data_max_retries: int
    data_retry_min_seconds: float
    data_retry_max_seconds: float
    data_use_baostock: bool
    universe_mode: str
    preferred_sector_keywords: list[str]
    sector_keyword_weights: dict[str, float]
    sector_keyword_aliases: dict[str, list[str]]
    sector_group_weights: dict[str, float]
    sector_boost: float
    pick_top_n: int
    pick_export_csv: Path


def _split_watchlist(raw: str) -> list[str]:
    items = [item.strip() for item in raw.split(",")]
    return [item for item in items if item]


def _parse_keyword_weights(raw: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        if ":" not in item:
            continue
        keyword, weight_text = item.split(":", 1)
        keyword = keyword.strip()
        weight_text = weight_text.strip()
        if not keyword:
            continue
        try:
            weights[keyword] = float(weight_text)
        except ValueError:
            continue
    return weights


def _parse_keyword_aliases(raw: str) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for item in [part.strip() for part in raw.split(";") if part.strip()]:
        if "=" not in item:
            continue
        keyword, alias_text = item.split("=", 1)
        keyword = keyword.strip()
        alias_list = [alias.strip() for alias in alias_text.split("|") if alias.strip()]
        if keyword and alias_list:
            aliases[keyword] = alias_list
    return aliases


def _parse_group_weights(raw: str) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in [part.strip() for part in raw.split(",") if part.strip()]:
        if ":" not in item:
            continue
        keyword, weight_text = item.split(":", 1)
        keyword = keyword.strip()
        weight_text = weight_text.strip()
        if not keyword:
            continue
        try:
            weights[keyword] = float(weight_text)
        except ValueError:
            continue
    return weights


def _default_output_dir() -> Path:
    desktop_output = os.getenv("DESKTOP_OUTPUT", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if desktop_output:
        return Path.home() / "Desktop" / "a-share-ai-system-output"
    return Path("outputs")


def load_settings() -> Settings:
    watchlist_file = Path(os.getenv("WATCHLIST_FILE", "watchlist.txt")).expanduser()
    desktop_output = os.getenv("DESKTOP_OUTPUT", "").strip().lower() in {"1", "true", "yes", "y", "on"}
    if desktop_output:
        output_dir = _default_output_dir()
    else:
        output_dir = Path(os.getenv("OUTPUT_DIR", str(_default_output_dir()))).expanduser()
    data_cache_dir = Path(os.getenv("DATA_CACHE_DIR", "cache")).expanduser()
    default_pick_export_csv = output_dir / "picked_stocks.csv"
    if desktop_output:
        pick_export_csv = default_pick_export_csv
    else:
        pick_export_csv = Path(os.getenv("PICK_EXPORT_CSV", str(default_pick_export_csv))).expanduser()
    raw_watchlist = os.getenv("WATCHLIST", "")
    watchlist = _split_watchlist(raw_watchlist)
    preferred_sector_keywords = _split_watchlist(os.getenv("PREFERRED_SECTOR_KEYWORDS", "科技,电子,半导体,算力,AI,软件,芯片,通信,消费电子,光模块"))
    sector_keyword_weights = _parse_keyword_weights(
        os.getenv(
            "SECTOR_KEYWORD_WEIGHTS",
            "科技:4,电子:6,半导体:12,算力:11,AI:10,软件:6,芯片:11,通信:8,消费电子:5,光模块:12",
        )
    )
    sector_keyword_aliases = _parse_keyword_aliases(
        os.getenv(
            "SECTOR_KEYWORD_ALIASES",
            "半导体=半导体|芯片|集成电路|存储|封测|晶圆|设备|兆易创新|寒武纪|澜起科技|长电科技;算力=算力|服务器|液冷|GPU|AI服务器|IDC|寒武纪|中际旭创|新易盛|工业富联;光模块=光模块|CPO|800G|100G|中际旭创|新易盛|天孚通信|光迅科技;通信=通信|5G|6G|光通信|光纤|亨通光电|中天科技|中兴通讯;AI=AI|人工智能|大模型|算法|寒武纪|算力芯片;电子=电子|消费电子|元器件|PCB|京东方A|立讯精密|歌尔股份;软件=软件|SaaS|应用软件|云计算|东方财富",
        )
    )
    sector_group_weights = _parse_group_weights(
        os.getenv(
            "SECTOR_GROUP_WEIGHTS",
            "半导体:16,芯片:14,存储:13,半导体设备:15,算力:14,AI:12,光模块:16,光通信:11,通信:9,电子:6,消费电子:6,软件:5",
        )
    )
    if not watchlist and watchlist_file.exists():
        watchlist = [line.strip() for line in watchlist_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip(),
        watchlist=watchlist,
        watchlist_file=watchlist_file,
        output_dir=output_dir,
        notify_provider=os.getenv("NOTIFY_PROVIDER", "").strip().lower(),
        notify_webhook_url=os.getenv("NOTIFY_WEBHOOK_URL", "").strip(),
        smtp_host=os.getenv("SMTP_HOST", "").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", "").strip(),
        smtp_to=os.getenv("SMTP_TO", "").strip(),
        universe_limit=int(os.getenv("UNIVERSE_LIMIT", "30")),
        lookback_days=int(os.getenv("LOOKBACK_DAYS", "120")),
        report_mode=os.getenv("REPORT_MODE", "daily").strip(),
        data_cache_dir=data_cache_dir,
        data_max_retries=int(os.getenv("DATA_MAX_RETRIES", "5")),
        data_retry_min_seconds=float(os.getenv("DATA_RETRY_MIN_SECONDS", "2")),
        data_retry_max_seconds=float(os.getenv("DATA_RETRY_MAX_SECONDS", "5")),
        data_use_baostock=os.getenv("DATA_USE_BAOSTOCK", "true").strip().lower() in {"1", "true", "yes", "y", "on"},
        universe_mode=os.getenv("UNIVERSE_MODE", "full").strip().lower(),
        preferred_sector_keywords=preferred_sector_keywords,
        sector_keyword_weights=sector_keyword_weights,
        sector_keyword_aliases=sector_keyword_aliases,
        sector_group_weights=sector_group_weights,
        sector_boost=float(os.getenv("SECTOR_BOOST", "8")),
        pick_top_n=int(os.getenv("PICK_TOP_N", "10")),
        pick_export_csv=pick_export_csv,
    )
