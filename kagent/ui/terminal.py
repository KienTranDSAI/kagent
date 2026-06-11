"""Rich-based terminal UI helpers.

Claude Code dùng React + Ink (~140 components). kagent dùng `rich` cho đơn giản.
"""

import time
from contextlib import asynccontextmanager
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text


console = Console()

# Flag: đang block trong SYNC input prompt (permission prompt).
# SIGINT handler đọc flag này để biết phải raise KeyboardInterrupt
# phá input() (task.cancel() không phá được sync call đang block).
# List-of-1 trick giống session_id_ref — mutable qua module reference.
SYNC_PROMPT_ACTIVE = [False]


def print_welcome(provider: str, model: str, tools: list[str], cwd: str, perm_mode: str):
    """Welcome panel hiển thị lúc start."""
    body = (
        f"[bold]Provider:[/] {provider}:{model}\n"
        f"[bold]Tools:[/] {', '.join(tools)}\n"
        f"[bold]CWD:[/] {cwd}\n"
        f"[bold]Permission:[/] {perm_mode}"
    )
    console.print(Panel(
        body,
        title="[bold cyan]kagent[/]",
        subtitle="[dim]type 'exit' to quit[/]",
        border_style="cyan",
    ))


def print_response(text: str):
    """Render text response as markdown (non-streaming fallback)."""
    console.print(Markdown(text))


def print_tool_call(tool_name: str, args: dict):
    """In tool call kèm args tóm tắt."""
    args_str = _format_args(args)
    console.print(f"  [dim]●[/] [bold cyan]{tool_name}[/]([dim]{args_str}[/])")


def print_tool_result(success: bool, duration: float, preview: str = ""):
    """In kết quả tool: ✓ thành công hoặc ✗ lỗi + thời gian."""
    icon = "[green]✓[/]" if success else "[red]✗[/]"
    line = f"    {icon} [dim]{duration:.2f}s[/]"
    if preview:
        line += f" [dim]— {preview}[/]"
    console.print(line)


def print_tool_error(message: str):
    console.print(f"    [red]✗ {message}[/]")


def print_permission_prompt(tool_name: str, args: dict):
    console.print("\n  [yellow]⚠ Permission required[/]")
    console.print(f"    Tool: [bold]{tool_name}[/]")
    if tool_name == "Bash":
        console.print(f"    Command: [cyan]{args.get('command', '')}[/]")
    else:
        for k, v in args.items():
            s = str(v)
            if len(s) > 80:
                s = s[:80] + "..."
            console.print(f"    {k}: [cyan]{s}[/]")


def print_error(message: str):
    console.print(f"[red]Error:[/] {message}")


def print_info(message: str):
    console.print(f"[dim]{message}[/]")


def get_prompt_label(mode) -> str:
    """REPL input prompt label phản ánh permission mode hiện tại."""
    from kagent.permissions.types import PermissionMode
    if mode == PermissionMode.PLAN:
        return "[yellow]⏸ plan[/] [bold green]>[/]"
    if mode == PermissionMode.ACCEPT_EDITS:
        return "[blue]⏵⏵ accept[/] [bold green]>[/]"
    if mode == PermissionMode.AUTO:
        return "[red]⏵⏵ auto[/] [bold green]>[/]"
    if mode == PermissionMode.DENY:
        return "[red]⊘ deny[/] [bold green]>[/]"
    return "[bold green]>[/]"


def render_todos(todos) -> None:
    """In checklist sau mỗi TodoWrite call.

    Icon convention:
      ☐ pending      (dim, content)
      ▶ in_progress  (yellow, activeForm)
      ✔ completed    (green, content, strikethrough)
    """
    if not todos:
        console.print("    [dim](todo list cleared)[/]")
        return
    for t in todos:
        if t.status == "completed":
            console.print(f"    [green]✔[/] [dim s]{t.content}[/]")
        elif t.status == "in_progress":
            console.print(f"    [yellow]▶[/] [yellow]{t.active_form}[/]")
        else:
            console.print(f"    [dim]☐[/] [dim]{t.content}[/]")


def _format_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v).replace("\n", " ")
        if len(s) > 50:
            s = s[:50] + "..."
        parts.append(f'{k}="{s}"')
    return ", ".join(parts)


@asynccontextmanager
async def tool_spinner(tool_name: str, args: dict):
    """Async context manager: in tool call + spinner, khi xong in kết quả.

    Usage:
        async with tool_spinner("Read", {"file_path": "x.py"}) as report:
            result = await tool.execute(...)
            report(success=not result.is_error, preview=str(result)[:80])
    """
    print_tool_call(tool_name, args)
    start = time.time()
    spinner = Spinner("dots", text=Text("  running...", style="dim"))
    status = {"success": True, "preview": ""}

    def report(success: bool = True, preview: str = ""):
        status["success"] = success
        status["preview"] = preview

    with Live(spinner, console=console, refresh_per_second=10, transient=True):
        try:
            yield report
        except Exception:
            status["success"] = False
            raise
        finally:
            duration = time.time() - start

    print_tool_result(status["success"], duration, status["preview"])
