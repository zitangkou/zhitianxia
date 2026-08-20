# 知天下（zhitianxia）

个人实验与工具 monorepo：同一仓库下多个独立小模块，各自目录、各自依赖，统一备份与版本管理。

**远程**：`git@github.com:zitangkou/zhitianxia.git`

## 模块一览

| 目录 | 说明 |
|------|------|
| [a_share_daily_review](./a_share_daily_review/) | A 股盘前早报 + 收盘复盘草稿；本机审核后人工发布（不自动发帖） |

后续新模块在根目录并列新建文件夹，并在本表追加一行即可。

## 克隆

```bash
git clone git@github.com:zitangkou/zhitianxia.git
cd zhitianxia
```

## 约定

- 每个子项目自带 `README` / 依赖文件，**不在根目录强行统一 requirements**
- 勿提交：虚拟环境、行情数据、当日草稿输出、密钥
- 提交说明尽量带模块前缀，例如：`feat(a_share): morning rss pipeline`

## 根目录结构（目标）

```text
zhitianxia/
├── README.md
├── .gitignore
├── a_share_daily_review/
└── （其它模块…）
```
