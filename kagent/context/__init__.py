import os
from datetime import date
from kagent.context.system_prompt import (
    BASE_SYSTEM_PROMPT,
    TODO_GUIDANCE,
    PLAN_MODE_GUIDANCE,
    MULTIMODAL_GUIDANCE,
)
from kagent.context.project import get_project_context
from kagent.context.user import load_user_instructions


def build_system_prompt(
    cwd: str | None = None,
    with_todo: bool = True,
    with_plan_mode: bool = False,
    with_multimodal: bool = False,
) -> str:
    """Build complete system prompt from all context sources.

    Sections (in order):
      1. Base prompt
      2. Plan-mode guidance (when EnterPlanMode tool is registered)
      3. Todo guidance (when TodoWrite tool is registered)
      4. Multimodal guidance (when provider supports PDF or image)
      5. Project context (git, project type)
      6. User instructions (.agent.md, CLAUDE.md, etc.)
      7. Persistent memories (from ~/.kagent/memory/)
      8. Environment (cwd, platform, date)
    """
    cwd = cwd or os.getcwd()
    parts = [BASE_SYSTEM_PROMPT]

    if with_plan_mode:
        parts.append(PLAN_MODE_GUIDANCE)

    if with_todo:
        parts.append(TODO_GUIDANCE)

    if with_multimodal:
        parts.append(MULTIMODAL_GUIDANCE)

    project_ctx = get_project_context(cwd)
    if project_ctx:
        parts.append(f"# Project Context\n{project_ctx}")

    user_instructions = load_user_instructions(cwd)
    if user_instructions:
        parts.append(user_instructions)

    memories = _load_memories()
    if memories:
        parts.append(f"# Memories (persistent)\n{memories}")

    parts.append(
        f"# Environment\n"
        f"- Working directory: {cwd}\n"
        f"- Platform: {os.uname().sysname}\n"
        f"- Date: {date.today().isoformat()}"
    )

    return "\n\n".join(parts)


def _load_memories() -> str:
    """Deferred import để tránh circular."""
    try:
        from kagent.memory.manager import MemoryManager
        return MemoryManager().all_content_for_prompt()
    except Exception:
        return ""
