"""ESC-to-interrupt: watch stdin trong lúc agent loop chạy.

Claude Code: Ink TUI nhận keypress event trực tiếp (screens/REPL.tsx).
kagent không có TUI event loop riêng → cbreak mode + loop.add_reader(stdin)
trong thời gian turn chạy; restore terminal khi xong.

Chỉ hoạt động Unix + TTY thật (termios). Windows / pipe: silent no-op,
user vẫn còn Ctrl+C.

Cẩn thận CONFLICT: input() / questionary cũng đọc stdin → mọi interactive
prompt giữa turn PHẢI pause() trước và resume() sau, nếu không 2 reader
giành nhau từng byte.
"""

import asyncio
import os
import sys

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:  # Windows
    _HAS_TERMIOS = False


class EscWatcher:
    def __init__(self):
        self._fd: int | None = None
        self._saved_attrs = None
        self._on_esc = None
        self._active = False    # start() đã gọi, chưa stop()
        self._attached = False  # cbreak + reader đang bật thật

    @property
    def available(self) -> bool:
        return _HAS_TERMIOS and sys.stdin.isatty()

    def start(self, on_esc) -> None:
        """Bật watcher cho 1 turn. Gọi ngay sau khi tạo turn_task."""
        if not self.available or self._active:
            return
        self._on_esc = on_esc
        self._active = True
        self._attach()

    def stop(self) -> None:
        """Tắt watcher + restore terminal. Gọi trong finally của turn."""
        if not self._active:
            return
        if self._attached:
            self._detach()
        self._active = False
        self._on_esc = None

    def pause(self) -> None:
        """Nhả stdin trước khi prompt interactive (input()/questionary)."""
        if self._active and self._attached:
            self._detach()

    def resume(self) -> None:
        """Lấy lại stdin sau prompt."""
        if self._active and not self._attached:
            self._attach()

    def _attach(self) -> None:
        self._fd = sys.stdin.fileno()
        self._saved_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)  # cbreak: per-key read, GIỮ ISIG (Ctrl+C vẫn ra SIGINT)
        asyncio.get_running_loop().add_reader(self._fd, self._handle_readable)
        self._attached = True

    def _detach(self) -> None:
        asyncio.get_running_loop().remove_reader(self._fd)
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved_attrs)
        self._attached = False

    def _handle_readable(self) -> None:
        try:
            data = os.read(self._fd, 64)
        except OSError:
            return
        # CHỈ nhận ESC đơn — escape sequence (mũi tên = \x1b[A) dài hơn 1 byte
        # nên không match. Phím thường gõ trong lúc turn chạy bị nuốt
        # (chưa có queued-messages như Claude Code — tradeoff đã biết).
        if data == b"\x1b" and self._on_esc is not None:
            self._on_esc()


# Singleton — checker/tools import trực tiếp để pause/resume,
# không cần thread qua tham số function.
esc_watcher = EscWatcher()
