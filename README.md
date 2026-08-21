# 知天下（zhitianxia）

个人工具 monorepo。远程：`git@github.com:zitangkou/zhitianxia.git`

## 模块

| 目录 | 说明 |
|------|------|
| [a_share_daily_review](./a_share_daily_review/) | A 股盘前早报 + 收盘复盘草稿；本机审核；可选钉钉；**不自动发社媒** |

- 总览：`a_share_daily_review/docs/00_项目总览.md`
- 智能体：`a_share_daily_review/docs/AGENTS.md`

## 快速开始

```bash
git clone git@github.com:zitangkou/zhitianxia.git
cd zhitianxia/a_share_daily_review
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_morning.py
```

## 约定

子项目自管依赖；勿提交 `.venv`、`output/`、行情数据、Webhook 密钥。提交前缀示例：`feat(a_share): ...`
