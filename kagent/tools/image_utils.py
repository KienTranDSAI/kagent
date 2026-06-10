"""Image helpers — validate magic bytes + base64 encode."""

import base64
import os
from pathlib import Path

IMAGE_MAX_SIZE = 10 * 1024 * 1024   # 10 MB

# Map extension → MIME (lowercase)
IMAGE_MIME = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}

# Magic bytes signature (header)
IMAGE_MAGIC = {
    "image/png":  b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
    "image/gif":  b"GIF8",
    "image/webp": b"RIFF",   # plus "WEBP" at offset 8 — skip for simplicity
}


def get_image_mime(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    return IMAGE_MIME.get(ext)


def validate_image(file_path: str) -> tuple[bool, str | None]:
    if not os.path.exists(file_path):
        return False, f"Image not found: {file_path}"
    if os.path.isdir(file_path):
        return False, f"Path is a directory: {file_path}"

    size = os.path.getsize(file_path)
    if size == 0:
        return False, f"Image file is empty: {file_path}"
    if size > IMAGE_MAX_SIZE:
        return False, f"Image too large ({size / 1024 / 1024:.1f} MB > 10 MB)"

    mime = get_image_mime(file_path)
    if mime is None:
        return False, f"Unsupported image extension: {Path(file_path).suffix}"

    with open(file_path, "rb") as f:
        header = f.read(8)
    expected = IMAGE_MAGIC.get(mime)
    if expected is not None and not header.startswith(expected):
        return False, f"File header does not match {mime} signature"

    return True, None


def read_image_base64(file_path: str) -> tuple[str, str]:
    """Returns (base64_data, mime_type). Assumes validate_image passed."""
    mime = get_image_mime(file_path)
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return b64, mime
