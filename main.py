from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from dotenv import load_dotenv

from ashare_ai.ai_client import generate_report, generate_strategy_code
from ashare_ai.backtest import backtest_ma_volume_strategy
from ashare_ai.config import load_settings
from ashare_ai.fetchers import build_market_samples, load_watchlist, select_symbols
from ashare_ai.notify import send_email, send_webhook
from ashare_ai.reports import build_summary_block, ensure_day_dir, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A-share AI analysis system")
    parser.add_argument("--mode", choices=["report", "strategy", "backtest"], default="report")
    parser.add_argument("--start-date", default=None, help="YYYYMMDD, 默认回看天数")
    parser.add_argument("--end-date", default=None, help="YYYYMMDD, 默认今天")
    parser.add_argument("--symbol", default=None, help="回测指定股票代码")
    parser.add_argument("--limit", type=int, default=None, help="观察池数量")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    settings = load_settings()
    args = parse_args()

    if not settings.openai_api_key and args.mode in {"report", "strategy"}:
        raise SystemExit("缺少 OPENAI_API_KEY，请先在 .env 中填写。")

    today = dt.date.today()
    end_date = args.end_date or today.strftime("%Y%m%d")
    start_date = args.start_date or (today - dt.timedelta(days=settings.lookback_days)).strftime("%Y%m%d")
    day_dir = ensure_day_dir(settings.output_dir, today.isoformat())

    watchlist = load_watchlist(settings.watchlist_file, settings.watchlist)
    symbols = select_symbols(watchlist, args.limit or settings.universe_limit)

    snapshots, failures = build_market_samples(symbols, start_date, end_date)
    feature_table = sorted(snapshots, key=lambda item: item["score"], reverse=True)

    market_summary = {
        "date": today.isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "symbol_count": len(symbols),
        "success_count": len(snapshots),
        "failure_count": len(failures),
        "failures": failures[:10],
        "summary_block": build_summary_block(feature_table),
    }

    write_json(day_dir / "market_summary.json", {"market_summary": market_summary, "feature_table": feature_table})

    if args.mode == "backtest":
        backtest_symbol = args.symbol or (symbols[0][0] if symbols else "600519")
        try:
            from ashare_ai.fetchers import fetch_daily_history

            hist = fetch_daily_history(backtest_symbol, start_date, end_date)
            backtest_summary = backtest_ma_volume_strategy(hist)
        except Exception as exc:
            backtest_summary = {"error": str(exc), "symbol": backtest_symbol}

        write_json(day_dir / "backtest_summary.json", {"symbol": backtest_symbol, "summary": backtest_summary})
        print(json.dumps({"symbol": backtest_symbol, "backtest_summary": backtest_summary}, ensure_ascii=False, indent=2))
        return 0

    backtest_summary = None
    backtest_symbol = args.symbol or (feature_table[0]["symbol"] if feature_table else (symbols[0][0] if symbols else "600519"))

    try:
        from ashare_ai.fetchers import fetch_daily_history

        hist = fetch_daily_history(backtest_symbol, start_date, end_date)
        backtest_summary = backtest_ma_volume_strategy(hist)
        write_json(day_dir / "backtest_summary.json", {"symbol": backtest_symbol, "summary": backtest_summary})
    except Exception as exc:
        backtest_summary = {"error": str(exc), "symbol": backtest_symbol}
        write_json(day_dir / "backtest_summary.json", backtest_summary)

    if args.mode == "strategy":
        strategy_code = generate_strategy_code(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            feature_table=feature_table,
            backtest_summary=backtest_summary,
        )
        strategy_path = day_dir / "generated_strategy.py"
        write_text(strategy_path, strategy_code)

        notify_text = f"策略代码已生成：{strategy_path.name}\n\n{strategy_code[:1200]}"
        send_webhook(settings.notify_provider, settings.notify_webhook_url, "A股策略生成", notify_text)
        send_email(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_to, "A股策略生成", notify_text)

        print(strategy_code)
        return 0

    report = generate_report(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        market_summary=market_summary,
        feature_table=feature_table,
        backtest_summary=backtest_summary,
    )
    report_path = day_dir / "daily_report.md"
    write_text(report_path, report)

    notify_text = f"{market_summary['summary_block']}\n\n{report[:1500]}"
    send_webhook(settings.notify_provider, settings.notify_webhook_url, "A股每日复盘", notify_text)
    send_email(settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, settings.smtp_to, "A股每日复盘", notify_text)

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
