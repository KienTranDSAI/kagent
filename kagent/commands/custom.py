"""Custom slash commands từ markdown files.

  .kagent/commands/deploy.md   → /deploy   (project — đè user khi trùng tên)
  ~/.kagent/commands/review.md → /review   (user — global mọi project)

File format:
  ---
  description: Deploy lên staging      ← hiện trong /help
  argument-hint: [environment]         ← hiện trong usage
  ---
  Deploy app lên môi trường $ARGUMENTS ...

Body trở thành user prompt chạy qua agent loop bình thường (qua
ctx.pending_prompt — REPL nhặt lên và chạy turn với đầy đủ ESC/sigint
machinery; command KHÔNG tự gọi agent_loop).

Extension sau (Claude Code có, kagent skip): $1..$9 positional,
allowed-tools, model override, !`bash` preamble.

Claude Code equivalent: src/commands.ts (md loading) + src/utils/argumentSubstitution.ts
"""

from pathlib import Path

from kagent.commands.base import Command


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Frontmatter tối giản `key: value` giữa 2 dòng `---`. Không cần YAML lib.

    Không có `---` mở/đóng → toàn bộ text là body, meta rỗng.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    meta: dict = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1:]).strip()
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return {}, text  # thiếu --- đóng → coi như không có frontmatter


def substitute_arguments(body: str, args: str) -> str:
    """Thay $ARGUMENTS; không có placeholder mà có args → append cuối prompt."""
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", args)
    if args:
        return f"{body}\n\nARGUMENTS: {args}"
    return body


class CustomCommand(Command):
    def __init__(self, name: str, body: str,
                 description: str = "", argument_hint: str = ""):
        self.name = name
        self.body = body
        self.description = description or f"Custom command ({name}.md)"
        self.usage = argument_hint

    async def execute(self, args, ctx):
        ctx.pending_prompt[0] = substitute_arguments(self.body, args.strip())


def load_custom_commands(
    project_dir: Path | None = None,
    user_dir: Path | None = None,
) -> list[CustomCommand]:
    """Scan *.md trong 2 folder. Project đè user khi trùng tên (load user trước)."""
    project_dir = Path(project_dir) if project_dir else Path.cwd() / ".kagent" / "commands"
    user_dir = Path(user_dir) if user_dir else Path.home() / ".kagent" / "commands"

    commands: dict[str, CustomCommand] = {}
    for folder in (user_dir, project_dir):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            try:
                meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not body.strip():
                continue
            name = path.stem.lower()
            commands[name] = CustomCommand(
                name=name,
                body=body,
                description=meta.get("description", ""),
                argument_hint=meta.get("argument-hint", ""),
            )
    return list(commands.values())
