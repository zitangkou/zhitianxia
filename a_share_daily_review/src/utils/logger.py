"""统一日志配置"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from .config import get_project_root


def setup_logger(
    name: str = "a_share_review",
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 文件
    if log_dir is None:
        log_dir = get_project_root() / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    fh = logging.FileHandler(log_dir / f"review_{today}.log", encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger
