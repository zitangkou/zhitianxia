#!/usr/bin/env python3
"""
交易日调度（阶段5）

默认（Asia/Shanghai）：
  07:30  盘前早报草稿
  15:45  收盘复盘草稿

不自动发帖；仅生成本地草稿，请打开审核台处理。

用法：
  python scripts/run_scheduler.py
  python scripts/run_scheduler.py --once morning
  python scripts/run_scheduler.py --once review
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger("scheduler")


def run_script(name: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / name)]
    if extra:
        cmd.extend(extra)
    logger.info("执行: %s", " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(ROOT))
    return p.returncode


def parse_args():
    p = argparse.ArgumentParser(description="早报/复盘调度")
    p.add_argument(
        "--once",
        choices=["morning", "review"],
        default=None,
        help="立即跑一次后退出",
    )
    p.add_argument("--with-morning-llm", action="store_true", help="早报也走 Ollama")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    sch = cfg.get("scheduler") or {}
    hour = int(sch.get("hour", 15))
    minute = int(sch.get("minute", 45))
    # 早报时间可写在 scheduler.morning_hour / morning_minute
    m_hour = int(sch.get("morning_hour", 7))
    m_minute = int(sch.get("morning_minute", 30))

    if args.once == "morning":
        extra = ["--llm"] if args.with_morning_llm else []
        return run_script("run_morning.py", extra)
    if args.once == "review":
        return run_script("run_daily.py", ["--no-llm"] if not (cfg.get("llm") or {}).get("enabled", True) else [])

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error("请安装 apscheduler: pip install apscheduler")
        return 1

    sched = BlockingScheduler(timezone=str(sch.get("timezone") or "Asia/Shanghai"))

    def job_morning():
        extra = ["--llm"] if args.with_morning_llm else []
        run_script("run_morning.py", extra)

    def job_review():
        run_script("run_daily.py")

    sched.add_job(job_morning, CronTrigger(hour=m_hour, minute=m_minute, day_of_week="mon-fri"))
    sched.add_job(job_review, CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri"))

    logger.info(
        "调度已启动: 早报 %02d:%02d / 复盘 %02d:%02d (周一至周五, %s)",
        m_hour, m_minute, hour, minute, sch.get("timezone", "Asia/Shanghai"),
    )
    logger.info("审核台: python -m src.review_ui.app  → http://127.0.0.1:8787")
    try:
        sched.start()
    except KeyboardInterrupt:
        logger.info("调度已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
