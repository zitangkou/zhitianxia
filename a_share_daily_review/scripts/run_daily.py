#!/usr/bin/env python3
"""
方案一主入口：每日自动复盘流水线

用法：
  cd a_share_daily_review
  python scripts/run_daily.py
  python scripts/run_daily.py --date 2026-08-19
  python scripts/run_daily.py --force
  python scripts/run_daily.py --no-llm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.review import ReviewEngine
from src.content.review_draft import build_review_draft
from src.data.fetcher import DataFetcher
from src.data.storage import DataStorage
from src.utils.calendar import get_latest_trading_day, is_trading_day
from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger("main")


def parse_args():
    parser = argparse.ArgumentParser(description="A股每日自动复盘 - 方案一")
    parser.add_argument("--date", type=str, default=None, help="指定交易日 YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="强制运行（忽略交易日检查）")
    parser.add_argument("--no-save", action="store_true", help="只拉取不落盘")
    parser.add_argument("--no-llm", action="store_true", help="跳过 Ollama 润色")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据（离线调试）")
    return parser.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    logger.info("=" * 60)
    logger.info(f"启动 {cfg['project']['name']} v{cfg['project']['version']}")
    logger.info("=" * 60)

    if args.date:
        trade_date = args.date[:10]
    else:
        trade_date = get_latest_trading_day().strftime("%Y-%m-%d")

    logger.info(f"目标交易日: {trade_date}")

    if not args.force and not is_trading_day(trade_date):
        logger.warning(f"{trade_date} 非交易日，退出。如需强制请加 --force")
        return 0

    fetcher = DataFetcher(cfg)
    storage = DataStorage(cfg)

    try:
        data = fetcher.run_daily_fetch(trade_date)

        if not data.get("is_trading_day") and not args.force:
            logger.info("非交易日，结束")
            return 0

        if not args.no_save:
            storage.save_daily_data(data)
        else:
            logger.info("已跳过落盘 (--no-save)")

        engine = ReviewEngine(cfg)
        review = engine.build(data)
        if not args.no_save:
            storage.save_review_summary(
                trade_date=trade_date,
                summary=review.to_dict(),
                llm_text=review.summary_text,
            )

        out_dir = Path(cfg["paths"]["output"]) / trade_date
        draft = build_review_draft(
            review,
            trade_date=trade_date,
            out_dir=out_dir,
            cfg=cfg,
            use_llm=not args.no_llm,
        )

        print("\n" + "=" * 50)
        print(draft.get("llm_text") or review.summary_text)
        print("=" * 50)
        if draft.get("charts"):
            print("图表:", ", ".join(draft["charts"]))
        print(f"审核草稿: {out_dir / 'review_draft.json'}")
        print("状态: pending_review（请打开审核台人工发布，勿自动发帖）")
        print("=" * 50 + "\n")

        logger.info("复盘流水线完成（含草稿/图表）")
        return 0

    except Exception as e:
        logger.exception(f"运行失败: {e}")
        try:
            storage.log_run(trade_date, status="error", message=str(e))
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
