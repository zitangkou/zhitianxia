"""生成帖子样式草稿（完整版 / 精简版）+ JSON，供人工审核"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("news.draft")

DISCLAIMER_SHORT = (
    "内容来自公开信息与行情数据整理，仅供参考，不构成投资建议。"
    "市场有风险，决策请独立判断。"
)


def _md_escape_title(t: str) -> str:
    return t.replace("\n", " ").strip()


def build_draft_payload(
    items: List[Dict[str, Any]],
    *,
    run_date: str,
    generated_at: str,
    top_n_full: int = 12,
    top_n_brief: int = 5,
) -> Dict[str, Any]:
    full_items = items[:top_n_full]
    brief_items = items[:top_n_brief]

    def pack(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for i, r in enumerate(rows, 1):
            out.append({
                "index": i,
                "selected": True,  # 审核页可改为 False
                "title": r.get("title"),
                "link": r.get("link"),
                "source_name": r.get("source_name"),
                "source_id": r.get("source_id"),
                "category": r.get("category"),
                "region": r.get("region"),
                "published": r.get("published"),
                "score": r.get("score"),
                "impact_hits": r.get("impact_hits") or [],
                "summary": (r.get("summary") or "")[:300],
            })
        return out

    return {
        "type": "morning_brief",
        "run_date": run_date,
        "generated_at": generated_at,
        "status": "pending_review",
        "auto_publish": False,
        "disclaimer_short": DISCLAIMER_SHORT,
        "items_full": pack(full_items),
        "items_brief": pack(brief_items),
        "meta": {
            "total_scored": len(items),
            "top_n_full": top_n_full,
            "top_n_brief": top_n_brief,
            "note": "仅草稿，须人工审核后发布；系统不自动发帖",
        },
    }


def render_markdown(payload: Dict[str, Any], mode: str = "full") -> str:
    """mode: full | brief"""
    run_date = payload.get("run_date", "")
    try:
        mmdd = datetime.strptime(run_date, "%Y-%m-%d").strftime("%m-%d")
    except Exception:
        mmdd = run_date

    if mode == "brief":
        rows = [x for x in payload.get("items_brief") or [] if x.get("selected", True)]
        lines = [f"【盘前】{mmdd} 隔夜精选", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. {_md_escape_title(r.get('title') or '')}")
        lines.append("")
        lines.append(f"⚠️ {payload.get('disclaimer_short') or DISCLAIMER_SHORT}")
        return "\n".join(lines)

    rows = [x for x in payload.get("items_full") or [] if x.get("selected", True)]
    lines = [
        f"【盘前速览】{mmdd} · 隔夜海外",
        "",
        "🌍 隔夜必须知道",
    ]
    for i, r in enumerate(rows, 1):
        title = _md_escape_title(r.get("title") or "")
        src = r.get("source_name") or ""
        lines.append(f"{i}. {title}")
        if src:
            lines.append(f"   · 来源：{src}")
    lines.append("")
    lines.append("👀 今日观察")
    lines.append("· （人工填写：0～2 条保守观察；无则删除本段）")
    lines.append("")
    lines.append("————————")
    lines.append("来源可核对（发布时可删减）")
    for i, r in enumerate(rows, 1):
        link = r.get("link") or ""
        src = r.get("source_name") or ""
        title = _md_escape_title(r.get("title") or "")
        lines.append(f"{i}. {title} — {src}")
        if link:
            lines.append(f"   {link}")
    lines.append("")
    lines.append(f"⚠️ {payload.get('disclaimer_short') or DISCLAIMER_SHORT}")
    return "\n".join(lines)


def save_drafts(
    payload: Dict[str, Any],
    output_dir: Path,
) -> Dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "morning_draft.json"
    full_md = output_dir / "morning_draft_full.md"
    brief_md = output_dir / "morning_draft_brief.md"

    # JSON：去掉不可序列化残留
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    full_text = render_markdown(payload, mode="full")
    brief_text = render_markdown(payload, mode="brief")
    full_md.write_text(full_text, encoding="utf-8")
    brief_md.write_text(brief_text, encoding="utf-8")

    logger.info("草稿已写入 %s", output_dir)
    return {"json": json_path, "full_md": full_md, "brief_md": brief_md}
