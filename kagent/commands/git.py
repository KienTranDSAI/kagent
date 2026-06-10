"""Git-related slash commands: /commit, /diff, /review."""

import subprocess
from rich.live import Live
from rich.markdown import Markdown
from rich.syntax import Syntax

from kagent.commands.base import Command
from kagent.ui.terminal import console, print_info, print_error


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run git command, return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out"


def _is_git_repo() -> bool:
    rc, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


class DiffCommand(Command):
    name = "diff"
    description = "Show git diff (add --staged for staged)"
    usage = "[--staged] [path]"

    async def execute(self, args, ctx):
        if not _is_git_repo():
            print_error("Not in a git repository.")
            return
        git_args = ["diff"] + (args.split() if args else [])
        rc, out, err = _run_git(git_args)
        if rc != 0:
            print_error(err.strip() or "git diff failed")
            return
        if not out.strip():
            console.print("[dim](no changes)[/]")
            return
        console.print(Syntax(out, "diff", theme="monokai", line_numbers=False, word_wrap=True))


COMMIT_PROMPT = """Write a concise git commit message for this diff.

Rules:
- First line: under 70 chars, imperative mood (e.g. "fix bug", "add feature")
- Blank line, then optional 1-2 sentence body explaining WHY (not what)
- No trailing period on subject
- No quotes around the message
- Return ONLY the commit message text, nothing else"""


class CommitCommand(Command):
    name = "commit"
    description = "Generate commit message from staged diff and commit"

    async def execute(self, args, ctx):
        if not _is_git_repo():
            print_error("Not in a git repository.")
            return

        rc, diff, err = _run_git(["diff", "--staged"])
        if rc != 0:
            print_error(err.strip() or "git diff --staged failed")
            return
        if not diff.strip():
            console.print("[yellow]No staged changes.[/] Run [cyan]git add <files>[/] first.")
            return

        if len(diff) > 20_000:
            diff = diff[:20_000] + "\n[... diff truncated ...]"

        print_info("Generating commit message...")
        response = await ctx.provider.chat(
            messages=[{"role": "user", "content": f"Diff:\n\n```diff\n{diff}\n```"}],
            system_prompt=COMMIT_PROMPT,
        )
        if ctx.cost_tracker and response.usage:
            ctx.cost_tracker.add(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        message = (response.text or "").strip()
        if message.startswith("```"):
            message = message.strip("`").strip()
        if not message:
            print_error("LLM returned empty message.")
            return

        console.print("\n[bold]Suggested message:[/]")
        console.print(f"[green]{message}[/]\n")

        try:
            confirm = console.input("[yellow]Commit with this message? [y/N/e(dit)][/] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled.[/]")
            return

        if confirm == "e":
            try:
                message = console.input("[cyan]New message:[/] ").strip() or message
            except (EOFError, KeyboardInterrupt):
                return
        elif confirm != "y":
            console.print("[dim]Cancelled.[/]")
            return

        rc, out, err = _run_git(["commit", "-m", message])
        if rc == 0:
            console.print(f"[green]✓ Committed:[/] {out.strip().splitlines()[0] if out.strip() else 'ok'}")
        else:
            print_error(err.strip() or out.strip() or "git commit failed")


REVIEW_PROMPT = """You are a careful code reviewer. Review the following git diff and report:

1. **Summary** — what this change does in 1-2 sentences
2. **Concerns** — bugs, edge cases, security issues, performance issues (bullet list)
3. **Style/readability** — naming, structure (brief)
4. **Tests** — what's tested / what's missing

Be concise and specific (cite file:line when possible). If nothing concerns you in a section, write "LGTM"."""


class ReviewCommand(Command):
    name = "review"
    description = "LLM code review on current diff (staged + unstaged)"
    usage = "[--staged]"

    async def execute(self, args, ctx):
        if not _is_git_repo():
            print_error("Not in a git repository.")
            return
        git_args = ["diff"] + (args.split() if args else [])
        rc, diff, err = _run_git(git_args)
        if rc != 0:
            print_error(err.strip() or "git diff failed")
            return
        if not diff.strip():
            rc, diff, _ = _run_git(["diff", "--staged"])
        if not diff.strip():
            console.print("[dim]Nothing to review.[/]")
            return

        if len(diff) > 40_000:
            diff = diff[:40_000] + "\n[... diff truncated ...]"

        console.print("[dim]Running review...[/]")
        text_acc = ""
        with Live(Markdown(""), console=console, refresh_per_second=10) as live:
            async for event in ctx.provider.stream_chat(
                messages=[{"role": "user", "content": f"Diff:\n\n```diff\n{diff}\n```"}],
                tools=None,
                system_prompt=REVIEW_PROMPT,
            ):
                if event["type"] == "text":
                    text_acc += event["delta"]
                    live.update(Markdown(text_acc))
                elif event["type"] == "usage" and ctx.cost_tracker:
                    ctx.cost_tracker.add(
                        input_tokens=event["input_tokens"],
                        output_tokens=event["output_tokens"],
                    )
