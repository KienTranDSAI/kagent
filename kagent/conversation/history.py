"""Session persistence — lưu conversation ra disk để resume sau.

Format: JSON files trong ~/.kagent/sessions/{session_id}.json
Override path qua env var KAGENT_SESSIONS_DIR.
"""

import json
import os
import uuid
from pathlib import Path
from datetime import datetime


def _sessions_dir() -> Path:
    override = os.getenv("KAGENT_SESSIONS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".kagent" / "sessions"


SESSIONS_DIR = _sessions_dir()


def new_session_id() -> str:
    """Tạo session id mới: YYYYMMDD-HHMMSS-xxxxxx."""
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def save_session(session_id: str, messages: list[dict], metadata: dict | None = None) -> Path:
    """Lưu conversation ra disk. Overwrite nếu đã có."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{session_id}.json"

    data = {
        "session_id": session_id,
        "updated": datetime.now().isoformat(timespec="seconds"),
        "messages": messages,
        "metadata": metadata or {},
    }

    if path.exists():
        try:
            old = json.loads(path.read_text())
            if "created" in old:
                data["created"] = old["created"]
        except Exception:
            pass

    data.setdefault("created", data["updated"])
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    return path


def load_session(session_id: str) -> list[dict] | None:
    """Load messages từ session. Return None nếu không tồn tại."""
    path = SESSIONS_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("messages", [])
    except Exception:
        return None


def list_sessions(limit: int = 10) -> list[dict]:
    """List N sessions gần nhất. Mỗi entry có id, updated, messages count."""
    if not SESSIONS_DIR.exists():
        return []

    entries = []
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            entries.append({
                "id": data.get("session_id", path.stem),
                "created": data.get("created", ""),
                "updated": data.get("updated", ""),
                "messages": len(data.get("messages", [])),
                "first_user": _first_user_message(data.get("messages", [])),
            })
        except Exception:
            continue

    entries.sort(key=lambda e: e["updated"], reverse=True)
    return entries[:limit]


def delete_session(session_id: str) -> bool:
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def _first_user_message(messages: list[dict]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                snippet = content.strip().replace("\n", " ")
                return snippet[:60] + ("..." if len(snippet) > 60 else "")
    return ""
