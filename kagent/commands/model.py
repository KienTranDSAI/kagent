"""/model slash command — đổi model trong CÙNG provider đang chạy.

KHÔNG đổi provider: client/API key/base_url giữ nguyên, chỉ mutate
`provider.model` in-place — mọi nơi giữ reference tới provider (tool
registry, sub-agent, compact) tự dùng model mới, không phải rebuild gì.
Đổi chéo provider (gemini ↔ openai) → restart với LLM_PROVIDER/LLM_MODEL
(history lưu normalized nhưng tool_call_id không tương thích chéo API).

`/model` không args → picker: lấy danh sách từ chính API
(Gemini models.list / OpenAI-compat GET /v1/models — vLLM, sglang đều có),
chọn bằng mũi tên. Không TTY → in list dạng text.
"""

import sys

import questionary

from kagent.commands.base import Command
from kagent.conversation import get_context_window
from kagent.ui.terminal import console, print_error


# Google API chỉ serve các family này — chặn sớm typo / model của provider
# khác. openai-compat KHÔNG check được (vLLM/sglang đặt alias tùy ý) → cho qua,
# server tự trả lỗi nếu model không tồn tại.
_GEMINI_PREFIXES = ("gemini", "gemma", "learnlm")

# OpenAI chính chủ trả cả model non-chat (whisper/tts/embedding/dall-e...)
# → picker chỉ giữ chat family. Self-hosted thì server chỉ serve model chat.
_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")
_OPENAI_NON_CHAT_HINTS = (
    "audio", "realtime", "transcribe", "tts", "whisper",
    "embedding", "dall-e", "image", "moderation", "search", "instruct",
)


def selectable_models(
    provider_name: str,
    raw_names: list[str],
    current: str,
    official_openai: bool = False,
) -> list[str]:
    """Lọc + chuẩn hóa danh sách cho picker — pure function, test được.

    Strip "models/" prefix (Gemini), lọc theo family, dedup + sort,
    current luôn đứng đầu (kể cả khi API không trả về nó).
    """
    names: list[str] = []
    for raw in raw_names:
        name = raw.removeprefix("models/")
        low = name.lower()
        if provider_name == "gemini" and not low.startswith(_GEMINI_PREFIXES):
            continue
        if official_openai:
            if not low.startswith(_OPENAI_CHAT_PREFIXES):
                continue
            if any(hint in low for hint in _OPENAI_NON_CHAT_HINTS):
                continue
        if name not in names:
            names.append(name)

    names.sort()
    if current in names:
        names.remove(current)
    return [current] + names


class ModelCommand(Command):
    name = "model"
    description = "Pick or switch model (cùng provider only)"
    usage = "[model_name]"

    async def execute(self, args, ctx):
        new = args.strip()
        if not new:
            await self._pick(ctx)
            return

        if ctx.provider_name == "gemini" and not new.lower().startswith(_GEMINI_PREFIXES):
            print_error(
                f"'{new}' không thuộc provider gemini — chỉ được đổi model trong "
                "cùng provider. Đổi provider thì restart với LLM_PROVIDER/LLM_MODEL."
            )
            return

        self._apply(ctx, new)

    async def _pick(self, ctx) -> None:
        """Picker: list model từ API → chọn bằng mũi tên (TTY) / in text (pipe)."""
        window = get_context_window(ctx.model)
        console.print(
            f"[bold]Model:[/] {ctx.provider_name}:{ctx.model} [dim](window {window:,})[/]"
        )
        try:
            raw = await ctx.provider.list_models()
        except Exception as e:
            print_error(f"Không lấy được danh sách model: {e}")
            console.print("[dim]Dùng: /model <tên>[/]")
            return

        base_url = str(getattr(getattr(ctx.provider, "client", None), "base_url", ""))
        official = "api.openai.com" in base_url
        models = selectable_models(ctx.provider_name, raw, ctx.model, official)
        if len(models) <= 1:
            console.print("[dim]API không trả thêm model nào — dùng /model <tên>[/]")
            return

        if not sys.stdin.isatty():
            for name in models:
                marker = "[green]●[/]" if name == ctx.model else " "
                console.print(f"  {marker} {name}")
            console.print("[dim]Chọn: /model <tên>[/]")
            return

        choices = [
            questionary.Choice(
                title=f"{m}  (current)" if m == ctx.model else m, value=m
            )
            for m in models
        ]
        try:
            picked = await questionary.select("Chọn model:", choices=choices).ask_async()
        except Exception as e:
            print_error(f"Prompt failed: {e}")
            return
        if picked is None or picked == ctx.model:
            console.print("[dim]Giữ nguyên model.[/]")
            return
        self._apply(ctx, picked)

    def _apply(self, ctx, new: str) -> None:
        old = ctx.model
        ctx.provider.model = new  # in-place — registry/sub-agent dùng chung instance
        ctx.model = new
        if ctx.cost_tracker is not None:
            ctx.cost_tracker.model = new  # /cost ước tính theo pricing model hiện tại
        window = get_context_window(new)
        console.print(
            f"[green]✓ Model:[/] {old} → [bold]{new}[/] [dim](window {window:,})[/]"
        )
