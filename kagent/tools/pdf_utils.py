"""PDF helpers — validate, base64, page extraction.

Mirrors claude-code/src/utils/pdf.ts.

Three paths:
- Native: read raw → base64 → document block (caller: provider supports PDF)
- Image fallback: pdftoppm → list of JPEG bytes → image blocks
- Text fallback: pypdf → extract text-layer string (no multimodal)
"""

import base64
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

PDF_MAGIC = b"%PDF-"
PDF_MAX_SIZE = 20 * 1024 * 1024            # 20 MB — native limit (Anthropic ~32MB request)
PDF_EXTRACT_MAX_SIZE = 100 * 1024 * 1024   # 100 MB — fallback path (client-side render)
PDF_MAX_PAGES_PER_READ = 20                # hard cap khi user dùng pages="..."

_pdftoppm_available: bool | None = None


def validate_pdf(file_path: str) -> tuple[bool, str | None]:
    """Check exists + size + magic bytes. Returns (ok, error_message)."""
    if not os.path.exists(file_path):
        return False, f"PDF not found: {file_path}"
    if os.path.isdir(file_path):
        return False, f"Path is a directory: {file_path}"

    size = os.path.getsize(file_path)
    if size == 0:
        return False, f"PDF file is empty: {file_path}"
    if size > PDF_EXTRACT_MAX_SIZE:
        return False, f"PDF too large ({size / 1024 / 1024:.1f} MB > 100 MB)"

    with open(file_path, "rb") as f:
        header = f.read(5)
    if not header.startswith(PDF_MAGIC):
        return False, f"Not a valid PDF (missing %PDF- header): {file_path}"

    return True, None


def read_pdf_base64(file_path: str) -> str:
    """Read entire PDF and return base64-encoded string. Assumes validated."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def is_pdftoppm_available() -> bool:
    """Check pdftoppm binary (poppler-utils). Cached per-process."""
    global _pdftoppm_available
    if _pdftoppm_available is not None:
        return _pdftoppm_available
    _pdftoppm_available = shutil.which("pdftoppm") is not None
    return _pdftoppm_available


def pdf_to_jpeg_pages(
    file_path: str,
    dpi: int = 100,
    first_page: int | None = None,
    last_page: int | None = None,
) -> list[bytes]:
    """Render PDF → list of JPEG bytes via pdftoppm subprocess.

    Raises RuntimeError on missing binary / timeout / password / corrupt.
    """
    if not is_pdftoppm_available():
        raise RuntimeError(
            "pdftoppm not installed. Install poppler-utils: "
            "`brew install poppler` (macOS) or `apt-get install poppler-utils` (Linux)."
        )

    with tempfile.TemporaryDirectory(prefix="pdf-render-") as outdir:
        prefix = os.path.join(outdir, "page")
        args = ["pdftoppm", "-jpeg", "-r", str(dpi)]
        if first_page is not None:
            args += ["-f", str(first_page)]
        if last_page is not None:
            args += ["-l", str(last_page)]
        args += [file_path, prefix]

        try:
            result = subprocess.run(args, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise RuntimeError("pdftoppm timed out after 120s")

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            low = stderr.lower()
            if "password" in low:
                raise RuntimeError("PDF is password-protected")
            if any(w in low for w in ("damaged", "corrupt", "invalid")):
                raise RuntimeError(f"PDF is corrupted: {stderr.strip()}")
            raise RuntimeError(f"pdftoppm failed: {stderr.strip()}")

        pages = sorted(Path(outdir).glob("page-*.jpg"))
        if not pages:
            raise RuntimeError("pdftoppm produced no output pages")
        return [p.read_bytes() for p in pages]


def extract_pdf_text(file_path: str) -> str:
    """Extract text-layer via pypdf. Empty string nếu PDF là scan (no text layer)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")

    reader = PdfReader(file_path)
    pages_text = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages_text.append(f"--- Page {i} ---\n{text}")
    return "\n\n".join(pages_text)


def parse_pdf_page_range(range_str: str) -> tuple[int, int] | None:
    """Parse '1-5', '3', '10-20' → (start, end). 1-based inclusive.
    Returns None nếu invalid (empty, reversed, zero, non-digit, comma list, ...).
    """
    if not isinstance(range_str, str):
        return None
    s = range_str.strip()
    if not s:
        return None
    if s.isdigit():
        n = int(s)
        if n < 1:
            return None
        return (n, n)
    m = re.match(r"^(\d+)-(\d+)$", s)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a < 1 or b < a:
        return None
    return (a, b)


def get_pdf_page_count(file_path: str) -> int:
    """Total pages via pypdf. Raises RuntimeError nếu pypdf missing hoặc parse fail."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")
    try:
        return len(PdfReader(file_path).pages)
    except Exception as e:
        raise RuntimeError(f"Failed to read PDF page count: {e}")


def get_pdf_size(file_path: str) -> int:
    return os.path.getsize(file_path)


def format_pdf_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
