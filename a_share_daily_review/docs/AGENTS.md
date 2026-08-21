# 给智能体 / 协作者的项目说明

本文面向需要改代码或继续开发的 **AI Agent 与人类开发者**。先读本文件再改仓库。

---

## 一句话目标

每天自动产出两类**可人工审核的草稿**（盘前海外资讯帖 + A 股收盘复盘帖），支持本机审核页与钉钉通知；**禁止**默认自动发到小红书等对外平台。

---

## 硬约束（不要改坏）

1. **不自动对外发帖**：草稿字段 `auto_publish: false` 为产品决策。  
2. **LLM 不得编造数字与来源**：只润色已有结构化输入。  
3. **合规**：无荐股、无收益承诺；文末短版免责声明。  
4. **密钥**：钉钉 webhook、secret 仅本地配置，勿写入真实 token。  
5. **数据产物不入库**：`output/`、`logs/`、行情 parquet 等应被 gitignore。

---

## 仓库位置

- Monorepo：`zhitianxia` → 子项目 `a_share_daily_review/`  
- 远程：`git@github.com:zitangkou/zhitianxia.git`  
- 运行前 cwd 必须是 **`a_share_daily_review` 根目录**。

---

## 模块地图

| 路径 | 职责 | 入口 |
|------|------|------|
| `src/data/fetcher.py` | A 股行情/涨停/龙虎榜等 | `run_daily.py` |
| `src/data/storage.py` | Parquet + SQLite | `run_daily.py` |
| `src/analysis/review.py` | 惊喜点与 summary_text | `ReviewEngine.build` |
| `src/news/*` | RSS 拉取过滤打分成稿 | `run_morning.py` |
| `src/content/charts.py` | 复盘图 | `build_review_draft` |
| `src/content/llm.py` | Ollama 润色 | 可选 |
| `src/content/review_draft.py` | review_draft.json/md | `run_daily.py` |
| `src/notify/*` | 钉钉推送 | `--notify` 或 `notify.enabled` |
| `src/review_ui/app.py` | 本机审核 HTTP | 端口 8787 |

配置：`config/settings.yaml`、`config/news_sources.yaml`。

---

## 主数据流

```text
早报: news_sources → fetch → filter → score → draft → 可选LLM → 可选钉钉 → 人审
复盘: fetcher → storage → ReviewEngine → charts + review_draft → 可选LLM → 可选钉钉 → 人审
```

输出：`output/YYYY-MM-DD/`。

---

## 修改时注意

- 改早报源：优先只改 `news_sources.yaml`。  
- 改「吸引人」逻辑：`src/analysis/review.py`。  
- 加 IM 渠道：`src/notify/dispatch.py`。  
- 改草稿 JSON 字段时同步 `review_ui`。  
- 弱网：`data.skip_heavy_endpoints: true`。

---

## 测试清单

```bash
python scripts/run_morning.py
python scripts/run_daily.py --no-llm --force
python -c "from src.notify import push_message; print('ok')"
```

相关：`06_架构与数据流.md`、`02_内容与审核规范_v1.md`、`05_钉钉推送.md`、`07_变更记录.md`。
