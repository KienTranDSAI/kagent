"""Tests cho diff preview (pure functions — không cần TTY)."""

from kagent.ui.diff_preview import (
    build_edit_preview,
    build_write_preview,
    diff_stats,
    truncate_lines,
)


def test_edit_preview_produces_diff(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\ny = 2\n", encoding="utf-8")
    diff, warn = build_edit_preview(
        {"file_path": str(f), "old_string": "x = 1", "new_string": "x = 42"},
        cwd=str(tmp_path),
    )
    assert warn is None
    assert "-x = 1" in diff
    assert "+x = 42" in diff
    assert "y = 2" in diff  # context line


def test_edit_preview_relative_path_resolved(tmp_path):
    (tmp_path / "b.txt").write_text("hello\n", encoding="utf-8")
    diff, warn = build_edit_preview(
        {"file_path": "b.txt", "old_string": "hello", "new_string": "hi"},
        cwd=str(tmp_path),
    )
    assert warn is None and "+hi" in diff


def test_edit_preview_no_match_warns(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    diff, warn = build_edit_preview(
        {"file_path": str(f), "old_string": "KHÔNG CÓ", "new_string": "z"},
        cwd=str(tmp_path),
    )
    assert diff is None
    assert "fail" in warn


def test_edit_preview_multi_match_warns(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("foo\nfoo\n", encoding="utf-8")
    diff, warn = build_edit_preview(
        {"file_path": str(f), "old_string": "foo", "new_string": "bar"},
        cwd=str(tmp_path),
    )
    assert diff is None
    assert "2" in warn


def test_edit_preview_replace_all_ok(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("foo\nfoo\n", encoding="utf-8")
    diff, warn = build_edit_preview(
        {"file_path": str(f), "old_string": "foo", "new_string": "bar", "replace_all": True},
        cwd=str(tmp_path),
    )
    assert warn is None
    assert diff.count("+bar") == 2


def test_edit_preview_missing_file(tmp_path):
    diff, warn = build_edit_preview(
        {"file_path": str(tmp_path / "nope.py"), "old_string": "a", "new_string": "b"},
        cwd=str(tmp_path),
    )
    assert diff is None
    assert "không tồn tại" in warn.lower()


def test_write_preview_new_file(tmp_path):
    text, is_diff = build_write_preview(
        {"file_path": str(tmp_path / "new.py"), "content": "print(1)\n"},
        cwd=str(tmp_path),
    )
    assert is_diff is False
    assert "print(1)" in text


def test_write_preview_existing_file_shows_diff(tmp_path):
    f = tmp_path / "old.py"
    f.write_text("old line\n", encoding="utf-8")
    text, is_diff = build_write_preview(
        {"file_path": str(f), "content": "new line\n"},
        cwd=str(tmp_path),
    )
    assert is_diff is True
    assert "-old line" in text
    assert "+new line" in text


def test_diff_stats():
    diff = "--- a/x\n+++ b/x\n@@ -1 +1,2 @@\n-old\n+new\n+more\n"
    adds, dels = diff_stats(diff)
    assert (adds, dels) == (2, 1)


def test_truncate_lines():
    text = "\n".join(str(i) for i in range(100))
    out = truncate_lines(text, max_lines=10)
    assert out.splitlines()[0] == "0"
    assert "90 dòng" in out  # 100 - 10 hidden
    assert len(out.splitlines()) == 11  # 10 + dòng "..."
