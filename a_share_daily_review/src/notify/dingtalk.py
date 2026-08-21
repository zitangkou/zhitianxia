"""钉钉自定义机器人 Webhook"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("notify.dingtalk")

# 钉钉单条文本建议不超过约 20000 字节；这里保守截断
MAX_CHARS = 3500


def _sign_url(webhook: str, secret: str) -> str:
    """加签机器人：timestamp + secret → 拼到 URL。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n…(已截断，完整见本地草稿)"


def send_dingtalk_text(
    content: str,
    *,
    webhook: str,
    secret: str = "",
    at_mobiles: Optional[list] = None,
    at_all: bool = False,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    url = _sign_url(webhook, secret) if secret else webhook
    body = {
        "msgtype": "text",
        "text": {"content": _truncate(content)},
        "at": {
            "atMobiles": at_mobiles or [],
            "isAtAll": at_all,
        },
    }
    r = requests.post(url, json=body, timeout=timeout)
    data = r.json() if r.content else {}
    if data.get("errcode", 0) != 0:
        logger.warning("钉钉 text 失败: %s", data)
    else:
        logger.info("钉钉 text 已发送")
    return data


def send_dingtalk_markdown(
    title: str,
    text: str,
    *,
    webhook: str,
    secret: str = "",
    at_mobiles: Optional[list] = None,
    at_all: bool = False,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    url = _sign_url(webhook, secret) if secret else webhook
    # 钉钉 markdown 里可 @
    md = _truncate(text)
    if at_all:
        md = md + "\n\n@all"
    body = {
        "msgtype": "markdown",
        "markdown": {
            "title": title[:64] or "通知",
            "text": md,
        },
        "at": {
            "atMobiles": at_mobiles or [],
            "isAtAll": at_all,
        },
    }
    r = requests.post(url, json=body, timeout=timeout)
    data = r.json() if r.content else {}
    if data.get("errcode", 0) != 0:
        logger.warning("钉钉 markdown 失败: %s", data)
    else:
        logger.info("钉钉 markdown 已发送")
    return data
