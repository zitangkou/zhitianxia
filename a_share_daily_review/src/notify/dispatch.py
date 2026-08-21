"""按配置分发消息（钉钉；可扩展飞书/企微）"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .dingtalk import send_dingtalk_markdown, send_dingtalk_text

logger = logging.getLogger("notify.dispatch")


def push_message(
    title: str,
    content: str,
    cfg: Optional[Dict[str, Any]] = None,
    *,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """
    根据 settings.notify 推送。
    force=True 时忽略 enabled（命令行 --notify 用）。
    """
    cfg = cfg or {}
    notify = dict(cfg.get("notify") or {})
    if not force and not notify.get("enabled", False):
        logger.info("notify.enabled=false，跳过推送")
        return []

    results: List[Dict[str, Any]] = []
    channels = notify.get("channels") or []

    # 兼容旧字段：仅 webhook_url
    if not channels and notify.get("webhook_url"):
        channels = [{
            "type": "dingtalk",
            "webhook": notify.get("webhook_url"),
            "secret": notify.get("secret", ""),
            "msgtype": notify.get("msgtype", "markdown"),
        }]

    if not channels:
        logger.warning("未配置 notify.channels / webhook_url")
        return []

    for ch in channels:
        if not ch.get("enabled", True):
            continue
        ctype = (ch.get("type") or "dingtalk").lower()
        try:
            if ctype == "dingtalk":
                webhook = ch.get("webhook") or ch.get("webhook_url") or ""
                if not webhook:
                    logger.warning("钉钉 channel 缺少 webhook")
                    continue
                secret = ch.get("secret") or ""
                msgtype = (ch.get("msgtype") or "markdown").lower()
                at_all = bool(ch.get("at_all", False))
                at_mobiles = ch.get("at_mobiles") or []
                if msgtype == "text":
                    # 钉钉 text 建议关键词在内容中（安全设置）
                    text = f"{title}\n\n{content}"
                    res = send_dingtalk_text(
                        text,
                        webhook=webhook,
                        secret=secret,
                        at_mobiles=at_mobiles,
                        at_all=at_all,
                    )
                else:
                    res = send_dingtalk_markdown(
                        title,
                        f"### {title}\n\n{content}",
                        webhook=webhook,
                        secret=secret,
                        at_mobiles=at_mobiles,
                        at_all=at_all,
                    )
                results.append({"channel": "dingtalk", "result": res})
            else:
                logger.warning("暂不支持的 channel 类型: %s", ctype)
        except Exception as e:
            logger.exception("推送失败 %s: %s", ctype, e)
            results.append({"channel": ctype, "error": str(e)})

    return results
