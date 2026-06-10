import base64
import json
import os
from pathlib import Path

from kagent.tools.base import Tool, ToolResult, ToolContext
from kagent.tools.pdf_utils import (
    validate_pdf, read_pdf_base64, pdf_to_jpeg_pages,
    extract_pdf_text, get_pdf_size, format_pdf_size,
    parse_pdf_page_range, get_pdf_page_count,
    PDF_MAX_SIZE, PDF_MAX_PAGES_PER_READ,
)
from kagent.tools.image_utils import validate_image, read_image_base64
from kagent.tools.notebook_utils import (
    validate_notebook, read_notebook,
    format_notebook_text, count_cells_by_type,
)


PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
NOTEBOOK_EXTS = {".ipynb"}


class FileReadTool(Tool):
    """Read file. Text by default. PDF/image returned as multimodal content_blocks.

    Claude Code equivalent: src/tools/FileReadTool/FileReadTool.ts
    """

    name = "Read"
    description = (
        "Read a file from disk. Text files return content with line numbers. "
        "PDF and image files return multimodal content blocks — the model sees "
        "them directly (no manual extraction needed). "
        "Use offset and limit for large text files."
    )

    def __init__(self, provider=None):
        # provider needed for capability detection — fall back to text-only if None
        self.provider = provider

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "offset": {
                    "type": "number",
                    "description": "Line number to start reading from (0-based). Default: 0 (text only)",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of lines to read. Default: 2000 (text only)",
                },
                "pages": {
                    "type": "string",
                    "description": (
                        "PDF page range, e.g. '3' or '1-5'. Max 20 pages per call. "
                        "Forces image-based fallback (loses vector layout) so non-native PDF "
                        "providers can still read subsets of long documents."
                    ),
                },
            },
            "required": ["file_path"],
        }

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = self._resolve_path(args["file_path"], context.cwd)
        ext = Path(file_path).suffix.lower()

        if ext in NOTEBOOK_EXTS:
            return self._read_notebook(file_path)
        if ext in PDF_EXTS:
            return self._read_pdf(file_path, args.get("pages"))
        if ext in IMAGE_EXTS:
            return self._read_image(file_path)
        return self._read_text(file_path, args)

    # ---------- Notebook ----------

    def _read_notebook(self, file_path: str) -> ToolResult:
        ok, err = validate_notebook(file_path)
        if not ok:
            return ToolResult(output="", error=err, is_error=True)
        try:
            cells = read_notebook(file_path)
        except json.JSONDecodeError as e:
            return ToolResult(
                output="",
                error=f"Invalid notebook JSON: {e}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                output="",
                error=f"Notebook parse error: {e}",
                is_error=True,
            )

        counts = count_cells_by_type(cells)
        summary = ", ".join(f"{n} {t}" for t, n in counts.items()) or "0 cells"
        text = format_notebook_text(cells)
        header = f"Notebook: {len(cells)} cells ({summary})"
        body = f"{header}\n\n{text}" if text else header
        return ToolResult(
            output=body,
            metadata={
                "file_path": file_path,
                "cell_count": len(cells),
                "cell_types": counts,
            },
        )

    # ---------- PDF ----------

    def _read_pdf(self, file_path: str, pages: str | None = None) -> ToolResult:
        ok, err = validate_pdf(file_path)
        if not ok:
            return ToolResult(output="", error=err, is_error=True)

        # Parse + validate page range (nếu có)
        page_range: tuple[int, int] | None = None
        if pages:
            page_range = parse_pdf_page_range(pages)
            if page_range is None:
                return ToolResult(
                    output="",
                    error=f"Invalid page range '{pages}'. Use '3' or '1-5' (1-based, end >= start).",
                    is_error=True,
                )
            start, end = page_range
            requested = end - start + 1
            if requested > PDF_MAX_PAGES_PER_READ:
                return ToolResult(
                    output="",
                    error=(
                        f"Page range exceeds max {PDF_MAX_PAGES_PER_READ} pages "
                        f"({requested} requested). Split into smaller ranges."
                    ),
                    is_error=True,
                )
            try:
                total = get_pdf_page_count(file_path)
            except RuntimeError:
                total = None
            if total is not None and start > total:
                return ToolResult(
                    output="",
                    error=f"Start page {start} > total pages {total}",
                    is_error=True,
                )

        size = get_pdf_size(file_path)
        provider = self.provider

        # Có page_range → buộc render qua images. Gemini/Anthropic không có API
        # để chọn page slice trong document block nên fallback pdftoppm là cách
        # duy nhất giữ được "chỉ đọc subset".
        if page_range is not None:
            if provider is None or not provider.supports_image:
                return ToolResult(
                    output="",
                    error=(
                        "Page range requires an image-capable provider (Gemini, Claude 3.5+, GPT-4o). "
                        "Current provider does not support image input."
                    ),
                    is_error=True,
                )
            return self._pdf_via_images(
                file_path,
                reason=f"page range {pages}",
                first_page=page_range[0],
                last_page=page_range[1],
            )

        # Path A — native PDF (Gemini, Anthropic)
        if provider is not None and provider.supports_pdf:
            if size > PDF_MAX_SIZE:
                if provider.supports_image:
                    return self._pdf_via_images(
                        file_path, reason=f"PDF too large for native path ({format_pdf_size(size)} > 20 MB)"
                    )
                return ToolResult(
                    output="",
                    error=(
                        f"PDF too large for native path ({format_pdf_size(size)} > 20 MB). "
                        f"This provider cannot fallback to images either."
                    ),
                    is_error=True,
                )
            b64 = read_pdf_base64(file_path)
            return ToolResult(
                output=f"PDF {format_pdf_size(size)} sent as document block — model will see content directly",
                content_blocks=[{
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": b64,
                    },
                }],
                metadata={"file_path": file_path, "size": size, "method": "native"},
            )

        # Path B — provider supports image: render từng page thành JPG
        if provider is not None and provider.supports_image:
            return self._pdf_via_images(
                file_path, reason="provider does not support native PDF"
            )

        # Path C — text-only provider: pypdf extract text-layer
        try:
            text = extract_pdf_text(file_path)
        except RuntimeError as e:
            return ToolResult(output="", error=str(e), is_error=True)

        if text.strip():
            return ToolResult(
                output=text,
                metadata={"file_path": file_path, "method": "pypdf_text_layer"},
            )
        return ToolResult(
            output="",
            error=(
                "PDF appears to be a scanned image (no text layer extractable). "
                "This provider does not support multimodal input. "
                "Switch to a vision-capable model (Gemini, Claude 3.5+, GPT-4o)."
            ),
            is_error=True,
        )

    def _pdf_via_images(
        self,
        file_path: str,
        reason: str,
        first_page: int | None = None,
        last_page: int | None = None,
    ) -> ToolResult:
        try:
            pages = pdf_to_jpeg_pages(
                file_path, first_page=first_page, last_page=last_page
            )
        except RuntimeError as e:
            return ToolResult(output="", error=str(e), is_error=True)

        blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(p).decode("ascii"),
                },
            }
            for p in pages
        ]
        meta: dict = {"file_path": file_path, "pages": len(pages), "method": "pdftoppm"}
        if first_page is not None:
            meta["first_page"] = first_page
        if last_page is not None:
            meta["last_page"] = last_page
        return ToolResult(
            output=f"PDF rendered to {len(pages)} JPEG page(s) ({reason})",
            content_blocks=blocks,
            metadata=meta,
        )

    # ---------- Image ----------

    def _read_image(self, file_path: str) -> ToolResult:
        ok, err = validate_image(file_path)
        if not ok:
            return ToolResult(output="", error=err, is_error=True)

        provider = self.provider
        if provider is None or not provider.supports_image:
            return ToolResult(
                output="",
                error=(
                    "This provider does not support image input. "
                    "Switch to Gemini, Claude 3.5+, or GPT-4o."
                ),
                is_error=True,
            )

        b64, mime = read_image_base64(file_path)
        size = os.path.getsize(file_path)
        return ToolResult(
            output=f"Image {mime} ({size // 1024} KB) sent as image block",
            content_blocks=[{
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            }],
            metadata={"file_path": file_path, "mime": mime, "size": size},
        )

    # ---------- Text (giữ nguyên path cũ) ----------

    def _read_text(self, file_path: str, args: dict) -> ToolResult:
        offset = int(args.get("offset", 0))
        limit = int(args.get("limit", 2000))

        if not os.path.exists(file_path):
            return ToolResult(output="", error=f"File not found: {file_path}", is_error=True)
        if os.path.isdir(file_path):
            return ToolResult(output="", error=f"Path is a directory: {file_path}", is_error=True)

        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(output="", error=f"Error reading file: {e}", is_error=True)

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        selected = lines[offset:offset + limit]

        numbered = []
        for i, line in enumerate(selected):
            line_num = offset + i + 1
            numbered.append(f"{line_num}\t{line.rstrip()}")

        output = "\n".join(numbered)
        if offset > 0 or offset + limit < total_lines:
            output += f"\n\n(Showing lines {offset+1}-{min(offset+limit, total_lines)} of {total_lines})"

        return ToolResult(
            output=output or "(empty file)",
            metadata={"file_path": file_path, "total_lines": total_lines},
        )

    def _resolve_path(self, path: str, cwd: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(cwd, path))
