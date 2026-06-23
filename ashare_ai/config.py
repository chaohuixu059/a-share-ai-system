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


def _split_watchlist(raw: str) -> list[str]:
    items = [item.strip() for item in raw.split(",")]
    return [item for item in items if item]


def load_settings() -> Settings:
    watchlist_file = Path(os.getenv("WATCHLIST_FILE", "watchlist.txt")).expanduser()
    output_dir = Path(os.getenv("OUTPUT_DIR", "outputs")).expanduser()
    raw_watchlist = os.getenv("WATCHLIST", "")
    watchlist = _split_watchlist(raw_watchlist)
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
    )
