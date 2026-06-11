"""Command framework — slash commands in REPL.

Claude Code equivalent: src/commands.ts + src/commands/*.ts
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandContext:
    """State shared giữa REPL và command handlers.

    Mutation rules:
    - `messages` có thể mutate (append, clear)
    - `session_id_ref[0]` có thể gán lại (list-of-1 trick cho pass-by-ref)
    - `cost_tracker` có thể tăng counter
    - provider / registry / model / memory là read-only references
    """
    messages: list[dict]
    session_id_ref: list[str]
    cost_tracker: object        # CostTracker
    provider: object            # LLMProvider
    tool_registry: object       # ToolRegistry
    model: str
    provider_name: str
    memory: object              # MemoryManager
    permission_checker: object = None  # PermissionChecker (cho /plan)
    context_tracker: object = None     # ContextTracker — real token count của main loop


class Command(ABC):
    name: str
    description: str
    usage: str = ""

    @abstractmethod
    async def execute(self, args: str, ctx: CommandContext) -> None:
        """Thực thi command. Tự in ra console, tự mutate ctx nếu cần."""
        ...


class CommandRegistry:
    """Registry cho slash commands."""

    def __init__(self):
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def get(self, name: str) -> Optional[Command]:
        return self._commands.get(name)

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def __contains__(self, name: str) -> bool:
        return name in self._commands


def parse_slash(input_str: str) -> tuple[str, str] | None:
    """Parse slash command. Return (name, args) or None nếu không phải slash."""
    if not input_str.startswith("/"):
        return None
    body = input_str[1:].strip()
    if not body:
        return None
    parts = body.split(maxsplit=1)
    name = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return name, args
