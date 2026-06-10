"""/mode slash command — switch permission mode at runtime."""

from kagent.commands.base import Command, CommandContext
from kagent.permissions.types import PermissionMode
from kagent.ui.terminal import console, print_error


_MODE_MAP = {
    "default": PermissionMode.DEFAULT,
    "accept-edits": PermissionMode.ACCEPT_EDITS,
    "accept": PermissionMode.ACCEPT_EDITS,
    "plan": PermissionMode.PLAN,
    "auto": PermissionMode.AUTO,
    "deny": PermissionMode.DENY,
}


class ModeCommand(Command):
    name = "mode"
    description = "Show or switch permission mode"
    usage = "[default|accept-edits|plan|auto|deny]"

    async def execute(self, args: str, ctx: CommandContext) -> None:
        checker = ctx.permission_checker
        if checker is None:
            print_error("Permission checker not available.")
            return

        target = args.strip().lower()
        if not target:
            console.print(
                f"Current mode: [bold]{checker.mode.value}[/]  "
                f"[dim](choices: {', '.join(sorted(set(_MODE_MAP)))})[/]"
            )
            return

        new_mode = _MODE_MAP.get(target)
        if new_mode is None:
            print_error(f"Unknown mode: {target}. Choices: {sorted(set(_MODE_MAP))}")
            return

        checker.set_mode(new_mode)
        console.print(f"[green]Mode → [bold]{new_mode.value}[/][/]")
