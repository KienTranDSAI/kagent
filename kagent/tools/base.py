from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolResult:
    """Result of a tool execution.

    Claude Code equivalent: ToolResultBlockParam

    `output`         — text preview cho UI + fallback cho text-only LLM
    `content_blocks` — multimodal payload (PDF/image). Khi != None,
                       provider sẽ wrap thành content block đúng API format.
                       Normalized format (Anthropic spec):
                         {"type": "document", "source": {"type": "base64",
                                                          "media_type": "application/pdf",
                                                          "data": "<b64>"}}
                         {"type": "image", "source": {"type": "base64",
                                                       "media_type": "image/jpeg",
                                                       "data": "<b64>"}}
                         {"type": "text", "text": "..."}
    """
    output: str                          # Main text output for LLM
    error: Optional[str] = None          # Error message if failed
    is_error: bool = False               # Whether execution failed
    metadata: dict = field(default_factory=dict)  # Extra data
    content_blocks: Optional[list[dict]] = None   # Multimodal blocks

    def is_multimodal(self) -> bool:
        return bool(self.content_blocks)

    def __str__(self) -> str:
        if self.is_error:
            return f"Error: {self.error}"
        return self.output


@dataclass
class ToolContext:
    """Execution context passed to every tool.

    Claude Code equivalent: ToolUseContext (much larger, ~20 fields)
    Start simple, expand as needed.
    """
    cwd: str  # Current working directory

    # Phase 6: permissions
    # permission_checker: PermissionChecker

    # Phase 8: conversation
    # abort_signal: asyncio.Event

    # Phase 9: concurrency
    # file_read_cache: dict


class Tool(ABC):
    """Base class for all tools.

    Claude Code equivalent: Tool type in Tool.ts
    Simplified from ~30 methods to essential ones.
    """
    name: str           # Unique identifier (e.g., "Bash")
    description: str    # Short description for LLM

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema for tool input.

        This schema is sent to the LLM API so it knows:
        - What parameters are available
        - Which are required
        - What types they accept
        - Description of each parameter

        Example:
        {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                }
            },
            "required": ["command"]
        }
        """
        ...

    @abstractmethod
    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            args: Parsed arguments matching input_schema
            context: Execution context (cwd, permissions, etc.)

        Returns:
            ToolResult with output text or error
        """
        ...

    def is_read_only(self) -> bool:
        """Does this tool only read data without side effects?

        Used for:
        - Permission system: read-only tools auto-allowed
        - Concurrency: read-only tools can run in parallel

        Default: False (safe assumption — assume writes)
        """
        return False

    def is_concurrency_safe(self) -> bool:
        """Can this tool safely run concurrently with other tools?

        Default: False (safe assumption — assume shared state)
        """
        return False

    def check_permissions(self, args: dict) -> Optional[str]:
        """Check if this tool call is allowed.

        Returns:
            None if allowed, or error message string if denied.
        Default: None (allow all — actual checking in Phase 6)
        """
        return None

    def bypasses_spinner(self) -> bool:
        """Whether tool execution takes over the terminal (interactive prompts).

        Tools returning True will skip the Rich Live spinner wrapper to avoid
        conflicting with libraries like prompt_toolkit/questionary that need
        direct terminal control.
        """
        return False

    def get_schema(self) -> dict:
        """Export schema for LLM API.

        Claude Code: toolToAPISchema() builds from name + prompt() + inputSchema.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
