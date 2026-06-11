"""Diff preview cho permission prompt (Edit/Write).

Claude Code equivalent: components/StructuredDiff/ + tools/FileEditTool/UI.tsx
— structured diff render NGAY TRONG approval dialog, user không bao giờ
approve mù một edit.

Tách 2 tầng:
- build_* : pure functions (path + args → text) — unit-testable
- show_permission_preview : render Rich — gọi từ PermissionChecker
"""

import difflib
import os

MAX_PREVIEW_LINES = 60     # diff dài hơn → cắt (đủ nhìn, không tràn màn hình)
MAX_NEW_FILE_LINES = 40    # preview file mới


def _resolve(path: str, cwd: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(cwd, path))


def unified_diff_text(old: str, new: str, path: str) -> str:
    """Unified diff (3 dòng context) — format giống `git diff`."""
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(lines)


def diff_stats(diff_text: str) -> tuple[int, int]:
    """(số dòng thêm, số dòng xóa) — bỏ qua header +++/---."""
    adds = dels = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            adds += 1
        elif line.startswith("-") and not line.startswith("---"):
            dels += 1
    return adds, dels


def truncate_lines(text: str, max_lines: int = MAX_PREVIEW_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    hidden = len(lines) - max_lines
    return "\n".join(lines[:max_lines]) + f"\n... ({hidden} dòng nữa bị ẩn)"


def build_edit_preview(args: dict, cwd: str) -> tuple[str | None, str | None]:
    """Preview cho Edit tool → (diff_text, warning); đúng 1 trong 2 khác None.

    Warning khi edit CHẮC CHẮN sẽ fail (file không có / 0 match / nhiều match)
    — signal tốt để user DENY thay vì approve mù.
    """
    path = _resolve(args.get("file_path", ""), cwd)
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")
    replace_all = args.get("replace_all", False)

    if not os.path.exists(path):
        return None, f"File không tồn tại: {path} — edit sẽ fail"
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        return None, f"Không đọc được file ({e}) — không preview được"

    count = content.count(old_string)
    if count == 0:
        return None, "old_string KHÔNG tìm thấy trong file — edit sẽ fail"
    if count > 1 and not replace_all:
        return None, f"old_string khớp {count} chỗ (không có replace_all) — edit sẽ fail"

    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)
    return unified_diff_text(content, new_content, args.get("file_path", path)), None


def build_write_preview(args: dict, cwd: str) -> tuple[str, bool]:
    """Preview cho Write tool → (text, is_diff).

    File đã tồn tại → unified diff (overwrite — PHẢI thấy sẽ mất gì).
    File mới → head của content.
    """
    path = _resolve(args.get("file_path", ""), cwd)
    content = args.get("content", "")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old = fh.read()
            return unified_diff_text(old, content, args.get("file_path", path)), True
        except (OSError, UnicodeDecodeError):
            pass  # binary/unreadable → fallback hiện content như file mới
    return truncate_lines(content, MAX_NEW_FILE_LINES), False


def _lexer_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext or "text"


def show_permission_preview(tool_name: str, args: dict, cwd: str | None = None) -> None:
    """Render preview trước câu 'Allow?'. Tool khác Edit/Write → no-op.

    Import Rich bên trong function để giữ build_* thuần (test không cần console).
    """
    from rich.syntax import Syntax
    from kagent.ui.terminal import console

    cwd = cwd or os.getcwd()

    if tool_name == "Edit":
        diff, warning = build_edit_preview(args, cwd)
        if warning:
            console.print(f"    [yellow]⚠ {warning}[/]")
            return
        adds, dels = diff_stats(diff)
        console.print(f"    [green]+{adds}[/] [red]-{dels}[/]")
        console.print(Syntax(truncate_lines(diff), "diff", theme="monokai"))

    elif tool_name == "Write":
        text, is_diff = build_write_preview(args, cwd)
        if is_diff:
            adds, dels = diff_stats(text)
            console.print(
                f"    [yellow]⚠ File đã tồn tại — sẽ bị OVERWRITE[/] "
                f"[green]+{adds}[/] [red]-{dels}[/]"
            )
            console.print(Syntax(truncate_lines(text), "diff", theme="monokai"))
        else:
            n_lines = args.get("content", "").count("\n") + 1
            console.print(f"    [dim]File mới ({n_lines} dòng):[/]")
            try:
                console.print(Syntax(text, _lexer_for(args.get("file_path", "")),
                                     theme="monokai", line_numbers=True))
            except Exception:
                console.print(text)  # lexer lạ → in thô
