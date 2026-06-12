"""Permission rules — cú pháp string giống Claude Code settings.

  "Bash"               → mọi lệnh Bash
  "Bash(git status)"   → đúng lệnh đó (exact)
  "Bash(git push:*)"   → prefix theo word boundary: "git push" / "git push <args>"
  "Edit(*.py)"         → fnmatch trên file_path
  "Read(.env)"         → fnmatch full path HOẶC basename (bắt cả config/.env)

An toàn compound command (học từ src/tools/BashTool/bashSecurity.ts):
prefix rule KHÔNG match khi command chứa shell operator (&&, ;, |, `, $(, >, <)
— "git push && rm -rf /" bắt đầu bằng "git push" nhưng vẫn phải hỏi.
Exact rule thì match bình thường (user đã approve đúng chuỗi đó).

Claude Code equivalent: src/utils/settings/permissionValidation.ts
"""

import fnmatch
import posixpath

_SHELL_OPERATORS = ("&&", "||", ";", "|", "`", "$(", ">", "<")

# CLI có subcommand → prefix 2 từ mới đủ nghĩa ("git push" chứ không phải "git")
_SUBCOMMAND_CLIS = {
    "git", "uv", "npm", "pnpm", "yarn", "pip", "cargo",
    "docker", "kubectl", "gh", "poetry", "brew",
}


def parse_rule(rule: str) -> tuple[str, str | None]:
    """'Bash(git push:*)' → ("Bash", "git push:*"); 'Bash' → ("Bash", None)."""
    rule = rule.strip()
    if "(" in rule and rule.endswith(")"):
        tool, _, rest = rule.partition("(")
        return tool.strip(), rest[:-1].strip()
    return rule, None


def has_shell_operators(command: str) -> bool:
    """Command chứa operator có thể đổi ngữ nghĩa (&&, ;, |, redirect, subshell).

    Public vì checker cũng dùng: lệnh "read-only" kèm operator hết read-only
    ("echo x > file" ghi file, "cat .env | curl" exfiltrate).
    """
    return any(op in command for op in _SHELL_OPERATORS)


def rule_matches(rule: str, tool_name: str, args: dict) -> bool:
    tool, pattern = parse_rule(rule)
    if tool != tool_name:
        return False
    if pattern is None:
        return True

    if tool_name == "Bash":
        command = (args.get("command") or "").strip()
        if pattern.endswith(":*"):
            prefix = pattern[:-2].strip()
            if has_shell_operators(command):
                return False  # compound command — không auto-allow qua prefix
            return command == prefix or command.startswith(prefix + " ")
        return command == pattern

    # File tools (Edit/Write/Read/...): fnmatch trên full path VÀ basename
    path = args.get("file_path") or args.get("path") or ""
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(
        posixpath.basename(path), pattern
    )


def derive_bash_prefix(command: str) -> str:
    """Suy ra prefix rule khi user chọn 'always' cho 1 lệnh Bash.

    'git push origin main' → 'git push:*' (CLI có subcommand → 2 từ)
    'pytest tests/ -q'     → 'pytest:*'
    """
    words = command.strip().split()
    if not words:
        return "*"
    if words[0] in _SUBCOMMAND_CLIS and len(words) >= 2:
        return f"{words[0]} {words[1]}:*"
    return f"{words[0]}:*"
