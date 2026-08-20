"""将 ReviewEngine 结果打包为审核用 review_draft.json"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.content.charts import make_review_charts
from src.content.llm import polish_review
from src.news.draft import DISCLAIMER_SHORT

logger = logging.getLogger("content.review_draft")


def build_review_draft(
    review: Any,
    *,
    trade_date: str,
    out_dir: Path,
    cfg: Dict[str, Any],
    use_llm: bool = True,
) -> Dict[str, Any]:
    """
    review: ReviewResult 或 duck-typed 对象（summary_text, surprise_points, ...）
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_text = getattr(review, "summary_text", None) or ""
    if hasattr(review, "to_dict"):
        raw = review.to_dict()
    else:
        raw = {}

    # 供图表
    chart_input = {
        "limit_up_count": raw.get("limit_up_count") or getattr(review, "limit_up_count", 0),
        "limit_down_count": raw.get("limit_down_count") or getattr(review, "limit_down_count", 0),
        "zhaban_count": raw.get("zhaban_count") or getattr(review, "zhaban_count", 0),
        "board_ladder": raw.get("board_ladder") or getattr(review, "board_ladder", {}) or {},
    }
    charts = make_review_charts(chart_input, out_dir)

    llm_text = None
    llm_cfg = cfg.get("llm") or {}
    if use_llm and llm_cfg.get("enabled", True) and llm_cfg.get("provider") == "ollama":
        extra = {
            "surprise_points": raw.get("surprise_points") or getattr(review, "surprise_points", []),
            "max_board": raw.get("max_board_height") or raw.get("max_board"),
        }
        llm_text = polish_review(summary_text, extra=extra, llm_cfg=llm_cfg)

    final_text = llm_text or summary_text
    if DISCLAIMER_SHORT not in final_text:
        final_text = final_text.rstrip() + "\n\n⚠️ " + DISCLAIMER_SHORT

    payload: Dict[str, Any] = {
        "type": "daily_review",
        "run_date": trade_date,
        "generated_at": datetime.now().isoformat(),
        "status": "pending_review",
        "auto_publish": False,
        "disclaimer_short": DISCLAIMER_SHORT,
        "summary_text": summary_text,
        "llm_text": final_text,
        "used_llm": bool(llm_text),
        "surprise_points": raw.get("surprise_points") or getattr(review, "surprise_points", []),
        "charts": charts,
        "stats": chart_input,
        "meta": {"note": "仅草稿，须人工审核后发布；系统不自动发帖"},
    }

    path = out_dir / "review_draft.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    (out_dir / "review_draft.md").write_text(final_text, encoding="utf-8")
    (out_dir / "review_summary.txt").write_text(summary_text, encoding="utf-8")
    logger.info("复盘草稿已写入 %s", path)
    return payload
