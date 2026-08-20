"""RSS 拉取（feedparser + 低并发，适配 Mac mini）"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import feedparser
import requests

logger = logging.getLogger("news.fetch")


def _parse_entry_time(entry: dict) -> Optional[datetime]:
    """尽量解析条目时间，统一为 aware UTC 再由上层转上海。"""
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime(*st[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def fetch_one_source(
    source: Dict[str, Any],
    timeout: float = 12.0,
    max_items: int = 15,
) -> List[Dict[str, Any]]:
    """拉取单个 RSS，返回标准化条目列表。失败返回空列表。"""
    sid = source.get("id", "")
    url = source.get("url", "")
    if not url:
        return []

    headers = {
        "User-Agent": "a-share-daily-review/0.1 (local research; RSS reader)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        logger.warning("源失败 %s (%s): %s", sid, source.get("name"), e)
        return []

    items: List[Dict[str, Any]] = []
    for entry in (parsed.entries or [])[:max_items]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        # 去掉过长 html 噪声（简单截断）
        if len(summary) > 500:
            summary = summary[:500] + "…"
        published = _parse_entry_time(entry)
        items.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "published": published.isoformat() if published else None,
                "published_dt": published,
                "source_id": sid,
                "source_name": source.get("name", sid),
                "category": source.get("category", "other"),
                "region": source.get("region", "overseas"),
            }
        )
    logger.info("源 %s 获取 %d 条", sid, len(items))
    return items


def fetch_all_sources(
    sources: List[Dict[str, Any]],
    timeout: float = 12.0,
    max_items: int = 15,
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """并发拉取所有 enabled 源。"""
    enabled = [s for s in sources if s.get("enabled", True)]
    if not enabled:
        logger.warning("没有启用的资讯源")
        return []

    all_items: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {
            ex.submit(fetch_one_source, s, timeout, max_items): s for s in enabled
        }
        for fut in as_completed(futs):
            try:
                all_items.extend(fut.result())
            except Exception as e:
                logger.warning("并发拉取异常: %s", e)
    logger.info("合计拉取 %d 条（去重前）", len(all_items))
    return all_items
