# A 股 AI 自动化系统

这是一个可直接运行的最小可用版本，包含：

- A 股数据抓取
- 简单技术指标计算
- OpenAI 复盘/策略生成
- 内置安全回测示例
- GitHub Actions 定时执行
- Webhook/邮件通知

## 先做什么

1. 复制 `.env.example` 为 `.env`
2. 填入 `OPENAI_API_KEY`
3. 如果你有自己的模型名，就改 `OPENAI_MODEL`
4. 需要的话再改 `WATCHLIST`
5. 如果要启用 i问财价值投资股票池，填入 `IWENCAI_API_KEY`，并确认 `IWENCAI_ENABLED=true`

## 安装

```bash
pip install -r requirements.txt
```

## 运行

默认生成每日复盘报告：

```bash
python main.py
```

生成策略代码：

```bash
python main.py --mode strategy
```

运行内置回测：

```bash
python main.py --mode backtest
```

## 输出

会生成：

- `outputs/YYYY-MM-DD/daily_report.md`
- `outputs/YYYY-MM-DD/market_summary.json`
- `outputs/YYYY-MM-DD/generated_strategy.py` 或 `backtest_summary.json`

如果你把 `OUTPUT_DIR` 设成桌面路径，比如 `~/Desktop/a-share-ai-system-output`，文件就会直接出现在桌面下面。
如果你想强制把最新日报单独输出到桌面，只要把 `DESKTOP_OUTPUT=true` 打开即可；程序会额外生成 `latest_daily_report.md`，方便你每天直接查看最新结果。
如果你还想直接打开网页版本，可以看 `latest_dashboard.html`，它是本地生成的静态仪表盘页面。
仪表盘侧边栏和页脚会显示“最后生成时间”，你刷新页面时可以直接判断是不是刚跑过。

## 个股盘后分析

系统现在支持对单只股票做盘后技术分析，会读取最近 10 天的真实量价数据并输出一份人类可读的分析摘要。

默认规则：

- 优先分析当前前排第一只股票
- 如果你在 `.env` 里设置了 `STOCK_ANALYSIS_SYMBOL`，会优先分析你指定的标的
- 如果你设置了 `STOCK_ANALYSIS_SYMBOLS=600519,300750,002594`，系统会逐只分析这些股票
- 会同时输出：
  - `latest_stock_analysis.md`
  - `stock_analysis.json`
  - 仪表盘中的“个股分析”卡片

可配置项：

- `STOCK_ANALYSIS_ENABLED=true`
- `STOCK_ANALYSIS_SYMBOL=600519`
- `STOCK_ANALYSIS_SYMBOLS=600519,300750,002594`
- `STOCK_ANALYSIS_NAME=贵州茅台`
- `STOCK_ANALYSIS_NAMES=贵州茅台,宁德时代,比亚迪`
- `STOCK_ANALYSIS_LOOKBACK_DAYS=10`
- `STOCK_ANALYSIS_MAX_COUNT=0`

## i问财股票池

系统现在支持把同花顺 i问财结果直接写进仪表盘，默认使用这个筛选条件：

- 股息率大于 1.5%
- 连续 3 年分红
- 经营活动现金流净额为正
- ROE 大于 6%

你可以在 `.env` 里修改 `IWENCAI_QUERY`，也可以通过 `IWENCAI_ENABLED=false` 临时关闭。

仪表盘首页会优先显示：

1. 主线
2. i问财价值池 20 只
3. 三只重点观察
4. 买卖纪律和风险提示

## GitHub Actions

已放好 `.github/workflows/daily_analysis.yml`。你只需要：

1. 把仓库推到 GitHub
2. 在仓库 Secrets 中添加 `OPENAI_API_KEY`
3. 如需通知，再加 `NOTIFY_WEBHOOK_URL`
4. 现在默认会在北京时间 09:00、13:00、15:00 各自动跑一次

## 本机自动定时

如果你希望本机桌面的 `latest_dashboard.html` 也在北京时间 09:00、13:00、15:00 自动刷新，可以安装 macOS 的 LaunchAgent：

```bash
chmod +x scripts/run_local_analysis.sh
cp com.xuxu.a-share-ai-system.daily.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.xuxu.a-share-ai-system.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.xuxu.a-share-ai-system.daily.plist
```

本机定时会把结果写到：

- `~/Desktop/a-share-ai-system-output/latest_dashboard.html`
- `~/Desktop/a-share-ai-system-output/latest_daily_report.md`
- `~/Desktop/a-share-ai-system-output/latest_stock_analysis.md`
- `~/Desktop/a-share-ai-system-output/latest_breakout_analysis.md`

## 安全说明

- 不会默认执行 AI 生成的代码
- 回测使用的是本地安全模板
- A 股规则已在 Prompt 中明确了 T+1 和涨跌停约束

## 数据降级策略

- 全市场和历史行情都会优先使用 AkShare 的主接口
- 主接口失败后会自动尝试备用接口
- 如果单只股票抓取失败，系统会记录错误并跳过，不会中断整份日报
- 日报里会明确标注本次数据降级情况
- `DATA_CACHE_DIR` 可以把历史行情缓存到本地，避免重复抓取
- `DATA_MAX_RETRIES`、`DATA_RETRY_MIN_SECONDS`、`DATA_RETRY_MAX_SECONDS` 用来控制重试和随机退避
- `DATA_USE_BAOSTOCK=true` 时会在 AkShare 全部失败后自动切换到 BaoStock 备用源
- `DATA_USE_TUSHARE=true` 时会在 AkShare 和 BaoStock 都失败后自动切换到 Tushare 备用源
- `TUSHARE_TOKEN` 用来访问 Tushare Pro，建议放在 `.env` 或 GitHub Secrets 里，不要写进代码

## 选股策略

- 默认支持全市场候选池
- `PREFERRED_SECTOR_KEYWORDS` 会给科技、电子、半导体等偏好板块加分
- `PICK_TOP_N` 控制最终展示的候选数量
- `PICK_EXPORT_CSV` 会把候选股导出成单独的 CSV 文件，便于你直接查看
- `SECTOR_KEYWORD_WEIGHTS` 支持给半导体、算力、光模块等细分赛道单独加权
- `SECTOR_KEYWORD_ALIASES` 支持把一个赛道扩展成多个关键词，适合做半导体设备、AI服务器、光通信这种更细颗粒度的偏好
- `OPEN_DASHBOARD_HTML=true` 会额外生成可直接在浏览器打开的 HTML 仪表盘

## 你可以继续加的能力

- 财经新闻抓取
- 北向资金、涨停池、行业轮动
- 更完整的 Backtrader / Qlib 策略层
- 企业微信、Server酱、邮件多通道推送
