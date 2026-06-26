from __future__ import annotations

from pathlib import Path


class UnsupportedEmailError(Exception):
    """Raised when no readable body content can be extracted from the MSG file."""


def _strip_html(html_bytes: bytes) -> str:
    """Strip HTML tags from bytes, returning plain text."""
    import html.parser

    class _Extractor(html.parser.HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self._parts.append(data)

        def get_text(self) -> str:
            return " ".join(self._parts)

    extractor = _Extractor()
    extractor.feed(html_bytes.decode("utf-8", errors="replace"))
    return extractor.get_text()


def extract_text(path: Path) -> str:
    """Extract all readable text from an Outlook .msg file.

    Returns a string with a structured header block followed by the body,
    suitable for PII detection. Output is always plain text.

    Raises UnsupportedEmailError if no body content is extractable.
    """
    import extract_msg

    msg = extract_msg.openMsg(str(path))
    try:
        header_lines: list[str] = []

        sender = (msg.sender or "").strip().rstrip("\x00")
        if sender:
            # Try to get sender email from stream directly.
            # getStringStream expects the name WITHOUT the type suffix.
            try:
                sender_email = msg.getStringStream("__substg1.0_0C1F") or ""
                sender_email = sender_email.strip().rstrip("\x00")
            except Exception:
                sender_email = ""
            if sender_email and sender_email not in sender:
                header_lines.append(f"From: {sender} <{sender_email}>")
            elif sender:
                header_lines.append(f"From: {sender}")

        # Read To and Cc directly from MAPI streams (m.to/m.cc use recipient
        # sub-storages which require a more complex MSG structure).
        # getStringStream expects the name WITHOUT the type suffix.
        for field, stream_name in (
            ("To", "__substg1.0_0E04"),
            ("Cc", "__substg1.0_0E03"),
        ):
            try:
                val = msg.getStringStream(stream_name)
                if val:
                    val = val.strip().rstrip("\x00")
                    if val:
                        header_lines.append(f"{field}: {val}")
            except Exception:
                pass

        subject = (msg.subject or "").strip().rstrip("\x00")
        if subject:
            header_lines.append(f"Subject: {subject}")

        # Prefer plain text body; fall back to HTML.
        body = (msg.body or "").strip().rstrip("\x00")
        if not body and msg.htmlBody:
            body = _strip_html(msg.htmlBody).strip()

    finally:
        msg.close()

    if not body and not header_lines:
        raise UnsupportedEmailError(
            f"{path.name}: no readable content found in MSG file."
        )

    parts: list[str] = []
    if header_lines:
        parts.append("\n".join(header_lines))
    if body:
        parts.append(body)

    return "\n\n".join(parts)
