"""Tests cho /model command — đổi model trong CÙNG provider."""

from kagent.commands.model import ModelCommand, selectable_models
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


def test_selectable_strips_prefix_and_filters_gemini_families():
    raw = [
        "models/gemini-2.5-pro",
        "models/gemini-2.5-flash",
        "models/embedding-001",       # không phải chat family → loại
        "models/gemma-3-27b-it",
        "models/imagen-3.0",          # loại
    ]
    out = selectable_models("gemini", raw, current="gemini-2.5-flash")
    assert out[0] == "gemini-2.5-flash"  # current đứng đầu
    assert "gemini-2.5-pro" in out
    assert "gemma-3-27b-it" in out
    assert all("embedding" not in m and "imagen" not in m for m in out)


def test_selectable_current_always_first_and_deduped():
    raw = ["models/gemini-2.5-pro", "models/gemini-2.5-pro"]
    out = selectable_models("gemini", raw, current="gemini-2.5-flash")
    assert out[0] == "gemini-2.5-flash"   # current chèn vào dù API không trả
    assert out.count("gemini-2.5-pro") == 1


def test_selectable_openai_selfhosted_keeps_any_alias():
    out = selectable_models("openai", ["qwen3.6"], current="qwen3.6")
    assert out == ["qwen3.6"]


def test_selectable_openai_official_filters_non_chat():
    raw = [
        "gpt-4o", "o3-mini", "chatgpt-4o-latest",
        "whisper-1", "text-embedding-3-small", "dall-e-3",
        "gpt-4o-audio-preview", "tts-1",
    ]
    out = selectable_models("openai", raw, current="gpt-4o", official_openai=True)
    assert "gpt-4o" in out and "o3-mini" in out and "chatgpt-4o-latest" in out
    assert all(
        bad not in m
        for m in out
        for bad in ("whisper", "embedding", "dall-e", "audio", "tts")
    )


async def test_no_args_does_not_switch_model():
    # Picker path (non-TTY trong pytest → in list fallback) — không đổi gì
    ctx = make_ctx()
    ctx.provider.list_models = _fake_list  # type: ignore[attr-defined]
    await ModelCommand().execute("", ctx)
    assert ctx.model == "gemini-2.5-flash"
    assert ctx.provider.model == "gemini-2.5-flash"


async def _fake_list():
    return ["models/gemini-2.5-pro", "models/gemini-2.5-flash"]
