"""盘前早报流水线"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import yaml

from src.utils.config import get_project_root

from .draft import build_draft_payload, save_drafts
from .fetch import fetch_all_sources
from .filter import filter_items
from .score import score_items

logger = logging.getLogger("news.pipeline")


def load_news_config(path: Optional[Path] = None) -> Dict[str, Any]:
    root = get_project_root()
    path = path or (root / "config" / "news_sources.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_morning_pipeline(
    cfg: Optional[Dict[str, Any]] = None,
    news_cfg: Optional[Dict[str, Any]] = None,
    run_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行：拉源 → 过滤 → 打分 → 写草稿。
    返回 {payload, paths, stats}
    """
    root = get_project_root()
    news_cfg = news_cfg or load_news_config()
    tz_name = (news_cfg.get("time_window") or {}).get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    run_date = run_date or now.strftime("%Y-%m-%d")

    limits = news_cfg.get("limits") or {}
    timeout = float(limits.get("request_timeout_sec", 12))
    max_items = int(limits.get("max_fetch_per_source", 15))
    workers = int(limits.get("max_concurrent", 4))
    top_full = int(limits.get("top_n_full", 12))
    top_brief = int(limits.get("top_n_brief", 5))

    sources = news_cfg.get("sources") or []
    raw = fetch_all_sources(
        sources,
        timeout=timeout,
        max_items=max_items,
        max_workers=workers,
    )
    filtered = filter_items(raw, news_cfg, now=now)
    scored = score_items(filtered, news_cfg, now=now)

    payload = build_draft_payload(
        scored,
        run_date=run_date,
        generated_at=now.isoformat(),
        top_n_full=top_full,
        top_n_brief=top_brief,
    )

    # 输出目录：优先 settings.paths.output
    if cfg and cfg.get("paths", {}).get("output"):
        out_root = Path(cfg["paths"]["output"])
    else:
        out_root = root / "output"
    out_dir = out_root / run_date
    paths = save_drafts(payload, out_dir)

    stats = {
        "raw": len(raw),
        "filtered": len(filtered),
        "scored": len(scored),
        "full": len(payload.get("items_full") or []),
        "brief": len(payload.get("items_brief") or []),
        "output_dir": str(out_dir),
    }
    logger.info("早报流水线完成: %s", stats)
    return {"payload": payload, "paths": paths, "stats": stats}
