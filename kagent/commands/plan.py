"""/plan slash command — manually toggle Plan Mode from REPL."""

from kagent.commands.base import Command, CommandContext
from kagent.permissions.types import PermissionMode
from kagent.ui.terminal import console, print_error


class PlanCommand(Command):
    name = "plan"
    description = "Toggle Plan Mode (read-only exploration)"

    async def execute(self, args: str, ctx: CommandContext) -> None:
        checker = ctx.permission_checker
        if checker is None:
            print_error("Permission checker not available.")
            return

        # Toggle: nếu đang PLAN → exit về DEFAULT; ngược lại → vào PLAN.
        if checker.mode == PermissionMode.PLAN:
            checker.set_mode(PermissionMode.DEFAULT)
            console.print("[green]✓ Exited Plan Mode → DEFAULT.[/]")
            return

        checker.set_mode(PermissionMode.PLAN)
        console.print(
            "[yellow]⏸ Plan Mode enabled.[/] "
            "[dim]Write/Edit/Bash sẽ bị deny đến khi agent gọi ExitPlanMode "
            "hoặc /plan toggle lại.[/]"
        )
