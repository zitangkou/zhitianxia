"""消息推送：钉钉等（仅通知草稿，不代替人工发帖）"""

from .dingtalk import send_dingtalk_markdown, send_dingtalk_text
from .dispatch import push_message

__all__ = ["push_message", "send_dingtalk_text", "send_dingtalk_markdown"]
