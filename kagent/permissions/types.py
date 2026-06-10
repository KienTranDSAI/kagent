from enum import Enum
from dataclasses import dataclass


class PermissionMode(Enum):
    """How to handle permission checks.

    Claude Code equivalent: PermissionMode in types/permissions.ts
    """
    DEFAULT = "default"    # Ask for write operations
    AUTO = "auto"          # Allow everything (dangerous!)
    DENY = "deny"          # Deny all tool execution
    PLAN = "plan"          # Read-only exploration (write/bash silent-deny)
    ACCEPT_EDITS = "acceptEdits"  # Auto-allow Edit/Write; Bash + other writes still ask


class PermissionDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionRule:
    """A persistent permission rule.

    Examples:
    - PermissionRule(tool="Bash", pattern="git *")     → allow all git commands
    - PermissionRule(tool="Edit", pattern="*.py")      → allow editing Python files
    - PermissionRule(tool="Bash", pattern="*")          → allow all Bash commands
    """
    tool: str
    pattern: str
    decision: PermissionDecision
