"""Token estimation — dùng cho threshold detection trước khi compact.

KHÔNG chính xác tuyệt đối — chỉ để biết khi nào gần chạm context window.
Để đếm chính xác, dùng token counting API của provider.
"""


def estimate_tokens(text: str) -> int:
    """Ước lượng tokens dựa trên số ký tự.

    - ASCII/English: ~4 chars/token
    - Code: ~3.5 chars/token
    - CJK (Vietnamese, Chinese, ...): ~1.5 chars/token

    Ở đây dùng heuristic đơn giản: chia cho 3.5 (trung bình giữa text và code).
    """
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Tổng tokens trong message history (normalized format của kagent)."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_tokens(str(block.get("text", block.get("content", ""))))
                else:
                    total += estimate_tokens(str(block))
        if "text" in msg and isinstance(msg["text"], str):
            total += estimate_tokens(msg["text"])
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                total += estimate_tokens(str(tc.get("args", {})))
                total += estimate_tokens(tc.get("name", ""))
    return total


CONTEXT_WINDOWS = {
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-1.5-pro": 2_000_000,
    "gemini-1.5-flash": 1_000_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-opus-4-20250514": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
}


def get_context_window(model: str, default: int = 128_000) -> int:
    """Trả về context window của model. Fallback = 128K."""
    return CONTEXT_WINDOWS.get(model, default)
