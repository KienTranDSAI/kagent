"""Tests cho PermissionChecker — focus: needs_permission() bypass (TodoWrite)."""

import pytest

from kagent.permissions.checker import PermissionChecker
from kagent.permissions.types import PermissionMode, PermissionDecision
from kagent.tools.base import Tool, ToolResult
from kagent.tools.todo_write import TodoWriteTool, TodoStore


class MutatingTool(Tool):
    """Tool thường: mutate, cần permission (default behavior)."""
    name = "Mutating"
    description = "test tool"

    @property
    def input_schema(self):
        return {"type": "object", "properties": {}}

    async def execute(self, args, context):
        return ToolResult(output="ok")


@pytest.fixture
def todo_tool():
    return TodoWriteTool(TodoStore())


@pytest.fixture
def mutating_tool():
    return MutatingTool()


class TestNeedsPermissionBypass:
    def test_todo_write_declares_no_permission(self, todo_tool):
        assert todo_tool.needs_permission() is False

    def test_default_tool_needs_permission(self, mutating_tool):
        assert mutating_tool.needs_permission() is True

    def test_todo_allowed_in_default_mode(self, todo_tool):
        checker = PermissionChecker(PermissionMode.DEFAULT)
        assert checker.check(todo_tool, {"todos": []}) == PermissionDecision.ALLOW

    def test_todo_allowed_in_accept_edits_mode(self, todo_tool):
        checker = PermissionChecker(PermissionMode.ACCEPT_EDITS)
        assert checker.check(todo_tool, {"todos": []}) == PermissionDecision.ALLOW

    def test_todo_allowed_in_plan_mode(self, todo_tool):
        checker = PermissionChecker(PermissionMode.PLAN)
        assert checker.check(todo_tool, {"todos": []}) == PermissionDecision.ALLOW

    def test_todo_allowed_in_auto_mode(self, todo_tool):
        checker = PermissionChecker(PermissionMode.AUTO)
        assert checker.check(todo_tool, {"todos": []}) == PermissionDecision.ALLOW

    def test_todo_denied_in_deny_mode(self, todo_tool):
        # DENY là absolute — needs_permission không bypass được.
        checker = PermissionChecker(PermissionMode.DENY)
        assert checker.check(todo_tool, {"todos": []}) == PermissionDecision.DENY


class TestDefaultToolUnchanged:
    """Tool thường vẫn đi qua flow cũ — không bị needs_permission ảnh hưởng."""

    def test_mutating_tool_asks_in_default_mode(self, mutating_tool):
        checker = PermissionChecker(PermissionMode.DEFAULT)
        assert checker.check(mutating_tool, {}) == PermissionDecision.ASK

    def test_mutating_tool_denied_in_plan_mode(self, mutating_tool):
        checker = PermissionChecker(PermissionMode.PLAN)
        assert checker.check(mutating_tool, {}) == PermissionDecision.DENY

    def test_mutating_tool_asks_in_accept_edits_mode(self, mutating_tool):
        # Không phải Write/Edit → vẫn ask.
        checker = PermissionChecker(PermissionMode.ACCEPT_EDITS)
        assert checker.check(mutating_tool, {}) == PermissionDecision.ASK
