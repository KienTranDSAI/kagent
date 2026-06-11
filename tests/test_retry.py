"""Tests cho retry/backoff helper."""

import asyncio
import pytest

from kagent.providers import retry as retry_mod
from kagent.providers.retry import (
    with_retries,
    stream_with_retries,
    is_retryable_error,
    compute_delay,
    set_retry_notifier,
)


class FakeAPIError(Exception):
    """Giả lập SDK error có status code (genai dùng .code, openai dùng .status_code)."""
    def __init__(self, code: int):
        super().__init__(f"status {code}")
        self.code = code


@pytest.fixture
def no_sleep(monkeypatch):
    """Thay asyncio.sleep bằng recorder + tắt jitter để test deterministic."""
    sleeps: list[float] = []

    async def fake_sleep(d):
        sleeps.append(d)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(retry_mod.random, "uniform", lambda a, b: 0.0)
    return sleeps


async def test_with_retries_succeeds_after_transient(no_sleep):
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise FakeAPIError(429)
        return "ok"

    assert await with_retries(fn) == "ok"
    assert calls["n"] == 3
    assert len(no_sleep) == 2
    assert no_sleep[1] > no_sleep[0]  # exponential growth


async def test_with_retries_non_retryable_raises_immediately(no_sleep):
    async def fn():
        raise FakeAPIError(400)

    with pytest.raises(FakeAPIError):
        await with_retries(fn)
    assert no_sleep == []


async def test_with_retries_gives_up_after_max(no_sleep, monkeypatch):
    monkeypatch.setattr(retry_mod, "MAX_RETRIES", 2)

    async def fn():
        raise FakeAPIError(503)

    with pytest.raises(FakeAPIError):
        await with_retries(fn)
    assert len(no_sleep) == 2


async def test_stream_retries_before_first_event(no_sleep):
    state = {"call": 0}

    async def make_stream():
        state["call"] += 1
        if state["call"] == 1:
            raise FakeAPIError(429)
        yield {"type": "text", "delta": "a"}
        yield {"type": "finish", "reason": "stop"}

    events = [e async for e in stream_with_retries(make_stream)]
    assert [e["type"] for e in events] == ["text", "finish"]
    assert len(no_sleep) == 1


async def test_stream_no_retry_after_first_event(no_sleep):
    async def make_stream():
        yield {"type": "text", "delta": "a"}
        raise FakeAPIError(503)

    events = []
    with pytest.raises(FakeAPIError):
        async for e in stream_with_retries(make_stream):
            events.append(e)
    assert len(events) == 1     # đã nhận event đầu
    assert no_sleep == []       # KHÔNG retry giữa stream


async def test_retry_notifier_called(no_sleep):
    """UI nhận thông báo retry qua callback inject — không phải retry tự in."""
    seen: list[tuple] = []
    set_retry_notifier(lambda attempt, max_retries, exc, delay: seen.append((attempt, max_retries)))
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeAPIError(429)
        return "ok"

    try:
        assert await with_retries(fn) == "ok"
    finally:
        set_retry_notifier(None)
    assert seen == [(0, retry_mod.MAX_RETRIES)]


def test_compute_delay_growth_and_cap(monkeypatch):
    monkeypatch.setattr(retry_mod.random, "uniform", lambda a, b: 0.0)
    assert compute_delay(0) == retry_mod.BASE_DELAY
    assert compute_delay(1) == retry_mod.BASE_DELAY * 2
    assert compute_delay(10) == retry_mod.MAX_DELAY  # cap


def test_compute_delay_respects_retry_after(monkeypatch):
    monkeypatch.setattr(retry_mod.random, "uniform", lambda a, b: 0.0)
    assert compute_delay(0, retry_after=10.0) == 10.0


def test_is_retryable_status_mapping():
    assert is_retryable_error(FakeAPIError(429))
    assert is_retryable_error(FakeAPIError(503))
    assert is_retryable_error(FakeAPIError(529))
    assert not is_retryable_error(FakeAPIError(400))
    assert not is_retryable_error(FakeAPIError(401))
    assert not is_retryable_error(ValueError("x"))
    assert is_retryable_error(ConnectionError())
