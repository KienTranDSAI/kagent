"""Persistent memory — save facts across sessions.

Files: `~/.kagent/memory/{name}.md` (plain markdown, no frontmatter)
Auto-loaded vào system prompt qua `context/__init__.py`.
"""

import re
from pathlib import Path


MEMORY_DIR = Path.home() / ".kagent" / "memory"
SAFE_NAME = re.compile(r"[^a-zA-Z0-9_\-]+")


class MemoryManager:
    def __init__(self, directory: Path = MEMORY_DIR):
        self.dir = directory

    def _path(self, name: str) -> Path:
        safe = SAFE_NAME.sub("_", name).strip("_").lower() or "unnamed"
        return self.dir / f"{safe}.md"

    def save(self, name: str, content: str) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(name)
        path.write_text(content.strip() + "\n", encoding="utf-8")
        return path

    def load(self, name: str) -> str | None:
        path = self._path(name)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def delete(self, name: str) -> bool:
        path = self._path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> list[dict]:
        """Return list of {name, preview, size}."""
        if not self.dir.exists():
            return []
        items = []
        for path in sorted(self.dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
                preview = content.strip().split("\n", 1)[0][:60]
                items.append({
                    "name": path.stem,
                    "preview": preview,
                    "size": len(content),
                })
            except Exception:
                continue
        return items

    def all_content_for_prompt(self) -> str:
        """Concatenate all memories dùng inject vào system prompt."""
        if not self.dir.exists():
            return ""
        parts = []
        for path in sorted(self.dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(f"## {path.stem}\n{content}")
            except Exception:
                continue
        return "\n\n".join(parts)
