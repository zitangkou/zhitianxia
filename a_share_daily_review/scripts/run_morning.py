#!/usr/bin/env python3
"""
盘前综合帖 · 早报草稿流水线

用法：
  python scripts/run_morning.py
  python scripts/run_morning.py --date 2026-08-21
  python scripts/run_morning.py --llm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.content.llm import polish_morning
from src.news.draft import DISCLAIMER_SHORT
from src.news.pipeline import run_morning_pipeline
from src.utils.config import load_config
from src.utils.logger import setup_logger

logger = setup_logger("morning")


def parse_args():
    p = argparse.ArgumentParser(description="盘前早报草稿（人工审核后发布）")
    p.add_argument("--date", type=str, default=None, help="业务日期 YYYY-MM-DD")
    p.add_argument("--llm", action="store_true", help="启用 Ollama 中文润色（默认关，省内存）")
    p.add_argument("--notify", action="store_true", help="推送到钉钉等（读 config notify）")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config()
    logger.info("=" * 60)
    logger.info("盘前早报草稿流水线启动（不自动发帖）")
    logger.info("=" * 60)

    try:
        result = run_morning_pipeline(cfg=cfg, run_date=args.date)
        stats = result["stats"]
        paths = result["paths"]
        payload = result["payload"]
        out_dir = Path(stats["output_dir"])

        if args.llm:
            llm_cfg = dict(cfg.get("llm") or {})
            llm_cfg["enabled"] = True
            items = [x for x in (payload.get("items_full") or []) if x.get("selected", True)]
            polished = polish_morning(
                items,
                run_date=payload.get("run_date") or "",
                disclaimer=payload.get("disclaimer_short") or DISCLAIMER_SHORT,
                llm_cfg=llm_cfg,
            )
            if polished:
                payload["llm_text"] = polished
                payload["used_llm"] = True
                (out_dir / "morning_draft_llm.md").write_text(polished, encoding="utf-8")
                with open(paths["json"], "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
                logger.info("已生成 morning_draft_llm.md")
            else:
                logger.warning("LLM 润色失败，保留模板草稿")

        print("\n" + "=" * 50)
        print(f"日期: {payload.get('run_date')}")
        print(f"拉取 {stats['raw']} → 过滤 {stats['filtered']} → 成稿 full={stats['full']} brief={stats['brief']}")
        print(f"输出目录: {stats['output_dir']}")
        print(f"  - {paths['full_md'].name}")
        print(f"  - {paths['brief_md'].name}")
        print(f"  - {paths['json'].name}")
        if args.llm and payload.get("used_llm"):
            print("  - morning_draft_llm.md")
        print("状态: pending_review（请人工审核后发布）")
        print("=" * 50)

        brief_text = paths["brief_md"].read_text(encoding="utf-8")
        print("\n--- 精简版预览 ---\n")
        print(brief_text)
        print("\n------------------\n")

        # 可选：推送到钉钉等
        if args.notify or (cfg.get("notify") or {}).get("enabled"):
            try:
                from src.notify import push_message
                body = brief_text
                if payload.get("llm_text"):
                    body = payload["llm_text"]
                title = f"盘前早报 {payload.get('run_date', '')}"
                push_message(title, body, cfg, force=bool(args.notify))
                print("已尝试消息推送（钉钉等）")
            except Exception as e:
                logger.warning("消息推送失败: %s", e)

        return 0
    except Exception as e:
        logger.exception("早报流水线失败: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
