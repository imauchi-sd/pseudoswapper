from __future__ import annotations

from pathlib import Path


class UnsupportedFileError(Exception):
    """Raised when a PDF yields no extractable text (e.g. scanned/image-only PDF)."""


def extract_text(path: Path) -> str:
    """Extract all text from a PDF, joining pages with blank lines.

    Raises UnsupportedFileError if no text is found on any page — this indicates
    a scanned or image-only PDF that requires OCR, which is out of scope for v1.
    """
    import pdfplumber

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)

    combined = "\n\n".join(pages)
    if not combined.strip():
        raise UnsupportedFileError(
            f"{path.name}: no extractable text found. "
            "Scanned or image-only PDFs are not supported — convert to text first."
        )
    return combined
