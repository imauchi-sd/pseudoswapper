from __future__ import annotations

import email
import email.policy
import html.parser
import re
from pathlib import Path


class UnsupportedEmailError(Exception):
    """Raised when no readable body content can be extracted from the email."""


class _HTMLTextExtractor(html.parser.HTMLParser):
    """Strip HTML tags and return plain text."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(html_text: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html_text)
    return extractor.get_text()


def _extract_body(msg: email.message.Message) -> str:
    """Return the best plain-text body from *msg*.

    Preference order:
    1. text/plain part from a multipart message
    2. text/html part (tags stripped)
    3. Non-multipart body decoded as UTF-8

    Returns empty string if nothing readable is found.
    """
    if msg.is_multipart():
        # Walk all parts; prefer text/plain over text/html
        plain: str | None = None
        html_body: str | None = None
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and plain is None:
                payload = part.get_payload(decode=True)
                if payload:
                    plain = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            elif ct == "text/html" and html_body is None:
                payload = part.get_payload(decode=True)
                if payload:
                    html_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if plain is not None:
            return plain
        if html_body is not None:
            return _strip_html(html_body)
        return ""

    # Non-multipart
    ct = msg.get_content_type()
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    if ct == "text/html":
        return _strip_html(text)
    return text


def extract_text(path: Path) -> str:
    """Extract all readable text from an EML file.

    Returns a string with a structured header block followed by the body,
    suitable for PII detection.

    Raises UnsupportedEmailError if no body content is extractable.
    """
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)

    # Build a simple header block with the fields most likely to contain PII.
    header_lines: list[str] = []
    for field in ("From", "To", "Cc", "Bcc", "Reply-To", "Subject"):
        value = msg.get(field, "")
        if value.strip():
            header_lines.append(f"{field}: {value.strip()}")

    body = _extract_body(msg)

    if not body.strip() and not header_lines:
        raise UnsupportedEmailError(
            f"{path.name}: no readable content found in email."
        )

    parts = []
    if header_lines:
        parts.append("\n".join(header_lines))
    if body.strip():
        parts.append(body)

    return "\n\n".join(parts)
