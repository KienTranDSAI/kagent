"""Settings system — JSON config 3 tầng, giống Claude Code settings.json.

Precedence (thấp → cao, tầng sau merge đè tầng trước):
  1. ~/.kagent/settings.json        — user (global mọi project)
  2. .kagent/settings.json          — project (commit được, share team)
  3. .kagent/settings.local.json    — project local (gitignore, máy cá nhân)

Merge semantics:
  - dict  → merge đệ quy (key 2 tầng cùng sống)
  - list  → CONCAT (permission rules / hooks từ MỌI tầng đều có hiệu lực,
            giống Claude Code — không phải tầng cao đè tầng thấp)
  - scalar → tầng cao thắng

Layering: module này thuộc core — KHÔNG import kagent.ui. Settings hỏng
báo qua on_warning callback do composition root (cli.main) inject;
mặc định None → im lặng (đúng cho tests/library).

Claude Code equivalent: src/utils/settings/ (constants.ts, applySettingsChange.ts)
"""

import json
from pathlib import Path
from typing import Callable


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        elif isinstance(value, list) and isinstance(out.get(key), list):
            out[key] = out[key] + value
        else:
            out[key] = value
    return out


def settings_paths(cwd: Path | None = None, home: Path | None = None) -> list[Path]:
    """Đường dẫn 3 tầng theo thứ tự merge (THẤP → CAO)."""
    cwd = Path(cwd) if cwd else Path.cwd()
    home = Path(home) if home else Path.home()
    return [
        home / ".kagent" / "settings.json",
        cwd / ".kagent" / "settings.json",
        cwd / ".kagent" / "settings.local.json",
    ]


def load_settings(
    cwd: Path | None = None,
    home: Path | None = None,
    on_warning: Callable[[str], None] | None = None,
) -> dict:
    """Load + merge settings. File thiếu → skip; file hỏng → warning + skip."""
    merged: dict = {}
    for path in settings_paths(cwd, home):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            if on_warning is not None:
                on_warning(f"Bỏ qua {path}: {e}")
            continue
        if isinstance(data, dict):
            merged = _merge(merged, data)
    return merged


def add_permission_rule(
    rule: str,
    kind: str = "allow",
    scope: str = "local",
    cwd: Path | None = None,
    home: Path | None = None,
) -> Path:
    """Persist 1 permission rule. Trả về path đã ghi.

    kind: "allow" | "deny"
    scope: "local" (mặc định — máy này) | "project" | "user"
    """
    cwd = Path(cwd) if cwd else Path.cwd()
    home = Path(home) if home else Path.home()
    path = {
        "local": cwd / ".kagent" / "settings.local.json",
        "project": cwd / ".kagent" / "settings.json",
        "user": home / ".kagent" / "settings.json",
    }[scope]

    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}  # file hỏng → ghi đè bằng config sạch (rule vẫn được lưu)

    rules = data.setdefault("permissions", {}).setdefault(kind, [])
    if rule not in rules:
        rules.append(rule)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path
