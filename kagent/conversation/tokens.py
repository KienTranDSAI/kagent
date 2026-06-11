"""Token estimation + real token tracking — cho threshold detection trước khi compact.

Heuristic (chars/3.5) KHÔNG chính xác tuyệt đối — chỉ là fallback.
Số chính xác lấy từ usage API của lần gọi LLM gần nhất (ContextTracker).
"""

from dataclasses import dataclass


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


@dataclass
class ContextTracker:
    """Context size THẬT từ usage API của lần gọi LLM gần nhất (main loop only).

    input_tokens của 1 response = toàn bộ context model vừa đọc (system prompt
    + history + tool schemas) — chính model đếm, chính xác tuyệt đối, miễn phí.
    Cộng output của lần đó ≈ context hiện tại (trước khi append tool results mới).

    Claude Code equivalent: tokenUsage trong services/compact/autoCompact.ts.

    KHÔNG dùng chung với CostTracker: /commit //review cũng add vào cost
    (LLM call phụ) sẽ làm bẩn số context của main conversation.

    Sau compact/clear/resume thì số này stale → reset() để engine fallback
    về heuristic cho tới lần gọi API kế tiếp.
    """
    last_input_tokens: int = 0
    last_output_tokens: int = 0

    def update(self, input_tokens: int, output_tokens: int) -> None:
        self.last_input_tokens = input_tokens
        self.last_output_tokens = output_tokens

    @property
    def tokens(self) -> int:
        return self.last_input_tokens + self.last_output_tokens

    def reset(self) -> None:
        self.last_input_tokens = 0
        self.last_output_tokens = 0


def resolve_context_tokens(
    messages: list[dict],
    tracker: ContextTracker | None,
) -> tuple[int, str]:
    """(tokens, source) — ưu tiên số thật từ API, fallback heuristic.

    source: "api" | "heuristic" — để UI hiển thị độ tin cậy của con số.
    """
    if tracker is not None and tracker.tokens > 0:
        return tracker.tokens, "api"
    return estimate_messages_tokens(messages), "heuristic"


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


# Fallback theo prefix khi model không có trong bảng exact
# (vd "gemini-3.1-flash", "claude-fable-5", "gpt-5.2"). Match từ trên xuống.
PREFIX_CONTEXT_WINDOWS = [
    ("gemini-1.5-pro", 2_000_000),
    ("gemini", 1_000_000),
    ("claude", 200_000),
    ("gpt-5", 400_000),
    ("gpt-4.1", 1_000_000),
    ("gpt-4o", 128_000),
    ("qwen3", 262_144),
]


def get_context_window(model: str, default: int = 128_000) -> int:
    """Context window của model: exact match → prefix match → default 128K."""
    if model in CONTEXT_WINDOWS:
        return CONTEXT_WINDOWS[model]
    m = model.lower()
    for prefix, window in PREFIX_CONTEXT_WINDOWS:
        if m.startswith(prefix):
            return window
    return default
