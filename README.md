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

## GitHub Actions

已放好 `.github/workflows/daily_analysis.yml`。你只需要：

1. 把仓库推到 GitHub
2. 在仓库 Secrets 中添加 `OPENAI_API_KEY`
3. 如需通知，再加 `NOTIFY_WEBHOOK_URL`

## 安全说明

- 不会默认执行 AI 生成的代码
- 回测使用的是本地安全模板
- A 股规则已在 Prompt 中明确了 T+1 和涨跌停约束

## 数据降级策略

- 全市场和历史行情都会优先使用 AkShare 的主接口
- 主接口失败后会自动尝试备用接口
- 如果单只股票抓取失败，系统会记录错误并跳过，不会中断整份日报
- 日报里会明确标注本次数据降级情况

## 你可以继续加的能力

- 财经新闻抓取
- 北向资金、涨停池、行业轮动
- 更完整的 Backtrader / Qlib 策略层
- 企业微信、Server酱、邮件多通道推送
