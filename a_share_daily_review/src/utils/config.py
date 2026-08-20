"""配置加载工具"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def get_project_root() -> Path:
    """返回项目根目录（a_share_daily_review/）"""
    # 本文件位于 src/utils/config.py
    return Path(__file__).resolve().parents[2]


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """加载 settings.yaml"""
    root = get_project_root()
    if config_path is None:
        config_path = root / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 把相对路径转成绝对路径，方便后续使用
    paths = cfg.get("paths", {})
    for key, rel in list(paths.items()):
        if key == "root":
            paths[key] = str(root)
        else:
            # 支持 {date} 占位，后续再 format
            paths[key] = str(root / rel)

    cfg["paths"] = paths
    return cfg
