"""EnterPlanModeTool + ExitPlanModeTool.

Plan Mode = read-only exploration phase trước khi implement.
Hai tool này KHÔNG tự gate permission; chúng chỉ flip `permission_checker.mode`,
PermissionChecker ở tầng dưới sẽ silent-deny mọi write/bash khác.

Claude Code equivalent:
- src/tools/EnterPlanModeTool/EnterPlanModeTool.ts
- src/tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts
"""

import questionary
from prompt_toolkit.styles import Style
from rich.markdown import Markdown

from kagent.tools.base import Tool, ToolResult, ToolContext
from kagent.permissions.checker import PermissionChecker
from kagent.permissions.types import PermissionMode
from kagent.ui.interrupt import esc_watcher
from kagent.ui.terminal import console


_PROMPT_STYLE = Style.from_dict({
    "qmark": "fg:#ffaf00 bold",
    "question": "bold",
    "pointer": "fg:#ffaf00 bold",
    "highlighted": "fg:#ffaf00 bold",
    "answer": "fg:#ffaf00 bold",
})


PLAN_MODE_INSTRUCTIONS = """Entered Plan Mode.

In plan mode you should:
1. Thoroughly explore the codebase using Read/Grep/Glob.
2. Identify existing patterns and architecture.
3. Consider multiple approaches and trade-offs.
4. Use AskUserQuestion if you need to clarify approach with the user.
5. Design a concrete implementation strategy.
6. When ready, call ExitPlanMode(plan="...") to present the plan for user approval.

DO NOT write or edit any files yet. Write/Edit/Bash (non read-only) are blocked
at the permission layer — calls will return "Permission denied" until the user
approves the plan via ExitPlanMode."""


class EnterPlanModeTool(Tool):
    name = "EnterPlanMode"
    description = (
        "Switch to Plan Mode: a read-only exploration phase before implementation. "
        "Use proactively for non-trivial tasks (new features, refactors, "
        "architectural decisions, multi-file changes). In Plan Mode, only "
        "Read/Grep/Glob and read-only Bash are allowed. Exit via ExitPlanMode "
        "with the proposed plan for user approval."
    )

    def __init__(self, permission_checker: PermissionChecker, previous_mode_ref: list):
        self.permission_checker = permission_checker
        # list-of-one share giữa Enter và Exit để snapshot/restore mode.
        self.previous_mode_ref = previous_mode_ref

    @property
    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        if self.permission_checker.mode == PermissionMode.PLAN:
            return ToolResult(output="Already in Plan Mode.")
        # Snapshot mode hiện tại để Exit restore đúng (DEFAULT / AUTO / ...).
        self.previous_mode_ref[0] = self.permission_checker.mode
        self.permission_checker.set_mode(PermissionMode.PLAN)
        console.print("\n[yellow]⏸ Plan Mode active — read-only exploration[/]\n")
        return ToolResult(output=PLAN_MODE_INSTRUCTIONS)


class ExitPlanModeTool(Tool):
    name = "ExitPlanMode"
    description = (
        "Exit Plan Mode by presenting your implementation plan to the user "
        "for approval. The user approves or rejects. On approval, switch back "
        "to the previous mode and proceed with implementation. On reject, "
        "stay in Plan Mode and refine."
    )

    def __init__(self, permission_checker: PermissionChecker, previous_mode_ref: list):
        self.permission_checker = permission_checker
        self.previous_mode_ref = previous_mode_ref

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": (
                        "Implementation plan in markdown. Cover: scope, files "
                        "to touch, ordered steps, risks/edge cases."
                    ),
                },
            },
            "required": ["plan"],
        }

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return False  # độc quyền terminal cho prompt

    def bypasses_spinner(self) -> bool:
        return True

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        if self.permission_checker.mode != PermissionMode.PLAN:
            return ToolResult(
                output="", error="Not in Plan Mode — call EnterPlanMode first.",
                is_error=True,
            )

        plan_text = args.get("plan", "").strip()
        if not plan_text:
            return ToolResult(output="", error="Missing 'plan' content.", is_error=True)

        console.print("\n[bold cyan]── Proposed Plan ──[/]\n")
        console.print(Markdown(plan_text))
        console.print()

        # questionary cần độc quyền stdin — pause ESC watcher trong lúc prompt.
        esc_watcher.pause()
        try:
            choice = await questionary.select(
                "Approve plan?",
                choices=[
                    questionary.Choice(title="Approve — exit Plan Mode", value="approve"),
                    questionary.Choice(title="Reject — stay in Plan Mode", value="reject"),
                ],
                style=_PROMPT_STYLE,
            ).ask_async()
        except Exception as e:
            return ToolResult(output="", error=f"Prompt failed: {e}", is_error=True)
        finally:
            esc_watcher.resume()

        if choice is None or choice == "reject":
            console.print("[yellow]Plan rejected — staying in Plan Mode.[/]\n")
            return ToolResult(
                output="User rejected the plan. Continue refining in Plan Mode. "
                       "Use Read/Grep/Glob to gather more context, then call "
                       "ExitPlanMode again with an updated plan."
            )

        prev = self.previous_mode_ref[0] or PermissionMode.DEFAULT
        self.permission_checker.set_mode(prev)
        console.print(f"[green]✓ Plan approved — switched to {prev.value} mode[/]\n")
        return ToolResult(
            output=f"Plan approved by user. Switched to {prev.value} mode. "
                   f"Proceed with implementation following the plan."
        )
