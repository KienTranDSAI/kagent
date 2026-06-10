"""Conversation compaction — 2 tiers:

Tier 1: micro_compact (free) — replace tool output cũ bằng placeholder
Tier 3: compact_conversation (API call) — LLM summarize messages cũ

Claude Code equivalent:
  - microCompact.ts (tier 1)
  - compact.ts (tier 3)
"""

from kagent.providers.base import LLMProvider


MC_CLEARED = "[Old tool result content cleared]"


COMPACT_PROMPT = """Summarize this conversation concisely, preserving:

1. **User's primary request and intent** — what they're trying to accomplish
2. **Key technical details** — specific files, functions, errors mentioned
3. **Files read or modified** — include file paths and what was done
4. **Errors encountered and how they were resolved**
5. **All user instructions and preferences** — CRITICAL: don't lose these
6. **Current state of work** — what's done, what's in progress
7. **Next steps** — if the user indicated what to do next

Be concise but don't lose important context. Focus on facts, not conversation flow."""


def micro_compact(messages: list[dict], keep_last_n: int = 10, min_len: int = 500) -> list[dict]:
    """Tier 1 — FREE. Thay tool results cũ bằng placeholder.

    Args:
        messages: Message history
        keep_last_n: Số messages gần nhất giữ nguyên
        min_len: Chỉ clear tool output dài hơn ngưỡng này

    Returns:
        New list (không mutate input)
    """
    if len(messages) <= keep_last_n:
        return list(messages)

    cutoff = len(messages) - keep_last_n
    result = []
    cleared_count = 0

    for i, msg in enumerate(messages):
        if i < cutoff and msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > min_len:
                new_msg = dict(msg)
                new_msg["content"] = MC_CLEARED
                result.append(new_msg)
                cleared_count += 1
                continue
        result.append(msg)

    return result


async def compact_conversation(
    messages: list[dict],
    provider: LLMProvider,
    keep_last_n: int = 10,
) -> list[dict]:
    """Tier 3 — LLM summarize messages cũ, giữ lại N gần nhất.

    Costs tokens (1 API call). Nhưng giảm context dramatically.
    """
    if len(messages) <= keep_last_n:
        return list(messages)

    old_messages = messages[:-keep_last_n]
    recent_messages = messages[-keep_last_n:]

    conversation_text = _format_for_summary(old_messages)

    summary_response = await provider.chat(
        messages=[{
            "role": "user",
            "content": f"Summarize this conversation:\n\n{conversation_text}",
        }],
        system_prompt=COMPACT_PROMPT,
    )

    summary = (summary_response.text or "").strip() or "[Summary unavailable]"

    return [
        {"role": "user", "content": f"[Previous conversation summary]\n{summary}"},
        {"role": "assistant", "content": "Understood. I have context from our previous conversation. How can I continue helping?"},
        *recent_messages,
    ]


def _format_for_summary(messages: list[dict]) -> str:
    """Format messages thành plain text để LLM đọc."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(b) for b in content)
        if not isinstance(content, str):
            content = str(content)

        extra = ""
        if msg.get("text"):
            extra += f" TEXT={msg['text']}"
        if msg.get("tool_calls"):
            names = [tc.get("name", "?") for tc in msg["tool_calls"]]
            extra += f" TOOL_CALLS={names}"

        full = (content + extra).strip()
        if len(full) > 2000:
            full = full[:2000] + "..."
        parts.append(f"[{role}]: {full}")
    return "\n\n".join(parts)
