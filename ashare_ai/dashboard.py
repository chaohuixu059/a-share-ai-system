from __future__ import annotations

import json
import datetime as dt
from html import escape
from pathlib import Path
from typing import Any


def _format_pct(value: object) -> str:
    try:
        return f"{float(value):.2%}"
    except Exception:
        return "--"


def _format_num(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "--"


def _safe_text(value: object, default: str = "--") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _json_default(value: object) -> object:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return str(value)


def _card(title: str, value: str, subtitle: str = "", accent: str = "accent") -> str:
    subtitle_html = f'<div class="card-subtitle">{escape(subtitle)}</div>' if subtitle else ""
    return (
        f'<section class="card {accent}">'
        f'<div class="card-title">{escape(title)}</div>'
        f'<div class="card-value">{escape(value)}</div>'
        f"{subtitle_html}"
        f"</section>"
    )


def _row_html(item: dict[str, Any], index: int) -> str:
    groups = " / ".join(item.get("sector_groups", []) or []) or "未识别"
    reasons = "；".join(item.get("picker_reasons", [])[:2])
    risk = " / ".join(item.get("risk_tags", []) or [])
    return f"""
      <div class="rank-row">
        <div class="rank-index">{index}</div>
        <div class="rank-body">
          <div class="rank-top">
            <strong>{escape(str(item.get('symbol', '')))} {escape(str(item.get('name', '')))}</strong>
            <span class="score">{_format_num(item.get('picker_score', 0), 2)}</span>
          </div>
          <div class="rank-meta">
            <span>{escape(groups)}</span>
            <span>收盘 {_format_num(item.get('close', ''), 2)}</span>
            <span>5日 {_format_pct(item.get('ret_5d', 0))}</span>
            <span>20日 {_format_pct(item.get('ret_20d', 0))}</span>
            <span>风险 {escape(risk)}</span>
          </div>
          <div class="rank-reason">{escape(reasons)}</div>
        </div>
      </div>
    """


def _build_fund_flow_block(flow_snapshot: dict[str, Any]) -> str:
    market = flow_snapshot.get("market_flow") or []
    industry = flow_snapshot.get("industry_flow") or []
    concept = flow_snapshot.get("concept_flow") or []
    northbound = flow_snapshot.get("northbound_flow") or []
    main_flow = flow_snapshot.get("main_fund_flow") or []

    def row(item: dict[str, Any], columns: list[str], suffix: str = "") -> str:
        cells = []
        for col in columns:
            cells.append(f"<span>{escape(_safe_text(item.get(col, '')))}</span>")
        if suffix:
            cells.append(f"<strong>{escape(suffix)}</strong>")
        return "<div class='flow-row'>" + "".join(cells) + "</div>"

    market_rows = "".join(
        row(item, ["市场名称", "主力净流入", "涨跌幅"], "")
        for item in market[:5]
    ) or "<div class='muted'>暂无市场资金流。</div>"
    industry_rows = "".join(
        row(item, ["板块名称", "今日主力净流入", "今日涨跌幅"], "")
        for item in industry[:6]
    ) or "<div class='muted'>暂无行业资金流。</div>"
    concept_rows = "".join(
        row(item, ["板块名称", "今日主力净流入", "今日涨跌幅"], "")
        for item in concept[:6]
    ) or "<div class='muted'>暂无概念资金流。</div>"
    northbound_rows = "".join(
        row(item, list(item.keys())[:3], "")
        for item in northbound[:3]
    ) or "<div class='muted'>暂无北向资金摘要。</div>"
    main_rows = "".join(
        row(item, ["名称", "主力净流入-净额", "主力净流入-净占比"], "")
        for item in main_flow[:6]
    ) or "<div class='muted'>暂无主力资金排行。</div>"

    return f"""
    <section class="panel section-span-2">
      <div class="section-head">
        <h3>资金流雷达</h3>
        <span class="section-note">市场 / 行业 / 概念 / 北向 / 主力资金</span>
      </div>
      <div class="flow-grid">
        <div class="flow-card"><h4>市场总览</h4>{market_rows}</div>
        <div class="flow-card"><h4>行业资金</h4>{industry_rows}</div>
        <div class="flow-card"><h4>概念资金</h4>{concept_rows}</div>
        <div class="flow-card"><h4>北向摘要</h4>{northbound_rows}</div>
        <div class="flow-card flow-wide"><h4>主力净流入</h4>{main_rows}</div>
      </div>
    </section>
    """


def _build_history_nav(market_summary: dict[str, Any]) -> str:
    day_dir = Path(str(market_summary.get("output_dir", ""))) if market_summary.get("output_dir") else None
    days: list[str] = []
    if day_dir and day_dir.exists():
        days = sorted([item.name for item in day_dir.iterdir() if item.is_dir() and len(item.name) == 10], reverse=True)[:12]
    if not days:
        return "<span class='muted'>暂无历史日期。</span>"
    return "".join(f'<a class="badge" href="{escape(day)}/daily_report.md">{escape(day)}</a>' for day in days)


def build_dashboard_html(
    market_summary: dict,
    feature_table: list[dict],
    picked_stocks: list[dict],
    backtest_summary: dict | None = None,
    failures: list[dict] | None = None,
) -> str:
    backtest_summary = backtest_summary or {}
    failures = failures or []
    top5 = picked_stocks[:5]
    top8 = picked_stocks[:8]
    top_feature = feature_table[:6]
    flow_snapshot = market_summary.get("flow_snapshot", {}) or {}

    sector_counts: dict[str, int] = {}
    for item in picked_stocks:
        for group in item.get("sector_groups", []) or []:
            sector_counts[group] = sector_counts.get(group, 0) + 1
    ranked_sectors = sorted(sector_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:6]
    heatmap = {
        "强势": sum(1 for item in feature_table if float(item.get("ret_5d", 0) or 0) > 0.05),
        "中性": sum(1 for item in feature_table if -0.02 <= float(item.get("ret_5d", 0) or 0) <= 0.05),
        "偏弱": sum(1 for item in feature_table if float(item.get("ret_5d", 0) or 0) < -0.02),
    }
    today = market_summary.get("date", "")
    focus_sector = ranked_sectors[0][0] if ranked_sectors else "暂无"
    focus_sector_subtitle = f"覆盖 {ranked_sectors[0][1]} 只" if ranked_sectors else "等待命中"
    backtest_trade_count = str(backtest_summary.get("trade_count", 0))
    backtest_return = f"收益 {backtest_summary.get('total_return', 0):.2%}" if backtest_summary else "暂无"
    heatmap_bar_html = "".join(
        f'<div class="bar-row"><span>{escape(label)}</span><div class="bar-track"><div class="bar-fill" style="width:{max(10, count * 20)}%"></div></div><strong>{count}</strong></div>'
        for label, count in heatmap.items()
    )
    sector_bar_html = "".join(
        f'<div class="bar-row"><span>{escape(name)}</span><div class="bar-track"><div class="bar-fill" style="width:{min(100, count * 25)}%"></div></div><strong>{count}</strong></div>'
        for name, count in ranked_sectors[:3]
    ) or '<div class="muted">暂无</div>'
    score_bar_html = "".join(
        f'<div class="bar-row"><span>{escape(str(item.get("symbol", "")))}</span><div class="bar-track"><div class="bar-fill" style="width:{max(10, min(100, float(item.get("picker_score", 0)) * 1.5))}%"></div></div><strong>{_format_num(item.get("picker_score", 0), 1)}</strong></div>'
        for item in top5
    ) or '<div class="muted">暂无</div>'
    history_html = _build_history_nav(market_summary)

    summary_html = "".join(
        [
            _card("观察池", str(market_summary.get("success_count", 0)), f"失败 {market_summary.get('failure_count', 0)} 只"),
            _card("今日前排", str(len(top5)), "按综合评分排序"),
            _card("聚焦赛道", focus_sector, focus_sector_subtitle),
            _card("回测交易", backtest_trade_count, backtest_return),
        ]
    )

    sector_html = "".join(
        f'<div class="sector-pill"><span>{escape(name)}</span><strong>{count}</strong></div>'
        for name, count in ranked_sectors
    ) or '<div class="muted">暂无明确聚焦。</div>'

    action_html = ""
    if top8:
        action_rows = []
        for item in top8:
            groups = " / ".join(item.get("sector_groups", []) or []) or "未识别"
            action_rows.append(
                f"""
                <div class="action-row">
                  <div class="action-main">
                    <strong>{escape(str(item.get('symbol', '')))} {escape(str(item.get('name', '')))}</strong>
                    <span>{escape(groups)}</span>
                  </div>
                  <div class="action-meta">
                    <span>评分 {_format_num(item.get('picker_score', 0), 2)}</span>
                    <span>5日 {_format_pct(item.get('ret_5d', 0))}</span>
                    <span>20日 {_format_pct(item.get('ret_20d', 0))}</span>
                  </div>
                </div>
                """
            )
        action_html = "".join(action_rows)
    else:
        action_html = '<div class="muted">暂无前排样本。</div>'

    ranks_html = "".join(_row_html(item, idx + 1) for idx, item in enumerate(top5)) or '<div class="muted">暂无前排候选。</div>'
    snapshot_html = "".join(
        f"""
        <div class="snapshot-item">
          <div><strong>{escape(str(item.get('symbol', '')))} {escape(str(item.get('name', '')))}</strong></div>
          <div class="snapshot-meta">5日 {_format_pct(item.get('ret_5d', 0))} · 20日 {_format_pct(item.get('ret_20d', 0))} · 量比 {_format_num(item.get('vol_ratio', 1.0), 2)}</div>
        </div>
        """
        for item in top_feature
    ) or '<div class="muted">暂无快照。</div>'

    failure_html = "".join(
        f"<li>{escape(str(item.get('symbol', '')))} {escape(str(item.get('name', '')))}: {escape(str(item.get('error', '')))}</li>"
        for item in failures[:6]
    )

    chart_data = json.dumps(
        {
            "heatmap": heatmap,
            "sectors": ranked_sectors,
            "top": [
                {
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "score": item.get("picker_score", 0),
                    "ret5": item.get("ret_5d", 0),
                }
                for item in top5
            ],
        },
        ensure_ascii=False,
    )
    flow_data = json.dumps(flow_snapshot, ensure_ascii=False, default=_json_default)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>A股每日仪表盘</title>
  <style>
    :root {{
      --bg: #08101e;
      --panel: rgba(13, 20, 38, 0.88);
      --panel-2: rgba(17, 28, 52, 0.82);
      --line: rgba(255,255,255,0.10);
      --text: #eff4ff;
      --muted: #9fb0d0;
      --accent: #7dd3fc;
      --accent2: #c084fc;
      --good: #34d399;
      --warn: #fbbf24;
      --sidebar: rgba(9, 14, 28, 0.92);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(125, 211, 252, 0.18), transparent 22%),
        radial-gradient(circle at right center, rgba(192, 132, 252, 0.12), transparent 25%),
        linear-gradient(180deg, #050913 0%, #08101e 55%, #0c1527 100%);
      color: var(--text);
      min-height: 100vh;
    }}
    .app {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 24px 18px;
      background: var(--sidebar);
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .brand {{
      padding: 18px;
      border-radius: 20px;
      background: linear-gradient(180deg, rgba(125,211,252,0.16), rgba(192,132,252,0.10));
      border: 1px solid var(--line);
    }}
    .brand .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: .18em;
      font-size: 11px;
      margin-bottom: 8px;
    }}
    .brand h1 {{
      margin: 0;
      font-size: 24px;
      line-height: 1.1;
    }}
    .brand p {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      margin: 10px 0 0;
    }}
    .nav {{
      display: grid;
      gap: 10px;
    }}
    .nav a, .nav button {{
      appearance: none;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      text-decoration: none;
      padding: 12px 14px;
      border-radius: 14px;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }}
    .nav a:hover, .nav button:hover {{ background: rgba(255,255,255,0.08); }}
    .sidebar .mini {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      line-height: 1.65;
    }}
    .content {{
      padding: 28px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.5fr 0.9fr;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .hero-main, .hero-side, .panel, .card {{
      backdrop-filter: blur(16px);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: 0 18px 60px rgba(0, 0, 0, 0.26);
      border-radius: 24px;
    }}
    .hero-main {{
      padding: 28px;
      position: relative;
      overflow: hidden;
    }}
    .hero-main::after {{
      content: "";
      position: absolute;
      inset: auto -8% -54% auto;
      width: 380px;
      height: 380px;
      background: radial-gradient(circle, rgba(125, 211, 252, 0.22), transparent 68%);
      pointer-events: none;
    }}
    .eyebrow {{
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      margin-bottom: 12px;
    }}
    h2, h3, h4 {{ margin: 0; }}
    h2 {{
      font-size: clamp(34px, 4vw, 54px);
      line-height: 1.05;
    }}
    .subtitle {{
      margin-top: 12px;
      max-width: 840px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.75;
    }}
    .hero-meta, .toolbar-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.05);
      color: var(--text);
      text-decoration: none;
    }}
    .badge.good {{ color: var(--good); }}
    .badge.warn {{ color: var(--warn); }}
    .hero-side {{
      padding: 22px;
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .hero-side h3, .panel h3 {{
      font-size: 15px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .card {{
      padding: 18px;
      background: var(--panel-2);
      min-height: 128px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .card-title {{ color: var(--muted); font-size: 13px; }}
    .card-value {{ font-size: 28px; font-weight: 700; letter-spacing: -0.03em; }}
    .card-subtitle {{ color: var(--muted); font-size: 12px; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 12px;
      margin: 18px 0;
    }}
    .toolbar .group {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .toolbar button, .toolbar a {{
      appearance: none;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      text-decoration: none;
      padding: 10px 14px;
      border-radius: 12px;
      cursor: pointer;
      font: inherit;
    }}
    .toolbar button:hover, .toolbar a:hover {{
      background: rgba(255,255,255,0.1);
    }}
    .section-block, .panel {{
      padding: 22px;
      background: rgba(13, 20, 38, 0.84);
      border: 1px solid var(--line);
      border-radius: 24px;
      margin-bottom: 18px;
    }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
      margin-bottom: 16px;
    }}
    .section-note {{
      color: var(--muted);
      font-size: 12px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1.25fr 0.9fr;
      gap: 18px;
    }}
    .rank-row {{
      display: grid;
      grid-template-columns: 42px 1fr;
      gap: 14px;
      padding: 14px 0;
      border-top: 1px solid var(--line);
    }}
    .rank-row:first-child {{ border-top: 0; padding-top: 0; }}
    .rank-index {{
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, rgba(125, 211, 252, 0.22), rgba(192, 132, 252, 0.22));
      color: white;
      font-weight: 700;
    }}
    .rank-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
    .score {{ color: var(--accent); font-size: 20px; font-weight: 700; }}
    .rank-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 12px;
      margin: 8px 0;
      color: var(--muted);
      font-size: 12px;
    }}
    .rank-reason {{ color: #d8e4ff; font-size: 13px; line-height: 1.5; }}
    .sector-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .sector-pill {{
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--text);
    }}
    .snapshot-item {{
      padding: 12px 0;
      border-top: 1px solid var(--line);
    }}
    .snapshot-item:first-child {{ border-top: 0; padding-top: 0; }}
    .snapshot-meta {{ color: var(--muted); font-size: 12px; margin-top: 5px; }}
    .muted {{ color: var(--muted); }}
    .footer {{
      margin-top: 18px;
      padding: 16px 22px;
      border-radius: 18px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
    }}
    .chart-box {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }}
    .mini-chart {{
      padding: 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--line);
    }}
    .mini-chart h4 {{
      margin: 0 0 12px;
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .bars {{
      display: grid;
      gap: 10px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 68px 1fr 44px;
      gap: 10px;
      align-items: center;
      font-size: 12px;
    }}
    .bar-track {{
      position: relative;
      height: 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
    }}
    .bar-fill {{
      position: absolute;
      inset: 0 auto 0 0;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(125,211,252,0.75), rgba(192,132,252,0.95));
    }}
    .flow-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .flow-card {{
      padding: 16px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.05);
    }}
    .flow-card h4 {{
      margin: 0 0 12px;
      font-size: 13px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .flow-row {{
      display: grid;
      grid-template-columns: 1.2fr 1fr 0.7fr;
      gap: 8px;
      padding: 8px 0;
      border-top: 1px solid rgba(255,255,255,0.06);
      font-size: 12px;
      color: var(--text);
    }}
    .flow-row:first-child {{ border-top: 0; padding-top: 0; }}
    .section-span-2 {{ grid-column: 1 / -1; }}
    .action-grid {{
      display: grid;
      gap: 10px;
    }}
    .action-row {{
      display: grid;
      grid-template-columns: 1.3fr 1fr;
      gap: 12px;
      padding: 12px 0;
      border-top: 1px solid rgba(255,255,255,0.06);
    }}
    .action-row:first-child {{ border-top: 0; padding-top: 0; }}
    .action-main {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .action-main span, .action-meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    .action-meta {{
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px 12px;
      align-items: center;
    }}
    @media (max-width: 1200px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; height: auto; }}
      .hero, .layout, .metric-grid, .chart-box, .flow-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="eyebrow">A-Share Research Desk</div>
        <h1>本地研究台</h1>
        <p>赛道、资金流、候选股、回测和历史日报都集中在这里。你可以把它当成一个轻量版交易研究台来用。</p>
      </div>
      <nav class="nav">
        <a href="#overview">总览</a>
        <a href="#flow">资金流</a>
        <a href="#heat">热度</a>
        <a href="#rank">前排</a>
        <a href="#history">历史</a>
        <a href="latest_daily_report.md">详细日报</a>
        <a href="picked_stocks.csv">候选 CSV</a>
      </nav>
      <div class="mini">
        <div><strong>自动刷新</strong>：60 秒</div>
        <div><strong>日期</strong>：{escape(str(today)) if today else "最新"}</div>
        <div><strong>输出目录</strong>：{escape(str(market_summary.get("output_dir", "")))}</div>
      </div>
      <div class="mini">
        <strong>提示</strong><br />
        左边用于跳转，右边用于快速扫盘。资金流数据抓不到时会自动降级为空，不影响主页面。
      </div>
    </aside>
    <main class="content">
      <section class="hero" id="overview">
        <div class="hero-main">
          <div class="eyebrow">今日盘面</div>
          <h2>今天先看赛道，再看前排。</h2>
          <div class="subtitle">
            这是一个本地生成的 A 股 AI 仪表盘。它把全市场观察池、细分赛道、候选股前排、资金流摘要和回测结果放在一页里，
            方便你快速浏览，而不必翻开长报告。
          </div>
          <div class="hero-meta">
            <span class="badge good">观察池 {market_summary.get("success_count", 0)} 只</span>
            <span class="badge">失败 {market_summary.get("failure_count", 0)} 只</span>
            <span class="badge">最强赛道 {escape(focus_sector)}</span>
            <span class="badge">赛道热度 {escape(", ".join(f"{k} {v}" for k, v in heatmap.items()))}</span>
          </div>
        </div>
        <aside class="hero-side">
          <h3>今日信号</h3>
          <div class="badge warn">细分赛道权重已启用</div>
          <div class="badge">桌面最新页：latest_dashboard.html</div>
          <div class="badge">历史日报：latest_daily_report.md</div>
          <div class="badge">日期目录：/2026-06-23</div>
        </aside>
      </section>

      <div class="toolbar">
        <div class="group">
          <a href="latest_dashboard.html">刷新最新页</a>
          <a href="latest_daily_report.md">查看详细版</a>
          <a href="picked_stocks.csv">下载候选股</a>
        </div>
        <div class="group">
          <label class="badge"><input id="autoRefresh" type="checkbox" checked /> 自动刷新</label>
          <span class="badge">每 60 秒</span>
        </div>
      </div>

      <section class="panel" id="history">
        <div class="section-head">
          <h3>历史日期</h3>
          <span class="section-note">点击切换对应日期日报</span>
        </div>
        <div class="hero-meta">{history_html}</div>
      </section>

      <section class="metric-grid">
        {summary_html}
      </section>

      <section class="section-block" id="flow">
        <div class="section-head">
          <h3>资金流雷达</h3>
          <span class="section-note">市场 / 行业 / 概念 / 北向 / 主力资金</span>
        </div>
        <div class="flow-grid">
          <div class="flow-card"><h4>市场总览</h4>{_build_fund_flow_block(flow_snapshot)}</div>
        </div>
      </section>

      <section class="panel" id="heat" style="margin-bottom:18px;">
        <div class="section-head">
          <h3>热度与结构</h3>
          <span class="section-note">赛道热度、赛道分布和前排分数</span>
        </div>
        <div class="chart-box">
          <div class="mini-chart">
            <h4>赛道热度</h4>
            <div class="bars">{heatmap_bar_html}</div>
          </div>
          <div class="mini-chart">
            <h4>赛道分布</h4>
            <div class="bars">{sector_bar_html}</div>
          </div>
          <div class="mini-chart">
            <h4>前排分数</h4>
            <div class="bars">{score_bar_html}</div>
          </div>
        </div>
      </section>

      <section class="layout" id="rank">
        <div class="panel">
          <div class="section-head">
            <h3>前排候选</h3>
            <span class="section-note">按综合评分排序</span>
          </div>
          {ranks_html}
        </div>
        <div style="display:grid; gap:18px;">
          <div class="panel">
            <div class="section-head">
              <h3>赛道聚焦</h3>
              <span class="section-note">细分赛道命中数</span>
            </div>
            <div class="sector-grid">{sector_html}</div>
          </div>
          <div class="panel">
            <div class="section-head">
              <h3>行动区</h3>
              <span class="section-note">仓位模板与当前前排样本</span>
            </div>
            <div class="action-grid">
              <div class="badge warn">40% 现金 / 25% 核心趋势 / 20% 观察 / 15% 机动</div>
              <div class="muted">当前环境更适合只做前排和右侧确认，不做左侧抄底。</div>
              {action_html}
            </div>
          </div>
          <div class="panel">
            <div class="section-head">
              <h3>观察池快照</h3>
              <span class="section-note">最近 6 只样本</span>
            </div>
            {snapshot_html}
          </div>
          <div class="panel">
            <div class="section-head">
              <h3>降级与风险</h3>
              <span class="section-note">先研究，后验证</span>
            </div>
            <div class="muted">本系统只做研究与观察，不构成投资建议。</div>
            <ul>
              <li>A股执行遵循 T+1 和涨跌停约束。</li>
              <li>任何 AI 生成内容都应先做本地回测。</li>
            </ul>
            <ul>{failure_html}</ul>
          </div>
        </div>
      </section>

      <div class="footer">
        生成时间：本地运行自动刷新。你可以直接打开这个 HTML 页面查看最新结果。资金流数据若暂时抓不到，会自动降级，不影响主页面。
      </div>
    </main>
  </div>
  <script>
    const state = {chart_data};
    const fundFlow = {flow_data};
    const auto = document.getElementById('autoRefresh');
    if (auto && auto.checked) {{
      setInterval(() => window.location.reload(), 60000);
    }}
    auto && auto.addEventListener('change', () => {{
      if (auto.checked) {{
        window.location.reload();
      }}
    }});
    console.log({{ state, fundFlow }});
  </script>
</body>
</html>"""


def write_dashboard_html(output_path: Path, html: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
