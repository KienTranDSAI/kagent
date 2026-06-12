"""Tests cho custom slash commands — .kagent/commands/*.md."""

from types import SimpleNamespace

from kagent.commands.custom import (
    CustomCommand,
    load_custom_commands,
    parse_frontmatter,
    substitute_arguments,
)


# ── parse_frontmatter ───────────────────────────────────────

def test_frontmatter_parsed_and_stripped():
    text = "---\ndescription: Deploy app\nargument-hint: [env]\n---\nDeploy lên $ARGUMENTS"
    meta, body = parse_frontmatter(text)
    assert meta == {"description": "Deploy app", "argument-hint": "[env]"}
    assert body == "Deploy lên $ARGUMENTS"


def test_no_frontmatter_returns_full_body():
    assert parse_frontmatter("Just a prompt") == ({}, "Just a prompt")


def test_unclosed_frontmatter_treated_as_body():
    text = "---\ndescription: x\nno closing"
    meta, body = parse_frontmatter(text)
    assert meta == {} and body == text


# ── substitute_arguments ────────────────────────────────────

def test_arguments_placeholder_replaced():
    assert substitute_arguments("Fix $ARGUMENTS now", "engine.py") == "Fix engine.py now"


def test_args_appended_when_no_placeholder():
    out = substitute_arguments("Review the diff", "use Vietnamese")
    assert out == "Review the diff\n\nARGUMENTS: use Vietnamese"


def test_no_args_no_append():
    assert substitute_arguments("Review the diff", "") == "Review the diff"


# ── load_custom_commands ────────────────────────────────────

def _write_cmd(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(text, encoding="utf-8")


def test_load_project_overrides_user(tmp_path):
    user, project = tmp_path / "user_cmds", tmp_path / "proj_cmds"
    _write_cmd(user, "deploy", "user version")
    _write_cmd(user, "review", "---\ndescription: Review code\n---\nreview body")
    _write_cmd(project, "deploy", "project version")
    cmds = {c.name: c for c in load_custom_commands(project_dir=project, user_dir=user)}
    assert cmds["deploy"].body == "project version"   # project đè user
    assert cmds["review"].description == "Review code"


def test_empty_body_skipped(tmp_path):
    project = tmp_path / "cmds"
    _write_cmd(project, "blank", "---\ndescription: x\n---\n")
    assert load_custom_commands(project_dir=project, user_dir=tmp_path / "nope") == []


# ── execute → pending_prompt ────────────────────────────────

async def test_execute_sets_pending_prompt():
    cmd = CustomCommand(name="fix", body="Fix $ARGUMENTS carefully")
    ctx = SimpleNamespace(pending_prompt=[None])
    await cmd.execute("engine.py", ctx)
    assert ctx.pending_prompt[0] == "Fix engine.py carefully"
