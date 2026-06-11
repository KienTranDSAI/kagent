from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from kagent.tools.base import ToolResult


@dataclass
class ToolCall:
    """Represents a tool call from the LLM.
    Normalized across all providers.

    Provider-specific ID formats:
    - Anthropic: "toolu_xxx" (tool_use block id)
    - Gemini: we generate "call_{name}" (no native ID)
    - OpenAI: "call_xxx" (tool_calls array id)

    provider_metadata: opaque per-provider data the engine must echo back
    on the next turn (e.g. Gemini 3 thought_signature bytes).
    """
    id: str
    name: str
    args: dict
    provider_metadata: dict = field(default_factory=dict)


@dataclass
class Usage:
    """Token usage from a single API call."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider.

    Mọi provider trả về format khác nhau, nhưng engine.py
    chỉ thấy object này — không cần biết provider nào.
    """
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    raw: Any = None

    def is_text_only(self) -> bool:
        """No tool calls — just text response."""
        return len(self.tool_calls) == 0


class LLMProvider(ABC):
    """Abstract base for all LLM providers.

    Mỗi provider implement class này để normalize API format
    về LLMResponse thống nhất.

    Provider formats:
    ┌─────────────┬─────────────────────┬──────────────────────┐
    │ Provider    │ Tool call format    │ Tool result format   │
    ├─────────────┼─────────────────────┼──────────────────────┤
    │ Anthropic   │ tool_use block      │ tool_result block    │
    │ Gemini      │ functionCall        │ functionResponse     │
    │ OpenAI      │ tool_calls array    │ tool role message    │
    └─────────────┴─────────────────────┴──────────────────────┘
    """

    # Capability flags — default False. Multimodal-capable providers opt in.
    @property
    def supports_pdf(self) -> bool:
        """Provider has native PDF/document content type."""
        return False

    async def list_models(self) -> list[str]:
        """Tên các model khả dụng từ API (cho /model picker).

        Default: rỗng = provider không hỗ trợ liệt kê.
        """
        return []

    @property
    def supports_image(self) -> bool:
        """Provider can receive inline image content (base64)."""
        return False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Single-turn LLM call. Returns complete response."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Streaming LLM call. Yields text chunks.
        Full streaming + tool_use handling is Phase 7."""
        ...

    @abstractmethod
    def format_messages(self, messages: list[dict]) -> Any:
        """Convert normalized messages to provider-specific format."""
        ...

    @abstractmethod
    def format_tool_result(
        self,
        tool_call: ToolCall,
        result: Union["ToolResult", str],
    ) -> Union[dict, list[dict]]:
        """Format a tool execution result for sending back to the LLM.

        - text-only result → single dict message
        - multimodal result (content_blocks set) → list of 2 messages
          [tool_role_text, user_role_with_content_blocks]
        Accepts `str` for backward-compat (DENY/error paths in engine).
        """
        ...

    @abstractmethod
    def format_tools(self, tools: list[dict]) -> Any:
        """Convert tool schemas to provider-specific format."""
        ... ##Deploy here to sum up input schema of tools to pass into gemini

