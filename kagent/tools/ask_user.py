"""AskUserQuestion tool: interactive multiple-choice prompt.

Claude Code equivalent: src/tools/AskUserQuestionTool/AskUserQuestionTool.tsx
Scope: Standard (single question, 2-4 options, multiSelect, auto 'Other').
"""

import questionary
from prompt_toolkit.styles import Style

from kagent.tools.base import Tool, ToolResult, ToolContext
from kagent.ui.interrupt import esc_watcher
from kagent.ui.terminal import console


_QUESTIONARY_STYLE = Style.from_dict({
    "qmark": "fg:#5fafff bold",
    "question": "bold",
    "pointer": "fg:#5fafff bold",
    "highlighted": "fg:#5fafff bold",
    "selected": "fg:#5fafd7",
    "answer": "fg:#5fafd7 bold",
})

_OTHER_SENTINEL = "__OTHER__"


class AskUserQuestionTool(Tool):
    name = "AskUserQuestion"
    description = (
        "Ask the user a multiple-choice question to gather preferences, "
        "clarify ambiguity, or get a decision before continuing. "
        "Use when there's a non-obvious choice the user should make. "
        "Provide 2-4 distinct options; an 'Other' free-text option is "
        "added automatically. Set multiSelect=true if more than one "
        "option may apply."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "The full question to ask. Should be clear, "
                        "specific, and end with '?'."
                    ),
                },
                "header": {
                    "type": "string",
                    "description": (
                        "Very short label (<=12 chars) shown as a chip. "
                        "Examples: 'Library', 'Scope', 'Approach'."
                    ),
                },
                "options": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 4,
                    "description": "2-4 distinct, mutually exclusive choices.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Short option label (1-5 words).",
                            },
                            "description": {
                                "type": "string",
                                "description": "Explanation of the option, shown inline.",
                            },
                        },
                        "required": ["label", "description"],
                    },
                },
                "multiSelect": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow selecting multiple options.",
                },
            },
            "required": ["question", "header", "options"],
        }

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        # Needs exclusive terminal access — never batch in parallel.
        return False

    def bypasses_spinner(self) -> bool:
        return True

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        question = args.get("question", "").strip()
        header = args.get("header", "").strip()
        options = args.get("options", [])
        multi_select = bool(args.get("multiSelect", False))

        if not question:
            return ToolResult(output="", error="Missing 'question'", is_error=True)
        if not (2 <= len(options) <= 4):
            return ToolResult(
                output="",
                error=f"Need 2-4 options, got {len(options)}",
                is_error=True,
            )

        choices = []
        for o in options:
            label = str(o.get("label", "")).strip()
            desc = str(o.get("description", "")).strip()
            if not label:
                return ToolResult(
                    output="", error="Option missing 'label'", is_error=True
                )
            title = f"{label} — {desc}" if desc else label
            choices.append(questionary.Choice(title=title, value=label))
        choices.append(
            questionary.Choice(title="Other (type your own answer)", value=_OTHER_SENTINEL)
        )

        chip = header[:12] if header else "Question"
        console.print(f"\n[cyan]┌─[/] [bold cyan]{chip}[/]")
        console.print(f"[bold]{question}[/]\n")

        # questionary (prompt_toolkit raw mode) cần độc quyền stdin —
        # pause ESC watcher suốt block prompt, kể cả phần "Other" free text.
        esc_watcher.pause()
        try:
            try:
                if multi_select:
                    picked = await questionary.checkbox(
                        "Select one or more (space to toggle, enter to confirm):",
                        choices=choices,
                        style=_QUESTIONARY_STYLE,
                    ).ask_async()
                else:
                    picked = await questionary.select(
                        "Choose:",
                        choices=choices,
                        style=_QUESTIONARY_STYLE,
                    ).ask_async()
            except Exception as e:
                return ToolResult(
                    output="",
                    error=f"Prompt failed: {e}",
                    is_error=True,
                )

            if picked is None or (isinstance(picked, list) and len(picked) == 0):
                return ToolResult(
                    output="[User cancelled the question without answering]",
                    is_error=True,
                )

            # Resolve "Other" → free text
            if multi_select:
                assert isinstance(picked, list)
                if _OTHER_SENTINEL in picked:
                    picked = [p for p in picked if p != _OTHER_SENTINEL]
                    custom = await questionary.text(
                        "Your custom answer:", style=_QUESTIONARY_STYLE
                    ).ask_async()
                    if custom:
                        picked.append(custom.strip())
            else:
                if picked == _OTHER_SENTINEL:
                    custom = await questionary.text(
                        "Your custom answer:", style=_QUESTIONARY_STYLE
                    ).ask_async()
                    if custom is None or not custom.strip():
                        return ToolResult(
                            output="[User cancelled the custom answer]",
                            is_error=True,
                        )
                    picked = custom.strip()
        finally:
            esc_watcher.resume()

        answer_str = ", ".join(picked) if isinstance(picked, list) else picked
        return ToolResult(
            output=f'User answered the question "{question}" with: {answer_str}',
            metadata={"question": question, "answer": picked},
        )
