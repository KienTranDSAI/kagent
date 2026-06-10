import asyncio
import os
from kagent.tools.base import Tool, ToolResult, ToolContext


class GrepTool(Tool):
    """Search file contents using ripgrep.

    Claude Code equivalent: src/tools/GrepTool/GrepTool.ts
    Requires ripgrep (rg) installed: brew install ripgrep
    """

    name = "Grep"
    description = (
        "Search for text patterns in files using ripgrep. "
        "Supports regex patterns. Use glob parameter to filter file types. "
        "Returns matching lines with file paths and line numbers."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in. Default: current directory",
                },
                "glob": {
                    "type": "string",
                    "description": "File pattern filter (e.g., '*.py', '*.{ts,tsx}')",
                },
                "head_limit": {
                    "type": "number",
                    "description": "Max number of result lines to return. Default: 250",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case insensitive search. Default: false",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        pattern = args["pattern"]
        path = args.get("path", context.cwd)
        glob_pattern = args.get("glob")
        head_limit = int(args.get("head_limit", 250))
        case_insensitive = args.get("case_insensitive", False)

        if not os.path.isabs(path):
            path = os.path.join(context.cwd, path)

        # Build ripgrep command
        cmd = ["rg", "--no-heading", "--line-number"]

        if case_insensitive:
            cmd.append("-i")
        if glob_pattern:
            cmd.extend(["--glob", glob_pattern])

        cmd.extend([pattern, path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        except FileNotFoundError:
            return ToolResult(
                output="",
                error="ripgrep (rg) not installed. Install with: brew install ripgrep",
                is_error=True,
            )
        except asyncio.TimeoutError:
            return ToolResult(output="", error="Search timed out after 30s", is_error=True)

        output = stdout.decode("utf-8", errors="replace")
        lines = output.splitlines()

        # Apply head_limit
        total = len(lines)
        if total > head_limit:
            lines = lines[:head_limit]
            lines.append(f"\n... ({total} total matches, showing first {head_limit})")

        result = "\n".join(lines)
        return ToolResult(
            output=result or "No matches found",
            metadata={"total_matches": total},
        )

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return True
