"""Tests cho interrupt: seal history + sigint decision logic."""

from kagent.cli import sigint_decision
from kagent.engine import (
    seal_interrupted_messages,
    INTERRUPT_NOTICE,
    INTERRUPT_TOOL_NOTICE,
)


class FakeProvider:
    """Chỉ cần format_tool_result — bắt chước OpenAI format (1 dict)."""

    def format_tool_result(self, tool_call, result):
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.name,
            "content": str(result),
        }


class FakeMultimodalProvider:
    """Provider trả list 2 messages (multimodal path) — seal phải extend."""

    def format_tool_result(self, tool_call, result):
        return [
            {"role": "tool", "name": tool_call.name, "content": str(result)},
            {"role": "user", "content_blocks": [{"type": "text", "text": "x"}]},
        ]


def test_seal_appends_results_for_dangling_tool_calls():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [
            {"id": "c1", "name": "Bash", "args": {"command": "sleep 99"}},
            {"id": "c2", "name": "Read", "args": {"file_path": "x.py"}},
        ]},
    ]
    seal_interrupted_messages(messages, FakeProvider())
    assert len(messages) == 4
    assert messages[2]["role"] == "tool" and messages[2]["tool_call_id"] == "c1"
    assert messages[3]["role"] == "tool" and messages[3]["tool_call_id"] == "c2"
    assert INTERRUPT_TOOL_NOTICE in messages[2]["content"]


def test_seal_handles_list_formatted_results():
    messages = [
        {"role": "assistant", "tool_calls": [
            {"id": "c1", "name": "Read", "args": {}},
        ]},
    ]
    seal_interrupted_messages(messages, FakeMultimodalProvider())
    assert len(messages) == 3  # assistant + 2 messages từ list


def test_seal_keeps_partial_text_when_no_dangling_calls():
    messages = [{"role": "user", "content": "hi"}]
    seal_interrupted_messages(messages, FakeProvider(), partial_text="đang trả lời dở...")
    assert messages[-1]["role"] == "assistant"
    assert "đang trả lời dở..." in messages[-1]["content"]
    assert INTERRUPT_NOTICE in messages[-1]["content"]


def test_seal_noop_when_history_consistent():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "done"},
    ]
    seal_interrupted_messages(messages, FakeProvider())
    assert len(messages) == 2  # không thêm gì


def test_seal_prefers_dangling_fix_over_partial_text():
    # Cancel giữa tool exec: partial text đã nằm TRONG assistant_msg["text"] rồi
    # → chỉ cần seal tool results, không append assistant message mới.
    messages = [
        {"role": "assistant", "text": "let me check", "tool_calls": [
            {"id": "c1", "name": "Bash", "args": {}},
        ]},
    ]
    seal_interrupted_messages(messages, FakeProvider(), partial_text="let me check")
    assert len(messages) == 2
    assert messages[1]["role"] == "tool"


def test_sigint_idle_exits():
    assert sigint_decision(turn_running=False, prompt_active=False) == "raise"


def test_sigint_during_turn_cancels():
    assert sigint_decision(turn_running=True, prompt_active=False) == "cancel"


def test_sigint_during_sync_prompt_cancels_and_breaks_input():
    assert sigint_decision(turn_running=True, prompt_active=True) == "cancel+raise"
