"""TodoWrite tool — agent tự quản lý task list trong session.

Claude Code equivalent: src/tools/TodoWriteTool/TodoWriteTool.ts

Design:
- Overwrite semantics: mỗi call LLM pass full list, không patch từng item.
- All completed → auto-clear list (không pollute context).
- Per-session storage: store sống cùng tool instance, tool instance sống cùng registry.
- Sub-agent có TodoStore RIÊNG — không thấy/sửa todo của main.
- Validate: 0 hoặc 1 `in_progress` tại 1 thời điểm.
"""

from dataclasses import dataclass
from typing import Literal

from kagent.tools.base import Tool, ToolResult, ToolContext


TodoStatus = Literal["pending", "in_progress", "completed"]


@dataclass
class Todo:
    content: str       # Imperative form: "Run tests", "Add JWT util"
    active_form: str   # Continuous form: "Running tests", "Adding JWT util"
    status: TodoStatus


class TodoStore:
    """In-memory todo store, per-session.

    Lifecycle: 1 instance / registry / session.
    Sub-agent registry tạo TodoStore mới (xem tools/agent.py).
    """

    def __init__(self):
        self._todos: list[Todo] = []

    def get(self) -> list[Todo]:
        return list(self._todos)

    def set(self, todos: list[Todo]) -> tuple[list[Todo], list[Todo]]:
        """Replace todos. Returns (old, new).

        Auto-clear nếu tất cả completed — list cũ chỉ làm bẩn context khi task xong.
        """
        old = list(self._todos)
        if todos and all(t.status == "completed" for t in todos):
            self._todos = []
        else:
            self._todos = list(todos)
        return old, list(self._todos)


_LLM_REMINDER = (
    "Todos updated successfully. Continue using TodoWrite to track progress. "
    "Maintain exactly ONE in_progress at a time. Mark items completed "
    "IMMEDIATELY after finishing — never batch."
)


class TodoWriteTool(Tool):
    name = "TodoWrite"
    description = (
        "Create or update the session task list. Use proactively for tasks "
        "requiring 3+ steps or multiple distinct actions. Each todo has "
        "{content, activeForm, status} where status ∈ pending|in_progress|completed. "
        "Maintain exactly ONE in_progress at a time. Overwrite semantics — "
        "always pass the full updated list (not a patch). Mark items completed "
        "immediately after finishing them, not in a batch at the end."
    )

    def __init__(self, store: TodoStore):
        self.store = store

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": (
                        "The full updated todo list. Overwrites the previous list."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": (
                                    "Imperative form (used for pending/completed). "
                                    "Examples: 'Run tests', 'Add JWT util'."
                                ),
                            },
                            "activeForm": {
                                "type": "string",
                                "description": (
                                    "Present-continuous form (used for in_progress). "
                                    "Examples: 'Running tests', 'Adding JWT util'."
                                ),
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        "required": ["content", "activeForm", "status"],
                    },
                }
            },
            "required": ["todos"],
        }

    def is_read_only(self) -> bool:
        return False

    def is_concurrency_safe(self) -> bool:
        return False

    def needs_permission(self) -> bool:
        # Chỉ mutate in-memory store — như Claude Code: "No permission
        # checks required for todo operations".
        return False

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        raw = args.get("todos", [])
        if not isinstance(raw, list):
            return ToolResult(
                output="", error="'todos' must be a list of objects.", is_error=True,
            )

        in_progress = [
            t for t in raw
            if isinstance(t, dict) and t.get("status") == "in_progress"
        ]
        if len(in_progress) > 1:
            return ToolResult(
                output="",
                error=(
                    f"Exactly one in_progress allowed, got {len(in_progress)}. "
                    f"Re-submit with only one item marked in_progress."
                ),
                is_error=True,
            )

        todos: list[Todo] = []
        for i, t in enumerate(raw):
            if not isinstance(t, dict):
                return ToolResult(
                    output="", error=f"Todo[{i}] must be an object.", is_error=True,
                )
            try:
                content = str(t["content"]).strip()
                active_form = str(t["activeForm"]).strip()
                status = t["status"]
            except KeyError as e:
                return ToolResult(
                    output="",
                    error=f"Todo[{i}] missing required field: {e}",
                    is_error=True,
                )
            if status not in ("pending", "in_progress", "completed"):
                return ToolResult(
                    output="",
                    error=f"Todo[{i}].status invalid: {status!r}",
                    is_error=True,
                )
            if not content:
                return ToolResult(
                    output="", error=f"Todo[{i}].content is empty.", is_error=True,
                )
            todos.append(Todo(content=content, active_form=active_form, status=status))

        old, new = self.store.set(todos)

        from kagent.ui.terminal import render_todos
        render_todos(new)

        return ToolResult(
            output=_LLM_REMINDER,
            metadata={"old_count": len(old), "new_count": len(new)},
        )
