"""Built-in slash commands: help, cost, tokens, micro, compact, sessions, resume, new, save, clear, exit."""

import sys

from kagent.commands.base import Command
from kagent.conversation import (
    estimate_messages_tokens,
    get_context_window,
    micro_compact,
    compact_conversation,
    new_session_id,
    save_session,
    load_session,
    list_sessions,
)
from kagent.ui.terminal import console, print_info, print_error


class HelpCommand(Command):
    name = "help"
    description = "Show available commands"

    def __init__(self, registry):
        self.registry = registry

    async def execute(self, args, ctx):
        console.print("[bold]Available commands:[/]")
        for cmd in sorted(self.registry.all(), key=lambda c: c.name):
            usage = f" {cmd.usage}" if cmd.usage else ""
            console.print(f"  [cyan]/{cmd.name}[/]{usage}  [dim]— {cmd.description}[/]")
        console.print("\n[dim]CLI flags: --auto --accept-edits --plan --deny --resume <id>[/]")


class CostCommand(Command):
    name = "cost"
    description = "Show token usage + estimated cost"

    async def execute(self, args, ctx):
        console.print(f"[bold]Cost:[/] {ctx.cost_tracker.summary()}")


class TokensCommand(Command):
    name = "tokens"
    description = "Show current context size estimate"

    async def execute(self, args, ctx):
        est = estimate_messages_tokens(ctx.messages)
        ctx_window = get_context_window(ctx.model)
        pct = (est / ctx_window) * 100 if ctx_window else 0
        console.print(f"[bold]Context:[/] ~{est:,} / {ctx_window:,} ({pct:.1f}%)")


class MicroCompactCommand(Command):
    name = "micro"
    description = "Tier-1 micro-compact (clear old tool outputs)"

    async def execute(self, args, ctx):
        before = estimate_messages_tokens(ctx.messages)
        ctx.messages[:] = micro_compact(ctx.messages)
        after = estimate_messages_tokens(ctx.messages)
        console.print(f"[green]micro-compact:[/] {before:,} → {after:,} tokens")


class CompactCommand(Command):
    name = "compact"
    description = "Tier-3 full compact (LLM summarizes old messages)"

    async def execute(self, args, ctx):
        before = estimate_messages_tokens(ctx.messages)
        print_info("Running LLM summarization...")
        ctx.messages[:] = await compact_conversation(ctx.messages, ctx.provider)
        after = estimate_messages_tokens(ctx.messages)
        console.print(f"[green]compact:[/] {before:,} → {after:,} tokens")


class ClearCommand(Command):
    name = "clear"
    description = "Clear conversation history (keeps session id)"

    async def execute(self, args, ctx):
        ctx.messages.clear()
        console.print("[green]Conversation cleared.[/]")


class SessionsCommand(Command):
    name = "sessions"
    description = "List recent saved sessions"

    async def execute(self, args, ctx):
        entries = list_sessions(limit=20)
        if not entries:
            console.print("[dim]No saved sessions.[/]")
            return
        console.print("[bold]Sessions:[/]")
        for e in entries:
            console.print(
                f"  [cyan]{e['id']}[/]  [dim]{e['updated']}[/]  "
                f"msgs={e['messages']}  [dim]{e['first_user']}[/]"
            )


class ResumeCommand(Command):
    name = "resume"
    description = "Resume a saved session"
    usage = "<session_id>"

    async def execute(self, args, ctx):
        if not args:
            print_error("Usage: /resume <session_id>")
            return
        loaded = load_session(args)
        if loaded is None:
            print_error(f"Session not found: {args}")
            return
        ctx.messages.clear()
        ctx.messages.extend(loaded)
        ctx.session_id_ref[0] = args
        console.print(f"[green]Resumed:[/] {args} ({len(loaded)} messages)")


class NewSessionCommand(Command):
    name = "new"
    description = "Start a new session (clears history + new id)"

    async def execute(self, args, ctx):
        ctx.messages.clear()
        ctx.session_id_ref[0] = new_session_id()
        console.print(f"[green]New session:[/] {ctx.session_id_ref[0]}")


class SaveCommand(Command):
    name = "save"
    description = "Force-save current session to disk"

    async def execute(self, args, ctx):
        save_session(
            ctx.session_id_ref[0],
            ctx.messages,
            metadata={"model": ctx.model, "provider": ctx.provider_name},
        )
        console.print(f"[green]Saved:[/] {ctx.session_id_ref[0]}")


class ExitCommand(Command):
    name = "exit"
    description = "Exit the REPL"

    async def execute(self, args, ctx):
        console.print("[dim]Bye![/]")
        sys.exit(0)


class QuitCommand(ExitCommand):
    name = "quit"
    description = "Exit the REPL (alias of /exit)"
