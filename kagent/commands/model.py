"""/model slash command — đổi model trong CÙNG provider đang chạy.

KHÔNG đổi provider: client/API key/base_url giữ nguyên, chỉ mutate
`provider.model` in-place — mọi nơi giữ reference tới provider (tool
registry, sub-agent, compact) tự dùng model mới, không phải rebuild gì.
Đổi chéo provider (gemini ↔ openai) → restart với LLM_PROVIDER/LLM_MODEL
(history lưu normalized nhưng tool_call_id không tương thích chéo API).
"""

from kagent.commands.base import Command
from kagent.conversation import get_context_window
from kagent.ui.terminal import console, print_error


# Google API chỉ serve các family này — chặn sớm typo / model của provider
# khác. openai-compat KHÔNG check được (vLLM/sglang đặt alias tùy ý) → cho qua,
# server tự trả lỗi nếu model không tồn tại.
_GEMINI_PREFIXES = ("gemini", "gemma", "learnlm")


class ModelCommand(Command):
    name = "model"
    description = "Show or switch model (cùng provider only)"
    usage = "[model_name]"

    async def execute(self, args, ctx):
        new = args.strip()
        if not new:
            window = get_context_window(ctx.model)
            console.print(
                f"[bold]Model:[/] {ctx.provider_name}:{ctx.model} "
                f"[dim](window {window:,})[/]"
            )
            console.print("[dim]Đổi: /model <tên> — chỉ trong cùng provider[/]")
            return

        if ctx.provider_name == "gemini" and not new.lower().startswith(_GEMINI_PREFIXES):
            print_error(
                f"'{new}' không thuộc provider gemini — chỉ được đổi model trong "
                "cùng provider. Đổi provider thì restart với LLM_PROVIDER/LLM_MODEL."
            )
            return

        old = ctx.model
        ctx.provider.model = new  # in-place — registry/sub-agent dùng chung instance
        ctx.model = new
        if ctx.cost_tracker is not None:
            ctx.cost_tracker.model = new  # /cost ước tính theo pricing model hiện tại
        window = get_context_window(new)
        console.print(
            f"[green]✓ Model:[/] {old} → [bold]{new}[/] [dim](window {window:,})[/]"
        )
