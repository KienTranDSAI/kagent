"""Tests cho settings system — load/merge 3 tầng + persist rule."""

import json

from kagent.settings import load_settings, add_permission_rule


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_load_missing_files_returns_empty(tmp_path):
    assert load_settings(cwd=tmp_path / "proj", home=tmp_path / "home") == {}


def test_precedence_local_beats_project_beats_user(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    _write(home / ".kagent" / "settings.json", {"theme": "user", "verbose": True})
    _write(cwd / ".kagent" / "settings.json", {"theme": "project"})
    _write(cwd / ".kagent" / "settings.local.json", {"theme": "local"})
    s = load_settings(cwd=cwd, home=home)
    assert s["theme"] == "local"      # scalar: tầng cao thắng
    assert s["verbose"] is True       # key chỉ có ở user vẫn sống


def test_permission_lists_concat_all_layers(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    _write(home / ".kagent" / "settings.json",
           {"permissions": {"allow": ["Bash(git status:*)"]}})
    _write(cwd / ".kagent" / "settings.json",
           {"permissions": {"allow": ["Edit(*.py)"], "deny": ["Read(.env)"]}})
    _write(cwd / ".kagent" / "settings.local.json",
           {"permissions": {"allow": ["Bash(pytest:*)"]}})
    s = load_settings(cwd=cwd, home=home)
    # List CONCAT mọi tầng — rule từ user + project + local đều có hiệu lực
    assert s["permissions"]["allow"] == [
        "Bash(git status:*)", "Edit(*.py)", "Bash(pytest:*)",
    ]
    assert s["permissions"]["deny"] == ["Read(.env)"]


def test_nested_dict_merge_keeps_sibling_keys(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    _write(home / ".kagent" / "settings.json",
           {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}})
    _write(cwd / ".kagent" / "settings.json",
           {"hooks": {"Stop": [{"hooks": []}]}})
    s = load_settings(cwd=cwd, home=home)
    assert "PreToolUse" in s["hooks"] and "Stop" in s["hooks"]


def test_corrupted_json_skipped_with_warning(tmp_path):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    bad = cwd / ".kagent" / "settings.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{not json", encoding="utf-8")
    _write(home / ".kagent" / "settings.json", {"theme": "user"})
    warnings: list[str] = []
    s = load_settings(cwd=cwd, home=home, on_warning=warnings.append)
    assert s == {"theme": "user"}     # tầng hỏng bị bỏ qua, tầng khác vẫn load
    assert len(warnings) == 1 and "settings.json" in warnings[0]


def test_add_permission_rule_creates_appends_no_dup(tmp_path):
    cwd = tmp_path / "proj"
    path = add_permission_rule("Bash(git push:*)", kind="allow", scope="local", cwd=cwd)
    assert path == cwd / ".kagent" / "settings.local.json"
    add_permission_rule("Bash(git push:*)", kind="allow", scope="local", cwd=cwd)  # dup
    add_permission_rule("Read(.env)", kind="deny", scope="local", cwd=cwd)
    data = json.loads(path.read_text())
    assert data["permissions"]["allow"] == ["Bash(git push:*)"]  # không dup
    assert data["permissions"]["deny"] == ["Read(.env)"]
