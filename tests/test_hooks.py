"""Tests cho hook system — exit code protocol + matcher + engine integration."""

from kagent.hooks.runner import HookRunner, blocked_feedback, _matcher_matches


def _settings(event, command, matcher="", timeout=None):
    hook: dict = {"type": "command", "command": command}
    if timeout is not None:
        hook["timeout"] = timeout
    entry: dict = {"hooks": [hook]}
    if matcher:
        entry["matcher"] = matcher
    return {"hooks": {event: [entry]}}


# ── exit code protocol ──────────────────────────────────────

async def test_exit_0_not_blocked_captures_stdout():
    runner = HookRunner(_settings("PreToolUse", "echo hello-from-hook"))
    results = await runner.run("PreToolUse", tool_name="Bash", extra={})
    assert len(results) == 1
    assert results[0].blocked is False
    assert results[0].stdout == "hello-from-hook"


async def test_exit_2_blocked_with_stderr():
    runner = HookRunner(_settings("PreToolUse", "echo 'khong duoc push' >&2; exit 2"))
    results = await runner.run("PreToolUse", tool_name="Bash", extra={})
    assert results[0].blocked is True
    assert "khong duoc push" in results[0].stderr
    assert blocked_feedback(results) == "khong duoc push"


async def test_other_exit_code_not_blocked():
    runner = HookRunner(_settings("PreToolUse", "exit 1"))
    results = await runner.run("PreToolUse", tool_name="Bash", extra={})
    assert results[0].exit_code == 1 and results[0].blocked is False
    assert blocked_feedback(results) is None


async def test_payload_arrives_via_stdin():
    # `cat` echo nguyên JSON payload ra stdout
    runner = HookRunner(_settings("PreToolUse", "cat"), cwd="/tmp/x")
    results = await runner.run(
        "PreToolUse", tool_name="Bash",
        extra={"tool_name": "Bash", "tool_input": {"command": "ls"}},
    )
    out = results[0].stdout
    assert '"hook_event_name": "PreToolUse"' in out
    assert '"tool_name": "Bash"' in out
    assert '"cwd": "/tmp/x"' in out


async def test_timeout_kills_hook():
    runner = HookRunner(_settings("PreToolUse", "sleep 5", timeout=0.2))
    results = await runner.run("PreToolUse", tool_name="Bash", extra={})
    assert results[0].exit_code == 124
    assert results[0].blocked is False  # timeout là lỗi hook, không phải block


# ── matcher ─────────────────────────────────────────────────

def test_matcher_regex_full_match():
    assert _matcher_matches("Edit|Write", "Write")
    assert not _matcher_matches("Edit|Write", "Bash")
    assert not _matcher_matches("Edit", "EditX")        # full-match, không phải search
    assert _matcher_matches("", "Anything")
    assert _matcher_matches("*", "Anything")
    assert not _matcher_matches("[invalid(", "Bash")    # regex hỏng → không match, không crash


async def test_non_matching_hook_skipped():
    runner = HookRunner(_settings("PreToolUse", "echo x", matcher="Edit"))
    assert await runner.run("PreToolUse", tool_name="Bash", extra={}) == []


async def test_stop_event_ignores_matcher():
    runner = HookRunner(_settings("Stop", "echo done", matcher="Bash"))
    results = await runner.run("Stop", extra={})
    assert len(results) == 1 and results[0].stdout == "done"


# ── engine integration ──────────────────────────────────────

from kagent.engine import agent_loop  # noqa: E402
from kagent.tools.base import Tool, ToolResult  # noqa: E402
from kagent.tools.registry import ToolRegistry  # noqa: E402


class FakeTool(Tool):
    name = "Danger"
    description = "fake mutating tool"
    executed = False

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, args, context):
        FakeTool.executed = True
        return ToolResult(output="tool ran fine")


class FakeProvider:
    """Lần 1: gọi tool; lần 2: trả text — đủ cho engine chạy 2 iteration."""

    supports_pdf = False
    supports_image = False

    def __init__(self):
        self.calls = 0

    async def stream_chat(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            from kagent.providers.base import ToolCall
            yield {"type": "tool_call",
                   "call": ToolCall(id="c1", name="Danger", args={})}
        else:
            yield {"type": "text", "delta": "done"}
        yield {"type": "usage", "input_tokens": 1, "output_tokens": 1}

    def format_tool_result(self, tool_call, result):
        return {"role": "tool", "name": tool_call.name, "content": str(result)}

    def format_messages(self, messages):
        return messages

    def format_tools(self, tools):
        return tools


def _registry():
    reg = ToolRegistry()
    reg.register(FakeTool())
    return reg


async def test_pretooluse_exit2_blocks_tool():
    FakeTool.executed = False
    hooks = HookRunner(_settings("PreToolUse", "echo 'cam chay tool nay' >&2; exit 2"))
    messages: list[dict] = [{"role": "user", "content": "go"}]
    await agent_loop(
        messages=messages, provider=FakeProvider(), registry=_registry(),
        system_prompt="t", hooks=hooks,
    )
    assert FakeTool.executed is False                      # tool KHÔNG chạy
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert "cam chay tool nay" in tool_msgs[0]["content"]  # feedback về model


async def test_posttooluse_exit2_appends_feedback():
    FakeTool.executed = False
    hooks = HookRunner(_settings("PostToolUse", "echo 'lint fail: sua di' >&2; exit 2"))
    messages: list[dict] = [{"role": "user", "content": "go"}]
    await agent_loop(
        messages=messages, provider=FakeProvider(), registry=_registry(),
        system_prompt="t", hooks=hooks,
    )
    assert FakeTool.executed is True                       # tool VẪN chạy
    feedback_msgs = [
        m for m in messages
        if m.get("role") == "user" and "PostToolUse" in str(m.get("content", ""))
    ]
    assert len(feedback_msgs) == 1
    assert "lint fail: sua di" in feedback_msgs[0]["content"]
