import os
from pathlib import Path
from kagent.tools.base import Tool, ToolResult, ToolContext


class FileEditTool(Tool):
    """Edit files using string replacement.

    Claude Code equivalent: src/tools/FileEditTool/FileEditTool.ts (20KB)

    Key design: uses exact string matching, NOT line numbers.
    - LLMs are bad at counting lines
    - String matching is precise and self-verifying
    - If match is ambiguous → error guides LLM to add more context
    """

    name = "Edit"
    description = (
        "Edit a file by replacing exact string matches. "
        "Provide old_string (text to find) and new_string (replacement). "
        "The old_string must match exactly one location in the file, "
        "unless replace_all is true. If old_string matches multiple "
        "locations, provide more surrounding context to make it unique."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = self._resolve_path(args["file_path"], context.cwd)
        old_string = args["old_string"]
        new_string = args["new_string"]
        replace_all = args.get("replace_all", False)

        if not os.path.exists(file_path):
            return ToolResult(output="", error=f"File not found: {file_path}", is_error=True)

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(output="", error=f"Error reading file: {e}", is_error=True)

        count = content.count(old_string)
        if count == 0:
            return ToolResult(
                output="",
                error=f"old_string not found in {file_path}. Make sure the string matches exactly (including whitespace and indentation).",
                is_error=True,
            )

        if count > 1 and not replace_all:
            return ToolResult(
                output="",
                error=(
                    f"old_string found {count} times in {file_path}. "
                    "Provide more surrounding context to make it unique, "
                    "or set replace_all=true to replace all occurrences."
                ),
                is_error=True,
            )

        if old_string == new_string:
            return ToolResult(
                output="",
                error="old_string and new_string are identical. No changes needed.",
                is_error=True,
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        try:
            Path(file_path).write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult(output="", error=f"Error writing file: {e}", is_error=True)

        replacements = count if replace_all else 1
        return ToolResult(
            output=f"Edited {file_path}: replaced {replacements} occurrence(s)",
            metadata={"file_path": file_path, "replacements": replacements},
        )

    def _resolve_path(self, path: str, cwd: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(cwd, path))
