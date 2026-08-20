# A股每日自动复盘系统（方案一 · 轻量内容优先版）

每日交易日收盘后自动拉取中国A股数据 → 本地存储 → 生成结构化复盘 → 后续接 LLM 生成小红书风格文案 + 图表，用于打造财经账号。

## 当前进度（2026-08-20）

已完成：
- [x] 项目脚手架与配置
- [x] 交易日判断
- [x] 数据拉取（指数、涨停跌停；全市场/板块可配置跳过）
- [x] Parquet + SQLite 存储
- [x] 分析引擎骨架（结构化 ReviewResult + 模板摘要）
- [x] 主入口 `scripts/run_daily.py`

待完成（下一阶段）：
- [ ] 图表生成（matplotlib）
- [ ] LLM 文案（Ollama + Qwen 模板 fallback）
- [ ] 内容打包到 `output/YYYY-MM-DD/`
- [ ] APScheduler 定时
- [ ] 半自动发布辅助

## 快速开始

```bash
cd a_share_daily_review
pip install -r requirements.txt

# 运行当日（或最近交易日）
python scripts/run_daily.py

# 指定日期
python scripts/run_daily.py --date 2026-08-20

# 只看不存
python scripts/run_daily.py --no-save
```

## 配置说明

编辑 `config/settings.yaml`：

- `data.skip_heavy_endpoints: true`  
  网络不稳定时跳过全市场快照与部分板块接口（默认 true，保证能跑通）。  
  **你在本地 5070 主机、网络稳定时请改为 `false`**，以获取完整数据。

- `llm.model`: 推荐 `qwen2.5:7b` 或 `qwen2.5:14b` / `qwen3:14b`（需先 `ollama pull`）

## 数据落盘位置

- 行情：`data/parquet/{indices|limit_up|limit_down|...}/YYYY/MM/DD.parquet`
- 日志与摘要：`data/db/review.db`
- 运行日志：`logs/review_YYYYMMDD.log`

## 硬件建议（用户侧）

- GPU：RTX 5070 12GB → 本地跑 Qwen2.5/3 7B~14B Q4 非常合适
- 内存 32G、1TB 足够多年日线 + 部分分钟线

## 免责声明

本系统所有输出仅供学习与研究使用，不构成任何投资建议。自动发布到社交平台请遵守平台规则，建议初期半自动操作。
