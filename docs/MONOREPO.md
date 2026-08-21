# Monorepo 说明

- 一个 Git 仓库，多个并列模块目录。
- 当前主模块：`a_share_daily_review/`。
- 在仓库根 `git push`；只改某模块时 `git add 模块名/`。
- 不要在子目录再次 `git init`。
- 根 `.gitignore` 忽略各模块 output/data/logs/.venv 等。
