"""AgentTool — spawn sub-agent cho complex sub-task.

Sub-agent:
- Fresh message history (chỉ nhận prompt task, không thấy conversation cha)
- Cùng bộ tools (trừ Agent — tránh recursion)
- Cùng cwd (chung file system)
- Separate context window — không làm bẩn context cha

Claude Code equivalent: src/tools/AgentTool/
"""

from kagent.tools.base import Tool, ToolResult, ToolContext
from kagent.tools.registry import ToolRegistry


SUB_AGENT_SYSTEM_SUFFIX = """

# Sub-agent mode
You are a sub-agent spawned by a main agent for a focused sub-task. Complete the task and return a concise result summary. Don't ask clarifying questions — make reasonable decisions. The main agent will use your output directly."""


class AgentTool(Tool):
    name = "Agent"
    description = (
        "Spawn a sub-agent to handle a complex sub-task autonomously. "
        "The sub-agent has its own fresh context window and the same tools "
        "(except Agent itself, to prevent recursion). "
        "Use for: deep research, exploring different approaches, or tasks "
        "that would bloat the main conversation. "
        "Pass a clear self-contained task description as `prompt`."
    )

    def __init__(self, provider, registry: ToolRegistry):
        self.provider = provider
        self.registry = registry

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Short (3-5 words) description of what the agent will do",
                },
                "prompt": {
                    "type": "string",
                    "description": "Self-contained task description for the sub-agent. Include all context it needs — it won't see the parent conversation.",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        from kagent.engine import agent_loop  # deferred import to avoid circular

        prompt = args.get("prompt", "").strip()
        if not prompt:
            return ToolResult(output="", error="prompt is required", is_error=True)

        # Sub-registry without Agent tool; TodoWrite gets a fresh store so the
        # sub-agent's task list doesn't leak into the parent (and vice versa).
        from kagent.tools.todo_write import TodoWriteTool, TodoStore
        sub_registry = ToolRegistry()
        for t in self.registry.all_tools():
            if t.name == self.name:
                continue
            if t.name == "TodoWrite":
                sub_registry.register(TodoWriteTool(TodoStore()))
                continue
            sub_registry.register(t)

        sub_messages = [{"role": "user", "content": prompt}]

        try:
            from kagent.context import build_system_prompt
            sub_system = build_system_prompt(context.cwd) + SUB_AGENT_SYSTEM_SUFFIX

            output = await agent_loop(
                messages=sub_messages,
                provider=self.provider,
                registry=sub_registry,
                system_prompt=sub_system,
                permission_checker=None,  # sub-agent không hỏi user; main agent đã kiểm soát
                cost_tracker=None,        # cost gắn vào main tracker ở turn gọi Agent
                model=None,
            )
            return ToolResult(
                output=output or "(sub-agent returned no output)",
                metadata={"sub_turns": len(sub_messages)},
            )
        except Exception as e:
            return ToolResult(output="", error=f"Sub-agent error: {e}", is_error=True)

    def is_read_only(self) -> bool:
        return False  # sub-agent can write

    def is_concurrency_safe(self) -> bool:
        return False  # spawning another full loop — keep sequential
