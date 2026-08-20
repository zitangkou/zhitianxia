"""海外优先 + 冲击力 + 时效打分"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("news.score")


def score_items(
    items: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    sc = cfg.get("scoring") or {}
    cat_w = sc.get("category_weight") or {}
    keywords = sc.get("impact_keywords") or []
    half_life = float(sc.get("recency_half_life_hours", 18) or 18)

    tz = ZoneInfo((cfg.get("time_window") or {}).get("timezone", "Asia/Shanghai"))
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    scored: List[Dict[str, Any]] = []
    for it in items:
        cat = it.get("category") or "other"
        base = float(cat_w.get(cat, 0.5))

        # 区域：国内再乘系数（国外优先）
        region = it.get("region") or "overseas"
        region_mul = 1.0 if region == "overseas" else 0.7

        title = it.get("title") or ""
        title_l = title.lower()
        impact = 0.0
        hits = []
        for kw in keywords:
            word = str(kw.get("word", ""))
            if not word:
                continue
            if word.lower() in title_l or word in title:
                impact += float(kw.get("score", 1.0))
                hits.append(word)

        # 时效衰减
        recency = 0.35  # 缺时间
        dt = it.get("published_dt")
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            hours = max(0.0, (now - dt.astimezone(tz)).total_seconds() / 3600.0)
            # 半衰期衰减，最新接近 1.0
            recency = 0.5 ** (hours / half_life)
            recency = max(0.15, min(1.0, recency))
        elif it.get("missing_time"):
            recency = 0.25

        # 综合分
        score = base * region_mul * (1.0 + impact * 0.15) * (0.4 + 0.6 * recency)
        # 略微抬升有冲击词的条目
        if impact >= 2.5:
            score *= 1.1

        it = dict(it)
        it["score"] = round(score, 4)
        it["impact_hits"] = hits
        it["recency"] = round(recency, 4)
        # published_dt 不可 JSON 序列化
        if "published_dt" in it:
            it["published_dt"] = None
        scored.append(it)

    scored.sort(key=lambda x: (-x.get("score", 0), x.get("title", "")))
    logger.info("打分完成，Top1=%.3f %s", scored[0]["score"] if scored else 0, scored[0]["title"][:40] if scored else "")
    return scored
