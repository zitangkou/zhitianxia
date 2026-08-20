"""本地 Ollama 润色（可选；失败则回落模板原文）"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("content.llm")

MORNING_SYSTEM = """你是财经信息整理助手。根据给定的「已筛选新闻列表」生成中文盘前短讯。
硬性规则：
1. 不得新增列表中没有的数字、公司名、结论或来源。
2. 不得给出买卖建议或收益承诺。
3. 以海外/宏观为主，语气克制。
4. 输出纯文本，结构如下：
【盘前速览】日期 · 隔夜海外
🌍 隔夜必须知道
1. …
（保留原有事实，可润色中文表达）
⚠️ 文末保留免责声明原句。
"""

REVIEW_SYSTEM = """你是A股盘面复盘写手。根据给定的结构化摘要生成小红书风格短复盘。
硬性规则：
1. 只能使用输入中的事实与数字，禁止编造。
2. 禁止荐股、买卖点、收益承诺。
3. 把「最反常的一点」放在最前。
4. 文末加：内容来自公开信息与行情数据整理，仅供参考，不构成投资建议。市场有风险，决策请独立判断。
"""


def ollama_chat(
    prompt: str,
    *,
    system: str,
    base_url: str = "http://localhost:11434",
    model: str = "qwen2.5:7b",
    temperature: float = 0.4,
    timeout: float = 120.0,
) -> Optional[str]:
    url = base_url.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        msg = (data.get("message") or {}).get("content") or data.get("response")
        return (msg or "").strip() or None
    except Exception as e:
        logger.warning("Ollama 调用失败: %s", e)
        return None


def polish_morning(
    items: List[Dict[str, Any]],
    *,
    run_date: str,
    disclaimer: str,
    llm_cfg: Dict[str, Any],
) -> Optional[str]:
    if not llm_cfg.get("enabled", True):
        return None
    lines = [f"日期: {run_date}", "新闻列表:"]
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. 标题={it.get('title')} | 来源={it.get('source_name')} | 链接={it.get('link')}"
        )
    lines.append(f"免责声明原句: {disclaimer}")
    prompt = "\n".join(lines)
    return ollama_chat(
        prompt,
        system=MORNING_SYSTEM,
        base_url=str(llm_cfg.get("base_url", "http://localhost:11434")),
        model=str(llm_cfg.get("model", "qwen2.5:7b")),
        temperature=float(llm_cfg.get("temperature", 0.4)),
    )


def polish_review(
    summary_text: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
    llm_cfg: Dict[str, Any],
) -> Optional[str]:
    if not llm_cfg.get("enabled", True):
        return None
    prompt = "结构化摘要如下：\n" + summary_text
    if extra:
        prompt += "\n\n附加JSON要点:\n" + json.dumps(extra, ensure_ascii=False, default=str)[:3000]
    return ollama_chat(
        prompt,
        system=REVIEW_SYSTEM,
        base_url=str(llm_cfg.get("base_url", "http://localhost:11434")),
        model=str(llm_cfg.get("model", "qwen2.5:7b")),
        temperature=float(llm_cfg.get("temperature", 0.5)),
    )
