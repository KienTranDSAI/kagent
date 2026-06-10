"""Memory commands: /remember, /memory (list), /forget."""

from kagent.commands.base import Command
from kagent.ui.terminal import console, print_error


class RememberCommand(Command):
    name = "remember"
    description = "Save a fact to persistent memory (auto-loaded next session)"
    usage = "<name>: <content>"

    async def execute(self, args, ctx):
        if ":" not in args:
            print_error("Usage: /remember <name>: <content>")
            return
        name, content = args.split(":", 1)
        name = name.strip()
        content = content.strip()
        if not name or not content:
            print_error("Name and content are both required.")
            return
        path = ctx.memory.save(name, content)
        console.print(f"[green]✓ Remembered[/] [cyan]{path.stem}[/]  [dim]({path})[/]")


class MemoryCommand(Command):
    name = "memory"
    description = "List persistent memories"

    async def execute(self, args, ctx):
        items = ctx.memory.list_all()
        if not items:
            console.print("[dim]No memories yet. Use [cyan]/remember <name>: <content>[/] to save one.[/]")
            return
        console.print(f"[bold]Memories[/] ([dim]{ctx.memory.dir}[/]):")
        for item in items:
            console.print(
                f"  [cyan]{item['name']}[/]  "
                f"[dim]{item['size']}b[/]  "
                f"[dim]— {item['preview']}[/]"
            )


class ForgetCommand(Command):
    name = "forget"
    description = "Delete a memory by name"
    usage = "<name>"

    async def execute(self, args, ctx):
        if not args:
            print_error("Usage: /forget <name>")
            return
        ok = ctx.memory.delete(args)
        if ok:
            console.print(f"[green]✓ Forgot[/] {args}")
        else:
            print_error(f"No memory named '{args}'")
