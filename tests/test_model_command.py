"""Tests cho /model command — đổi model trong CÙNG provider."""

from kagent.commands.model import ModelCommand
from kagent.commands.base import CommandContext
from kagent.conversation import CostTracker


class FakeProvider:
    def __init__(self, model):
        self.model = model


def make_ctx(provider_name="gemini", model="gemini-2.5-flash"):
    return CommandContext(
        messages=[],
        session_id_ref=["s1"],
        cost_tracker=CostTracker(model=model),
        provider=FakeProvider(model),
        tool_registry=None,
        model=model,
        provider_name=provider_name,
        memory=None,
    )


async def test_switch_updates_provider_and_ctx():
    ctx = make_ctx()
    await ModelCommand().execute("gemini-2.5-pro", ctx)
    assert ctx.provider.model == "gemini-2.5-pro"   # mutate in-place
    assert ctx.model == "gemini-2.5-pro"
    assert ctx.cost_tracker.model == "gemini-2.5-pro"


async def test_gemini_rejects_foreign_model():
    ctx = make_ctx()
    await ModelCommand().execute("gpt-4o", ctx)
    assert ctx.model == "gemini-2.5-flash"          # không đổi gì
    assert ctx.provider.model == "gemini-2.5-flash"
    assert ctx.cost_tracker.model == "gemini-2.5-flash"


async def test_gemini_accepts_gemma_family():
    ctx = make_ctx()
    await ModelCommand().execute("gemma-3-27b-it", ctx)
    assert ctx.model == "gemma-3-27b-it"


async def test_openai_accepts_any_alias():
    # openai-compat (vLLM/sglang) đặt alias tùy ý — không check được tên
    ctx = make_ctx(provider_name="openai", model="qwen3.6")
    await ModelCommand().execute("my-custom-vllm-alias", ctx)
    assert ctx.provider.model == "my-custom-vllm-alias"
    assert ctx.model == "my-custom-vllm-alias"


async def test_no_args_shows_current_without_change():
    ctx = make_ctx()
    await ModelCommand().execute("", ctx)
    assert ctx.model == "gemini-2.5-flash"
    assert ctx.provider.model == "gemini-2.5-flash"
