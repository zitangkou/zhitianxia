"""时效过滤、URL 去重、基本清洗"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

logger = logging.getLogger("news.filter")


def _normalize_url(url: str) -> str:
    """去掉常见追踪参数，便于去重。"""
    try:
        p = urlparse(url)
        q = parse_qs(p.query)
        drop = {k for k in q if k.lower().startswith("utm_") or k.lower() in {
            "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "spm"
        }}
        for k in drop:
            q.pop(k, None)
        new_query = urlencode({k: v[0] if len(v) == 1 else v for k, v in q.items()}, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, "", new_query, ""))
    except Exception:
        return url.strip()


def _title_key(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\u4e00-\u9fff ]+", "", t)
    return t[:80]


def window_start(
    now: Optional[datetime] = None,
    cutoff_hour: int = 15,
    cutoff_minute: int = 0,
    tz_name: str = "Asia/Shanghai",
) -> datetime:
    """昨日 cutoff 时刻（上海时区 aware）。"""
    tz = ZoneInfo(tz_name)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)
    yesterday = (now.date() - timedelta(days=1))
    return datetime(
        yesterday.year, yesterday.month, yesterday.day,
        cutoff_hour, cutoff_minute, tzinfo=tz,
    )


def filter_items(
    items: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    1) 时间窗内（有发布时间的）
    2) 无时间的降权保留少量由 score 处理，这里仍保留但标记 missing_time
    3) URL / 标题去重
    """
    tw = cfg.get("time_window") or {}
    tz_name = tw.get("timezone", "Asia/Shanghai")
    tz = ZoneInfo(tz_name)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    start = window_start(
        now=now,
        cutoff_hour=int(tw.get("prev_day_cutoff_hour", 15)),
        cutoff_minute=int(tw.get("prev_day_cutoff_minute", 0)),
        tz_name=tz_name,
    )

    kept: List[Dict[str, Any]] = []
    seen_url: set = set()
    seen_title: set = set()

    for it in items:
        link = it.get("link") or ""
        title = it.get("title") or ""
        if not link or not title:
            continue

        norm = _normalize_url(link)
        tk = _title_key(title)
        if norm in seen_url or (tk and tk in seen_title):
            continue

        dt = it.get("published_dt")
        missing_time = dt is None
        in_window = True
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone_utc())
            dt_local = dt.astimezone(tz)
            it["published_dt"] = dt_local
            it["published"] = dt_local.isoformat()
            # 未来时间（坏数据）丢弃；早于窗口丢弃
            if dt_local > now + timedelta(hours=2):
                continue
            if dt_local < start:
                in_window = False
        it["missing_time"] = missing_time
        it["in_window"] = in_window
        # 无时间：暂留，打分时会降权；有时间但不在窗：丢弃
        if not missing_time and not in_window:
            continue

        seen_url.add(norm)
        if tk:
            seen_title.add(tk)
        it["link_normalized"] = norm
        kept.append(it)

    logger.info(
        "过滤后 %d 条（窗起 %s）",
        len(kept),
        start.strftime("%Y-%m-%d %H:%M"),
    )
    return kept


def timezone_utc():
    from datetime import timezone
    return timezone.utc
