from kagent.tools.registry import ToolRegistry
from kagent.tools.bash_tool import BashTool
from kagent.tools.file_read import FileReadTool
from kagent.tools.file_write import FileWriteTool
from kagent.tools.file_edit import FileEditTool
from kagent.tools.grep import GrepTool
from kagent.tools.glob_tool import GlobTool
from kagent.tools.agent import AgentTool
from kagent.tools.ask_user import AskUserQuestionTool
from kagent.tools.todo_write import TodoWriteTool, TodoStore
from kagent.tools.plan_mode import EnterPlanModeTool, ExitPlanModeTool


def create_default_registry(provider=None, permission_checker=None) -> ToolRegistry:
    """Create registry with all available tools.

    Args:
        provider: LLMProvider — nếu truyền vào thì register AgentTool (sub-agents).
                  Nếu None, skip AgentTool (để test standalone không cần provider).
        permission_checker: PermissionChecker — nếu truyền vào thì register
                  EnterPlanMode/ExitPlanMode (Phase 11). Hai tool này flip
                  mode trên cùng checker này.

    Claude Code equivalent: getAllBaseTools() in tools.ts
    """
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(FileReadTool(provider=provider))
    registry.register(FileWriteTool())
    registry.register(FileEditTool())
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(AskUserQuestionTool())
    registry.register(TodoWriteTool(TodoStore()))

    if permission_checker is not None:
        # list-of-one share state giữa Enter và Exit để snapshot/restore mode.
        previous_mode_ref = [permission_checker.mode]
        registry.register(EnterPlanModeTool(permission_checker, previous_mode_ref))
        registry.register(ExitPlanModeTool(permission_checker, previous_mode_ref))

    if provider is not None:
        registry.register(AgentTool(provider=provider, registry=registry))
    return registry
