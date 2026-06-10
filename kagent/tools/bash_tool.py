import asyncio
import os
from kagent.tools.base import Tool, ToolResult, ToolContext


class BashTool(Tool):
    """Execute shell commands.

    Claude Code equivalent: src/tools/BashTool/BashTool.tsx (1,143 lines)

    Simplified version. Features to add later:
    - run_in_background (Phase 7)
    - sandbox mode (Phase 6)
    - read-only detection (Phase 6)
    - sed simulation (not needed, we have FileEditTool)
    """

    name = "Bash"
    description = (
        "Execute a shell command and return its output (stdout + stderr). "
        "Use for: git commands, running tests, installing packages, "
        "system operations. Do NOT use for reading files (use Read) "
        "or searching code (use Grep)."
    )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds. Default: 120",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of what this command does",
                },
            },
            "required": ["command"],
        }

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 120)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.cwd,
                env={**os.environ},  # Inherit environment
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    output="",
                    error=f"Command timed out after {timeout}s",
                    is_error=True,
                )

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Combine output
            output_parts = []
            if stdout_str.strip():
                output_parts.append(stdout_str)
            if stderr_str.strip():
                output_parts.append(f"STDERR:\n{stderr_str}")

            output = "\n".join(output_parts) or "(no output)"

            # Truncate very long output (prevent context bloat)
            MAX_OUTPUT = 50_000  # ~12K tokens
            if len(output) > MAX_OUTPUT:
                output = output[:MAX_OUTPUT] + f"\n... (truncated, {len(output)} total chars)"

            if proc.returncode != 0:
                return ToolResult(
                    output=output,
                    error=f"Command exited with code {proc.returncode}",
                    is_error=True,
                    metadata={"exit_code": proc.returncode},
                )

            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(output="", error=str(e), is_error=True)

    def is_read_only(self) -> bool:
        # Bash can do anything — not read-only
        # Phase 6: detect read-only commands like ls, cat, git log
        return False
