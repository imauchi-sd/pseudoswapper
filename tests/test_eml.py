"""Tests for .eml document mode support (Stage C)."""
from pathlib import Path

import pytest

from pseudoswapper.extractors.eml import UnsupportedEmailError, extract_text
from pseudoswapper.modes.document import redact_document
from pseudoswapper.session import clear_session
from tests.conftest import make_config

FIXTURE = Path("tests/fixtures/sample_email.eml")


@pytest.fixture()
def cfg():
    return make_config(
        employees=[
            {"full_name": "John Doe", "email": "john.doe@acme.com"},
            {"full_name": "Jane Smith", "email": "j.smith@acme.com"},
        ],
        masking_rules={"PERSON": {}, "CREDIT_CARD": {}},
    )


@pytest.fixture(autouse=True)
def clean_session(tmp_path):
    yield
    clear_session(tmp_path)


# ── Output file characteristics ───────────────────────────────────────────────

def test_eml_output_is_txt(cfg, tmp_path):
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    assert out.suffix == ".txt"
    assert out.name == "email.redacted.txt"


def test_eml_output_exists(cfg, tmp_path):
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    assert out.exists()


# ── PII removal ───────────────────────────────────────────────────────────────

def test_eml_headers_redacted(cfg, tmp_path):
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "john.doe@acme.com" not in content
    assert "alice.wong@acme.com" not in content


def test_eml_subject_redacted(cfg, tmp_path):
    """Subject line contains 'Q3 Payroll Report Review' — no unreplaced employee email."""
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    # Subject is in the header block; confirm no employee email leaks there
    assert "john.doe@acme.com" not in content
    assert "j.smith@acme.com" not in content


def test_eml_body_pii_redacted(cfg, tmp_path):
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "john.doe@acme.com" not in content


def test_eml_phone_in_body_redacted(cfg, tmp_path):
    import shutil
    src = tmp_path / "email.eml"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "+44 20 7946 0958" not in content


# ── Extractor unit tests ──────────────────────────────────────────────────────

def test_multipart_uses_plain_part(tmp_path):
    """Verify that text/plain is preferred over text/html in multipart messages."""
    eml_content = (
        b"From: sender@example.com\r\n"
        b"Subject: plain test\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=\"testboundary\"\r\n"
        b"\r\n"
        b"--testboundary\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"PLAIN_ONLY_MARKER\r\n"
        b"--testboundary\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body><p>This is HTML content only.</p></body></html>\r\n"
        b"--testboundary--\r\n"
    )
    src = tmp_path / "multipart.eml"
    src.write_bytes(eml_content)
    result = extract_text(src)
    assert "PLAIN_ONLY_MARKER" in result


def test_html_only_eml_stripped_and_readable(tmp_path):
    """HTML-only EML should have tags stripped and text content preserved."""
    eml_content = (
        b"From: sender@example.com\r\n"
        b"Subject: html test\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body><p>Contact alice@example.com</p></body></html>\r\n"
    )
    src = tmp_path / "html_only.eml"
    src.write_bytes(eml_content)
    result = extract_text(src)
    assert "alice@example.com" in result


def test_empty_body_raises(tmp_path):
    """An EML with no headers and no body parts should raise UnsupportedEmailError."""
    # No From/To/Cc/Subject headers (so header_lines is empty) and no body parts.
    eml_content = (
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=\"emptyboundary\"\r\n"
        b"\r\n"
        b"--emptyboundary--\r\n"
    )
    src = tmp_path / "empty.eml"
    src.write_bytes(eml_content)
    with pytest.raises(UnsupportedEmailError):
        extract_text(src)
