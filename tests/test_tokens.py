"""Tests cho real token counting (ContextTracker) + context window lookup."""

from kagent.conversation.tokens import (
    ContextTracker,
    resolve_context_tokens,
    get_context_window,
)


def test_tracker_update_and_tokens():
    t = ContextTracker()
    assert t.tokens == 0
    t.update(input_tokens=1000, output_tokens=50)
    assert t.tokens == 1050
    t.update(input_tokens=2000, output_tokens=30)
    assert t.tokens == 2030  # ghi đè, không cộng dồn — là SNAPSHOT context


def test_tracker_reset():
    t = ContextTracker()
    t.update(input_tokens=500, output_tokens=10)
    t.reset()
    assert t.tokens == 0


def test_resolve_prefers_api_number():
    t = ContextTracker()
    t.update(input_tokens=9000, output_tokens=100)
    messages = [{"role": "user", "content": "x" * 35}]  # heuristic ~10 tokens
    tokens, source = resolve_context_tokens(messages, t)
    assert tokens == 9100
    assert source == "api"


def test_resolve_falls_back_to_heuristic():
    messages = [{"role": "user", "content": "x" * 350}]
    tokens, source = resolve_context_tokens(messages, None)
    assert source == "heuristic"
    assert tokens == 100

    tokens2, source2 = resolve_context_tokens(messages, ContextTracker())  # tracker rỗng
    assert source2 == "heuristic"
    assert tokens2 == 100


def test_context_window_exact_match():
    assert get_context_window("gemini-2.5-flash") == 1_000_000


def test_context_window_prefix_fallback():
    assert get_context_window("gemini-3.1-flash") == 1_000_000
    assert get_context_window("claude-fable-5") == 200_000
    assert get_context_window("gpt-5.2-turbo") == 400_000


def test_context_window_unknown_default():
    assert get_context_window("some-local-model") == 128_000
