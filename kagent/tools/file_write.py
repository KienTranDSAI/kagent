import os
from pathlib import Path
from kagent.tools.base import Tool, ToolResult, ToolContext


class FileWriteTool(Tool):
    """Create new files or overwrite existing ones.

    Claude Code equivalent: src/tools/FileWriteTool/FileWriteTool.ts
    """

    name = "Write"
    description = (
        "Write content to a file. Creates parent directories if needed. "
        "Overwrites existing file content. For modifying existing files, "
        "prefer Edit tool instead."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = self._resolve_path(args["file_path"], context.cwd)
        content = args["content"]

        try:
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            Path(file_path).write_text(content, encoding="utf-8")

            line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            return ToolResult(
                output=f"Successfully wrote {line_count} lines to {file_path}",
                metadata={"file_path": file_path},
            )
        except Exception as e:
            return ToolResult(output="", error=f"Error writing file: {e}", is_error=True)

    def _resolve_path(self, path: str, cwd: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(cwd, path))
