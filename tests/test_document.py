"""Tests for document mode (Phase 5)."""
from pathlib import Path

import pytest

from pseudoswapper.modes.document import redact_document
from pseudoswapper.session import session_exists, load_session
from tests.conftest import make_config

FIXTURE = Path("tests/fixtures/sample_document.txt")


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
    """Ensure no leftover session bleeds between tests."""
    yield
    from pseudoswapper.session import clear_session
    clear_session(tmp_path)


def test_output_file_has_redacted_suffix(cfg, tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Hello from John Doe at Acme Corporation.")
    out = redact_document(src, cfg, tmp_path)
    assert out.name == "report.redacted.txt"
    assert out.exists()


def test_output_written_alongside_input(cfg, tmp_path):
    src = tmp_path / "memo.txt"
    src.write_text("John Doe works at Acme Corporation.")
    out = redact_document(src, cfg, tmp_path)
    assert out.parent == src.parent


def test_yaml_company_term_replaced(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("This project is run by Acme Corporation.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "Acme Corporation" not in content
    assert "[COMPANY_" in content


def test_yaml_employee_name_replaced(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("The owner is John Doe.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "John Doe" not in content
    assert "[PERSON_" in content


def test_yaml_employee_username_replaced(cfg, tmp_path):
    # Username registered via pre-registration, detected by EmployeeRecognizer
    src = tmp_path / "doc.txt"
    src.write_text("Submitted by jdoe on Tuesday.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "jdoe" not in content


def test_email_replaced(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("Contact us at hello@example.com for details.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "hello@example.com" not in content
    assert "[EMAIL_" in content


def test_session_created_after_redact(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("John Doe from Acme Corporation.")
    redact_document(src, cfg, tmp_path)
    assert session_exists(tmp_path)


def test_employee_token_consistent_across_occurrences(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("John Doe called. John Doe left a voicemail.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    # Both occurrences must produce identical tokens
    assert content.count("[PERSON_1]") == 2


def test_two_employees_get_distinct_tokens(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("John Doe and Jane Smith attended the meeting.")
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "[PERSON_1]" in content
    assert "[PERSON_2]" in content


def test_session_registry_contains_detected_values(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("John Doe at john.doe@acme.com.")
    redact_document(src, cfg, tmp_path)
    registry = load_session(tmp_path)
    assert registry.lookup("John Doe") is not None
    assert registry.lookup("john.doe@acme.com") is not None


def test_full_sample_document_produces_no_known_pii(cfg, tmp_path):
    import shutil
    src = tmp_path / "sample_document.txt"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path)
    content = out.read_text()
    assert "John Doe" not in content
    assert "Jane Smith" not in content
    assert "Acme Corporation" not in content
    assert "Project Nightingale" not in content
    assert "john.doe@acme.com" not in content


# ── Passthrough integration tests ────────────────────────────────────────────

def test_passthrough_ip_preserved_in_document(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("Alert from 192.168.1.1 involving John Doe.")
    out = redact_document(src, cfg, tmp_path, passthrough_types={"IP"})
    content = out.read_text()
    assert "192.168.1.1" in content
    assert "John Doe" not in content


def test_passthrough_does_not_bypass_email(cfg, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("Contact john.doe@acme.com for details.")
    out = redact_document(src, cfg, tmp_path, passthrough_types={"EMAIL"})
    content = out.read_text()
    assert "john.doe@acme.com" not in content
    assert "[EMAIL_" in content
