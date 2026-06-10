import os
from pathlib import Path

# Files to look for (in order of priority)
INSTRUCTION_FILES = [
    ".agent.md",
    "AGENT.md",
    ".claude/CLAUDE.md",
    "CLAUDE.md",
]

# Global instructions
GLOBAL_INSTRUCTION_PATH = os.path.expanduser("~/.agent/instructions.md")


def load_user_instructions(cwd: str) -> str | None:
    """Load user instruction files.

    Claude Code equivalent: context.ts → getUserContext() → loads CLAUDE.md

    Looks for instruction files in:
    1. Global config (~/.agent/instructions.md)
    2. Project directory (first found from INSTRUCTION_FILES)

    Returns combined instructions or None.
    """
    parts = []

    # Global instructions
    if os.path.exists(GLOBAL_INSTRUCTION_PATH):
        content = Path(GLOBAL_INSTRUCTION_PATH).read_text(errors="replace").strip()
        if content:
            parts.append(f"# Global Instructions\n{content}")

    # Project instructions
    for filename in INSTRUCTION_FILES:
        path = os.path.join(cwd, filename)
        if os.path.exists(path):
            content = Path(path).read_text(errors="replace").strip()
            if content:
                parts.append(f"# Project Instructions ({filename})\n{content}")
            break  # Only load first found

    return "\n\n".join(parts) if parts else None
