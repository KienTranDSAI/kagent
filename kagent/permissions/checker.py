import fnmatch
from typing import TYPE_CHECKING
from kagent.permissions.types import PermissionMode, PermissionDecision, PermissionRule

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

    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT):
        self.mode = mode
        self.rules: list[PermissionRule] = []
        self.session_allows: set[str] = set()  # "Bash:*", "Edit:*"

    def set_mode(self, mode: PermissionMode) -> None:
        """Switch runtime mode. Dùng bởi Enter/ExitPlanMode + /plan."""
        self.mode = mode

    def check(self, tool: "Tool", args: dict) -> PermissionDecision:
        """Check if tool execution is allowed."""
        # Auto mode → allow everything
        if self.mode == PermissionMode.AUTO:
            return PermissionDecision.ALLOW

        # Deny mode → deny everything
        if self.mode == PermissionMode.DENY:
            return PermissionDecision.DENY

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

        # Check session allows
        tool_key = self._make_key(tool.name, args)
        for pattern in self.session_allows:
            if fnmatch.fnmatch(tool_key, pattern):
                return PermissionDecision.ALLOW

        # Check persistent rules
        for rule in self.rules:
            if rule.tool == tool.name:
                if fnmatch.fnmatch(tool_key, f"{rule.tool}:{rule.pattern}"):
                    return rule.decision

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

        while True:
            try:
                choice = input("    Allow? [y/n/always/never] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False

            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            elif choice == "always":
                key = f"{tool.name}:*"
                self.session_allows.add(key)
                print(f"    ✓ {tool.name} always allowed for this session")
                return True
            elif choice == "never":
                self.rules.append(PermissionRule(
                    tool=tool.name, pattern="*",
                    decision=PermissionDecision.DENY,
                ))
                return False
            else:
                print("    Please enter y, n, always, or never")

    def _is_read_only_command(self, command: str) -> bool:
        """Check if a Bash command is read-only."""
        cmd = command.strip()
        for ro_cmd in READ_ONLY_COMMANDS:
            if cmd == ro_cmd or cmd.startswith(ro_cmd + " "):
                return True
        return False

    def _make_key(self, tool_name: str, args: dict) -> str:
        """Create a key for pattern matching."""
        if tool_name == "Bash":
            return f"Bash:{args.get('command', '')}"
        elif tool_name in ("Edit", "Write", "Read"):
            return f"{tool_name}:{args.get('file_path', '')}"
        return f"{tool_name}:*"
