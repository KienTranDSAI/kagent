"""/todos slash command — hiển thị task list hiện tại của session."""

from kagent.commands.base import Command, CommandContext
from kagent.ui.terminal import console, render_todos


class TodosCommand(Command):
    name = "todos"
    description = "Show the current session todo list"

    async def execute(self, args: str, ctx: CommandContext) -> None:
        tool = ctx.tool_registry.get("TodoWrite")
        if tool is None or not hasattr(tool, "store"):
            console.print("[dim]TodoWrite tool not available.[/]")
            return
        todos = tool.store.get()
        if not todos:
            console.print("[dim](no todos)[/]")
            return
        console.print("[bold]Current todos:[/]")
        render_todos(todos)
