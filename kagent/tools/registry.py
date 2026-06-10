from kagent.tools.base import Tool


class ToolRegistry:
    """Registry of available tools.

    Claude Code equivalent: getAllBaseTools() + getTools() in tools.ts
    Simplified: no feature flags, no deny rules filtering (Phase 6).
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if name already exists."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get tool by name. Returns None if not found."""
        return self._tools.get(name)

    def all_tools(self) -> list[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_schemas_for_llm(self) -> list[dict]:
        """Convert all tools to the format LLM APIs expect.

        Returns list of:
        {
            "name": "Bash",
            "description": "Execute a shell command...",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Note: Exact format varies per provider.
        Anthropic uses this format directly.
        Gemini wraps in function_declarations.
        OpenAI wraps in {type: "function", function: {...}}.
        The provider adapter handles conversion.
        """
        return [tool.get_schema() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
