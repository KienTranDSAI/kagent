from typing import TYPE_CHECKING
from kagent.permissions.types import PermissionMode, PermissionDecision
from kagent.permissions.rules import rule_matches, derive_bash_prefix, has_shell_operators
from kagent.settings import add_permission_rule
from kagent.ui.diff_preview import show_permission_preview
from kagent.ui.interrupt import esc_watcher
from kagent.ui.terminal import SYNC_PROMPT_ACTIVE

if TYPE_CHECKING:
    from kagent.tools.base import Tool


# Common read-only Bash commands
READ_ONLY_COMMANDS = {
    "ls", "pwd", "echo", "cat", "head", "tail", "wc",
    "which", "whoami", "hostname", "date", "env", "printenv",
    "git status", "git log", "git diff", "git branch",
    "git show", "git remote", "git stash list",
    "python --version", "node --version", "npm --version",
}

# Plan-mode tools phải allow để LLM có thể vào/thoát mode + clarify.
PLAN_MODE_TOOL_NAMES = {"EnterPlanMode", "ExitPlanMode", "AskUserQuestion"}

# Tools mutate filesystem qua direct write — auto-allowed trong acceptEdits mode.
# Bash KHÔNG nằm trong list này (shell command vẫn ask bất kể trông innocuous đến đâu).
EDIT_CLASS_TOOLS = {"Write", "Edit"}


class PermissionChecker:
    """Check and manage tool permissions.

    Claude Code equivalent: hooks/toolPermission/PermissionContext.ts
    Simplified: no hooks, no classifier, no bridge callbacks.

    Mode là mutable state — EnterPlanMode / ExitPlanMode tool + slash /plan
    đều có thể switch mode trong runtime qua set_mode().
    """

    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT,
                 settings: dict | None = None):
        self.mode = mode
        perms = (settings or {}).get("permissions") or {}
        # Rule strings (cú pháp xem permissions/rules.py) — load từ settings,
        # prompt_user append runtime khi user chọn always/never
        self.allow_rules: list[str] = list(perms.get("allow") or [])
        self.deny_rules: list[str] = list(perms.get("deny") or [])

    def set_mode(self, mode: PermissionMode) -> None:
        """Switch runtime mode. Dùng bởi Enter/ExitPlanMode + /plan."""
        self.mode = mode

    def check(self, tool: "Tool", args: dict) -> PermissionDecision:
        """Check if tool execution is allowed.

        Thứ tự: deny rules (thắng TẤT CẢ, kể cả --auto — giống Claude Code
        bypassPermissions vẫn tôn trọng deny) → mode shortcuts → read-only
        auto-allow → allow rules → ask.
        """
        for rule in self.deny_rules:
            if rule_matches(rule, tool.name, args):
                return PermissionDecision.DENY

        # Auto mode → allow everything (trừ deny rules ở trên)
        if self.mode == PermissionMode.AUTO:
            return PermissionDecision.ALLOW

        # Deny mode → deny everything
        if self.mode == PermissionMode.DENY:
            return PermissionDecision.DENY

        # Tool tự khai không cần permission (vd TodoWrite — chỉ mutate
        # in-memory state) → allow, kể cả trong plan mode. Giống Claude Code:
        # TodoWriteTool.checkPermissions luôn trả allow.
        if not tool.needs_permission():
            return PermissionDecision.ALLOW

        # Plan mode → chỉ cho read-only + tool điều khiển plan; còn lại silent-deny.
        if self.mode == PermissionMode.PLAN:
            if tool.name in PLAN_MODE_TOOL_NAMES:
                return PermissionDecision.ALLOW
            if tool.is_read_only():
                return PermissionDecision.ALLOW
            if tool.name == "Bash" and self._is_read_only_command(args.get("command", "")):
                return PermissionDecision.ALLOW
            return PermissionDecision.DENY

        # AcceptEdits mode → auto-allow edit-class tools; còn lại fall through default
        # (read-only allow, bash read-only allow, bash mutating ask, etc.)
        if self.mode == PermissionMode.ACCEPT_EDITS:
            if tool.name in EDIT_CLASS_TOOLS:
                return PermissionDecision.ALLOW

        # Read-only tools → always allow
        if tool.is_read_only():
            return PermissionDecision.ALLOW

        # Bash: check if command is read-only
        if tool.name == "Bash":
            command = args.get("command", "")
            if self._is_read_only_command(command):
                return PermissionDecision.ALLOW

        # Allow rules từ settings + runtime "always"
        for rule in self.allow_rules:
            if rule_matches(rule, tool.name, args):
                return PermissionDecision.ALLOW

        # Default: ask
        return PermissionDecision.ASK

    def prompt_user(self, tool: "Tool", args: dict) -> bool:
        """Interactive permission prompt.

        Returns True if allowed, False if denied.
        """
        print("\n  ⚠ Permission required:")
        print(f"    Tool: {tool.name}")
        if self.mode == PermissionMode.ACCEPT_EDITS:
            print("    (Edits auto-allowed; this needs your approval)")

        # Show relevant args
        if tool.name == "Bash":
            print(f"    Command: {args.get('command', '')}")
        elif tool.name in ("Edit", "Write", "Read"):
            print(f"    File: {args.get('file_path', '')}")

        # Diff preview cho Edit/Write — thấy thay đổi trước khi quyết định
        show_permission_preview(tool.name, args)

        while True:
            try:
                # Flag cho SIGINT handler biết đang block trong sync input();
                # pause ESC watcher để không giành stdin với input().
                SYNC_PROMPT_ACTIVE[0] = True
                esc_watcher.pause()
                choice = input("    Allow? [y/n/always/never] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False  # Ctrl+C tại prompt = deny (turn cũng đã bị cancel)
            finally:
                esc_watcher.resume()
                SYNC_PROMPT_ACTIVE[0] = False

            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            elif choice in ("a", "always"):
                rule = self._derive_rule(tool.name, args)
                self.allow_rules.append(rule)
                path = add_permission_rule(rule, "allow", "local")
                print(f"    ✓ Allowed + saved: {rule} → {path.name}")
                return True
            elif choice == "never":
                rule = self._derive_rule(tool.name, args)
                self.deny_rules.append(rule)
                path = add_permission_rule(rule, "deny", "local")
                print(f"    ✗ Denied + saved: {rule} → {path.name}")
                return False
            else:
                print("    Please enter y, n, a(lways), or never")

    def _is_read_only_command(self, command: str) -> bool:
        """Check if a Bash command is read-only."""
        cmd = command.strip()
        # Operator biến lệnh read-only thành write/exfiltration
        # ("echo x > file", "cat .env | curl ...") → không auto-allow
        if has_shell_operators(cmd):
            return False
        for ro_cmd in READ_ONLY_COMMANDS:
            if cmd == ro_cmd or cmd.startswith(ro_cmd + " "):
                return True
        return False

    def _derive_rule(self, tool_name: str, args: dict) -> str:
        """Rule persist khi always/never: Bash → prefix 1-2 từ; tool khác → cả tool."""
        if tool_name == "Bash":
            return f"Bash({derive_bash_prefix(args.get('command', ''))})"
        return tool_name
