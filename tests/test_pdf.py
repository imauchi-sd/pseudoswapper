"""Tests for .pdf document mode support (Stage 2)."""
from pathlib import Path

import pytest

from pseudoswapper.extractors.pdf import UnsupportedFileError, extract_text
from pseudoswapper.modes.document import redact_document
from pseudoswapper.session import clear_session
from tests.conftest import make_config

FIXTURE = Path("tests/fixtures/sample_document.pdf")


@pytest.fixture()
def cfg():
    return make_config(
        company_terms=["Acme Corporation", "Acme Corp", "Project Nightingale", "acme.com"],
        employees=[
            {"full_name": "John Doe", "email": "john.doe@acme.com", "username": "jdoe"},
            {"full_name": "Jane Smith", "email": "j.smith@acme.com", "username": "jsmith"},
        ],
    )


@pytest.fixture(autouse=True)
def clean_session(tmp_path):
    yield
    clear_session(tmp_path)


def _make_pdf(path: Path, text: str) -> None:
    """Write a minimal single-page PDF containing *text*."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    doc.build([Paragraph(text, styles["Normal"])])


# ── Output file characteristics ───────────────────────────────────────────────

def test_output_suffix_is_redacted_txt(cfg, tmp_path):
    import shutil
    src = tmp_path / "report.pdf"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path)
    assert out.name == "report.redacted.txt"
    assert out.exists()


def test_output_is_plain_text(cfg, tmp_path):
    import shutil
    src = tmp_path / "report.pdf"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path)
    # Must be readable as UTF-8 text, not binary
    content = out.read_text(encoding="utf-8")
    assert isinstance(content, str)


def test_output_written_alongside_input(cfg, tmp_path):
    import shutil
    src = tmp_path / "memo.pdf"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path)
    assert out.parent == src.parent


# ── PII removal ───────────────────────────────────────────────────────────────

def test_employee_name_replaced(cfg, tmp_path):
    src = tmp_path / "doc.pdf"
    _make_pdf(src, "The owner is John Doe.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "John Doe" not in content
    assert "[PERSON_" in content


def test_company_term_replaced(cfg, tmp_path):
    src = tmp_path / "doc.pdf"
    _make_pdf(src, "This project is run by Acme Corporation.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "Acme Corporation" not in content
    assert "[COMPANY_" in content


def test_email_replaced(cfg, tmp_path):
    src = tmp_path / "doc.pdf"
    _make_pdf(src, "Contact us at hello@example.com for details.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "hello@example.com" not in content
    assert "[EMAIL_" in content


def test_token_consistent_across_pages(cfg, tmp_path):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    src = tmp_path / "multipage.pdf"
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(src), pagesize=letter)
    doc.build([
        Paragraph("John Doe called.", styles["Normal"]),
        PageBreak(),
        Paragraph("John Doe left a voicemail.", styles["Normal"]),
    ])
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert content.count("[PERSON_1]") == 2


def test_two_employees_get_distinct_tokens(cfg, tmp_path):
    src = tmp_path / "doc.pdf"
    _make_pdf(src, "John Doe and Jane Smith attended the meeting.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "[PERSON_1]" in content
    assert "[PERSON_2]" in content


# ── Passthrough ───────────────────────────────────────────────────────────────

def test_passthrough_ip_preserved(cfg, tmp_path):
    src = tmp_path / "doc.pdf"
    _make_pdf(src, "Alert from 192.168.1.1 involving John Doe.")
    out = redact_document(src, cfg, tmp_path, passthrough_types={"IP"})
    content = out.read_text()
    assert "192.168.1.1" in content
    assert "John Doe" not in content


# ── UnsupportedFileError ──────────────────────────────────────────────────────

def test_image_only_pdf_raises(tmp_path):
    """A PDF with no embedded text raises UnsupportedFileError."""
    import struct, zlib

    # Minimal valid PDF with a single blank page and no text streams.
    # Built by hand to avoid any dependency on image tools.
    blank_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f\r
0000000009 00000 n\r
0000000058 00000 n\r
0000000115 00000 n\r
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF
"""
    path = tmp_path / "blank.pdf"
    path.write_bytes(blank_pdf)
    with pytest.raises(UnsupportedFileError):
        extract_text(path)


# ── Full fixture ──────────────────────────────────────────────────────────────

def test_full_fixture_contains_no_known_pii(cfg, tmp_path):
    import shutil
    src = tmp_path / "sample_document.pdf"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "John Doe" not in content
    assert "Jane Smith" not in content
    assert "Acme Corporation" not in content
    assert "Project Nightingale" not in content
    assert "john.doe@acme.com" not in content
