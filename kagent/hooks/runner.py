"""Hook system — chạy shell command tại lifecycle events.

Events (subset của Claude Code):
  PreToolUse   — trước permission check; exit 2 = block tool, stderr → model
  PostToolUse  — sau khi tool chạy; exit 2 = stderr thành feedback → model
  Stop         — sau khi turn xong; exit 2 = stderr thành user message, turn tiếp tục

Protocol (giữ NGUYÊN field names của Claude Code để hook script dùng chung):
  - Hook nhận JSON payload qua STDIN: {hook_event_name, cwd, session_id, tool_name, ...}
  - exit 0  = OK (stdout hiện dim)
  - exit 2  = BLOCK — stderr là feedback đưa lại cho model
  - khác    = lỗi non-blocking (warning, flow tiếp tục)
  - timeout (default 60s) → kill process group, exit_code 124, KHÔNG block

Settings schema:
  {"hooks": {"PreToolUse": [
      {"matcher": "Bash|Edit", "hooks": [{"type": "command", "command": "...", "timeout": 30}]}
  ]}}
  matcher = regex full-match trên tool name; ""/"*"/thiếu = match tất cả.
  Stop không có tool → matcher bị bỏ qua.

Layering: module này thuộc core — KHÔNG import kagent.ui. Hiển thị
"[hook:...] ..." là việc của UI: composition root (cli.main) inject notifier
callback. Mặc định None → im lặng (đúng cho tests).

Claude Code equivalent: src/utils/hooks/ (hooksConfigManager.ts, hookEvents.ts)
"""

import asyncio
import json
import os
import re
import signal
from dataclasses import dataclass
from typing import Callable

DEFAULT_TIMEOUT = 60.0


@dataclass
class HookResult:
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def blocked(self) -> bool:
        return self.exit_code == 2


def _matcher_matches(matcher: str, tool_name: str) -> bool:
    if matcher in ("", "*"):
        return True
    try:
        return re.fullmatch(matcher, tool_name) is not None
    except re.error:
        return False  # regex hỏng trong settings không được crash REPL


async def _run_one(command: str, payload: dict, timeout: float) -> HookResult:
    proc = await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,  # kill được cả process group khi timeout
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(payload, ensure_ascii=False).encode()),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        await proc.wait()
        return HookResult(command=command, exit_code=124,
                          stderr=f"hook timeout sau {timeout}s")
    return HookResult(
        command=command,
        exit_code=proc.returncode or 0,
        stdout=stdout.decode(errors="replace").strip(),
        stderr=stderr.decode(errors="replace").strip(),
    )


class HookRunner:
    def __init__(
        self,
        settings: dict,
        cwd: str = "",
        session_id_ref: list | None = None,
        notifier: Callable[[str], None] | None = None,
    ):
        self.config: dict = (settings or {}).get("hooks") or {}
        self.cwd = cwd
        self.session_id_ref = session_id_ref  # list-of-1 — /new có thể đổi session
        self.notifier = notifier

    def has(self, event: str) -> bool:
        return bool(self.config.get(event))

    async def run(self, event: str, tool_name: str = "",
                  extra: dict | None = None) -> list[HookResult]:
        entries = self.config.get(event) or []
        if not entries:
            return []
        payload = {
            "hook_event_name": event,
            "cwd": self.cwd,
            "session_id": self.session_id_ref[0] if self.session_id_ref else "",
            **(extra or {}),
        }
        results: list[HookResult] = []
        for entry in entries:
            if event != "Stop" and not _matcher_matches(entry.get("matcher", ""), tool_name):
                continue
            for hook in entry.get("hooks") or []:
                if hook.get("type", "command") != "command" or not hook.get("command"):
                    continue
                timeout = float(hook.get("timeout", DEFAULT_TIMEOUT))
                result = await _run_one(hook["command"], payload, timeout)
                results.append(result)
                self._notify(event, result)
        return results

    def _notify(self, event: str, result: HookResult) -> None:
        if self.notifier is None:
            return
        if result.blocked:
            self.notifier(f"[hook:{event}] blocked (exit 2): {result.stderr[:200]}")
        elif result.exit_code != 0:
            self.notifier(f"[hook:{event}] exit {result.exit_code}: {result.stderr[:200]}")
        elif result.stdout:
            self.notifier(f"[hook:{event}] {result.stdout[:200]}")


def blocked_feedback(results: list[HookResult]) -> str | None:
    """Gom stderr của các hook exit 2. None nếu không hook nào block."""
    msgs = [r.stderr or "(blocked by hook, no stderr)" for r in results if r.blocked]
    return "\n".join(msgs) if msgs else None
