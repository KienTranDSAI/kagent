"""Jupyter Notebook helpers — parse + format cells.

Mirrors claude-code/src/utils/notebook.ts.
Output là text (không multimodal) — đơn giản hóa Phase 15.
Image outputs (matplotlib plot) chuyển thành placeholder "[image output png, ~12 KB]".
"""
import json
import os

NOTEBOOK_MAX_SIZE = 10 * 1024 * 1024      # 10 MB raw JSON
LARGE_OUTPUT_THRESHOLD = 10_000            # chars per output before truncate


def validate_notebook(file_path: str) -> tuple[bool, str | None]:
    if not os.path.exists(file_path):
        return False, f"Notebook not found: {file_path}"
    if os.path.isdir(file_path):
        return False, f"Path is a directory: {file_path}"
    size = os.path.getsize(file_path)
    if size == 0:
        return False, "Notebook is empty"
    if size > NOTEBOOK_MAX_SIZE:
        return False, f"Notebook too large ({size / 1024 / 1024:.1f} MB > 10 MB)"
    return True, None


def _join_source(src) -> str:
    """Cell source có thể là string hoặc list of strings (jupyter format)."""
    if isinstance(src, list):
        return "".join(s for s in src if isinstance(s, str))
    if isinstance(src, str):
        return src
    return ""


def _truncate(s: str) -> str:
    if len(s) > LARGE_OUTPUT_THRESHOLD:
        return s[:LARGE_OUTPUT_THRESHOLD] + f"\n[... truncated {len(s) - LARGE_OUTPUT_THRESHOLD} chars]"
    return s


def _format_output(out: dict) -> str:
    """Convert one cell output → text. Image outputs → placeholder metadata."""
    otype = out.get("output_type")
    if otype == "stream":
        name = out.get("name", "stdout")
        text = _join_source(out.get("text"))
        return f"[stream {name}] {_truncate(text)}"
    if otype in ("execute_result", "display_data"):
        data = out.get("data") or {}
        text = _join_source(data.get("text/plain"))
        chunks = []
        if text.strip():
            chunks.append(f"[{otype}] {_truncate(text)}")
        for mime in ("image/png", "image/jpeg"):
            if mime in data:
                b64 = data[mime]
                # base64 → raw bytes ≈ len * 3/4
                raw_bytes = len(b64) * 3 // 4 if isinstance(b64, str) else 0
                chunks.append(f"[image output {mime}, ~{raw_bytes // 1024} KB]")
        return "\n".join(chunks) if chunks else f"[{otype}] (no extractable content)"
    if otype == "error":
        ename = out.get("ename", "Error")
        evalue = out.get("evalue", "")
        tb = "\n".join(out.get("traceback") or [])
        return f"[error] {ename}: {evalue}\n{_truncate(tb)}"
    return f"[{otype or 'unknown'}] (unhandled output type)"


def read_notebook(file_path: str) -> list[dict]:
    """Parse .ipynb → list of normalized cell dicts.

    Each cell: {idx, cell_type, source, outputs: list[str]}
    Raises json.JSONDecodeError nếu file không phải JSON hợp lệ.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    cells_out: list[dict] = []
    for idx, cell in enumerate(nb.get("cells", [])):
        cells_out.append({
            "idx": idx,
            "cell_type": cell.get("cell_type", "unknown"),
            "source": _join_source(cell.get("source")),
            "outputs": [_format_output(o) for o in (cell.get("outputs") or [])],
        })
    return cells_out


def format_notebook_text(cells: list[dict]) -> str:
    """Render parsed cells → human-readable text for LLM."""
    lines: list[str] = []
    for c in cells:
        lines.append(f"\n[Cell {c['idx'] + 1}: {c['cell_type']}]")
        lines.append(c["source"].rstrip() or "(empty)")
        if c["outputs"]:
            lines.append("--- outputs ---")
            for o in c["outputs"]:
                lines.append(f"  {o}")
    return "\n".join(lines).strip()


def count_cells_by_type(cells: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        out[c["cell_type"]] = out.get(c["cell_type"], 0) + 1
    return out
