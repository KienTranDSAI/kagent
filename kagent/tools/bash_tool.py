import asyncio
import os
import signal
from kagent.tools.base import Tool, ToolResult, ToolContext


def _kill_process_group(proc) -> None:
    """Kill cả process group — proc là `sh -c`, lệnh thật là CON của nó.

    proc.kill() một mình chỉ giết shell, để lại orphan (vd `sleep 30`
    vẫn chạy sau khi user đã ESC). Cần start_new_session=True khi spawn
    để killpg không trúng chính kagent.
    """
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


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
                start_new_session=True,  # group riêng → kill được cả cây process
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                _kill_process_group(proc)
                await proc.wait()
                return ToolResult(
                    output="",
                    error=f"Command timed out after {timeout}s",
                    is_error=True,
                )
            except asyncio.CancelledError:
                # User interrupt (ESC/Ctrl+C) — kill kẻo subprocess mồ côi
                _kill_process_group(proc)
                await proc.wait()
                raise

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
