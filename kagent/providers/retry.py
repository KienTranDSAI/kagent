"""Retry với exponential backoff cho LLM API calls.

Claude Code equivalent: src/services/api/withRetry.ts
  (DEFAULT_MAX_RETRIES=10, BASE_DELAY_MS=500, respect Retry-After,
   streaming chỉ retry trước first event)

Nguyên tắc:
- Retryable: 408/429/5xx/529 + connection/timeout errors (transient).
- Non-retryable: 400/401/403/404 (lỗi của mình, retry vô ích) → raise ngay.
- CancelledError (user interrupt) KHÔNG BAO GIỜ retry.
- Streaming: chỉ retry trước khi nhận event đầu tiên. Sau đó text đã
  ra màn hình — retry sẽ duplicate → fail fast.

Layering: module này thuộc provider layer — KHÔNG import gì từ kagent.ui.
Hiển thị "[retry n/N]..." là việc của UI: composition root (cli.main) inject
callback qua set_retry_notifier(). Mặc định None → retry im lặng (đúng cho
tests và khi dùng kagent như library).
"""

import asyncio
import os
import random
from typing import AsyncIterator, Awaitable, Callable, TypeVar

import httpx
import openai

T = TypeVar("T")

# Notifier nhận (attempt, max_retries, exc, delay) — attempt đếm từ 0.
RetryNotifier = Callable[[int, int, BaseException, float], None]

MAX_RETRIES = int(os.getenv("KAGENT_MAX_RETRIES", "4"))
BASE_DELAY = 1.0   # giây — attempt 0 chờ ~1s, 1 → ~2s, 2 → ~4s ...
MAX_DELAY = 30.0

# HTTP status đáng retry: timeout, rate limit, server error, overloaded
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}

_notifier: RetryNotifier | None = None


def set_retry_notifier(notifier: RetryNotifier | None) -> None:
    """Inject callback hiển thị retry (gọi 1 lần ở composition root)."""
    global _notifier
    _notifier = notifier


def _notify(attempt: int, exc: BaseException, delay: float) -> None:
    if _notifier is not None:
        _notifier(attempt, MAX_RETRIES, exc, delay)


def _status_of(exc: BaseException) -> int | None:
    """Lấy HTTP status từ exception của bất kỳ SDK nào (duck typing).

    - google-genai: errors.APIError có .code (int)
    - openai: APIStatusError có .status_code (int)
    """
    for attr in ("code", "status_code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def is_retryable_error(exc: BaseException) -> bool:
    status = _status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS
    # Không có status code → chỉ retry lỗi connection/timeout
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return False


def get_retry_after(exc: BaseException) -> float | None:
    """Đọc Retry-After header nếu SDK exception đính kèm response."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def compute_delay(attempt: int, retry_after: float | None = None) -> float:
    """Exponential backoff + jitter. attempt đếm từ 0.

    Retry-After từ server (nếu có và lớn hơn) thắng số tự tính.
    """
    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    delay += random.uniform(0, delay * 0.25)  # jitter tránh thundering herd
    if retry_after is not None:
        delay = max(delay, min(retry_after, MAX_DELAY * 2))
    return delay


async def with_retries(fn: Callable[[], Awaitable[T]]) -> T:
    """Retry 1 async call (non-streaming). fn phải tạo coroutine MỚI mỗi lần gọi."""
    attempt = 0
    while True:
        try:
            return await fn()
        except asyncio.CancelledError:
            raise  # user interrupt — không retry
        except Exception as e:
            if not is_retryable_error(e) or attempt >= MAX_RETRIES:
                raise
            delay = compute_delay(attempt, get_retry_after(e))
            _notify(attempt, e, delay)
            await asyncio.sleep(delay)
            attempt += 1


async def stream_with_retries(
    make_stream: Callable[[], AsyncIterator[dict]],
) -> AsyncIterator[dict]:
    """Retry async generator: CHỈ retry trước event đầu tiên.

    make_stream là factory — mỗi attempt tạo generator mới
    (generator đã raise không thể dùng lại).
    """
    attempt = 0
    while True:
        gen = make_stream()
        try:
            first = await gen.__anext__()
        except StopAsyncIteration:
            return  # stream rỗng — hợp lệ, không retry
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not is_retryable_error(e) or attempt >= MAX_RETRIES:
                raise
            delay = compute_delay(attempt, get_retry_after(e))
            _notify(attempt, e, delay)
            await asyncio.sleep(delay)
            attempt += 1
            continue
        break

    yield first
    async for event in gen:
        yield event
