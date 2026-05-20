"""STS2 auxiliary LLM calls (correct call_llm signature)."""

from __future__ import annotations

from typing import Any, List, Optional


def sts2_call_llm(
    messages: List[dict],
    *,
    max_tokens: int = 500,
    temperature: float = 0.3,
) -> str:
    from agent.auxiliary_client import call_llm

    out = call_llm(
        "sts2",
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if out is None:
        return ""
    content = getattr(out, "choices", None)
    if content:
        try:
            return (content[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError):
            pass
    return str(out).strip()
