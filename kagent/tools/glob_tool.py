import os
import glob as glob_module
from kagent.tools.base import Tool, ToolResult, ToolContext


class GlobTool(Tool):
    """Find files by pattern matching.

    Claude Code equivalent: src/tools/GlobTool/GlobTool.ts
    Sort by modification time (newest first) — recently modified files more relevant.
    """

    name = "Glob"
    description = (
        "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts'). "
        "Results sorted by modification time (newest first). "
        "Use this to find files by name, not by content (use Grep for content)."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from. Default: current directory",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        pattern = args["pattern"]
        base_path = args.get("path", context.cwd)

        if not os.path.isabs(base_path):
            base_path = os.path.join(context.cwd, base_path)

        full_pattern = os.path.join(base_path, pattern)

        try:
            matches = glob_module.glob(full_pattern, recursive=True)
        except Exception as e:
            return ToolResult(output="", error=f"Glob error: {e}", is_error=True)

        if not matches:
            return ToolResult(output="No files found matching pattern")

        # Filter out directories — only return files
        matches = [m for m in matches if os.path.isfile(m)]

        if not matches:
            return ToolResult(output="No files found matching pattern")

        # Sort by modification time (newest first)
        try:
            matches.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        except OSError:
            matches.sort()

        # Make paths relative to cwd for readability
        relative = []
        for m in matches:
            try:
                relative.append(os.path.relpath(m, context.cwd))
            except ValueError:
                relative.append(m)

        output = "\n".join(relative)
        return ToolResult(
            output=output,
            metadata={"count": len(matches)},
        )

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return True
