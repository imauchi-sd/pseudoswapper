"""Tests for .msg (Outlook) document mode support (Stage D)."""
import io
import pathlib
import struct
from pathlib import Path

import pytest

from pseudoswapper.extractors.msg import UnsupportedEmailError, extract_text
from pseudoswapper.modes.document import redact_document
from pseudoswapper.session import clear_session, session_exists
from tests.conftest import make_config

FIXTURE = Path("tests/fixtures/sample_email.msg")

PT_STRING8 = 0x001E


def _make_msg(output_path: Path, props: dict) -> None:
    """Create a minimal .msg file with the given string properties."""
    from extract_msg.ole_writer import OleWriter

    writer = OleWriter()
    writer.addEntry("__nameid_version1.0", storage=True)
    writer.addEntry("__nameid_version1.0/__substg1.0_00020102", data=b"")
    writer.addEntry("__nameid_version1.0/__substg1.0_00030102", data=b"")
    writer.addEntry("__nameid_version1.0/__substg1.0_00040102", data=b"")

    header = b"\x00" * 16
    entries = b""
    for prop_id, value in props.items():
        tag = (prop_id << 16) | PT_STRING8
        data = value.encode("latin-1") + b"\x00"
        entries += struct.pack("<HHIIi", PT_STRING8, prop_id, 0, len(data), 0)
        writer.addEntry(f"__substg1.0_{tag:08X}", data=data)

    writer.addEntry("__properties_version1.0", data=header + entries)

    buf = io.BytesIO()
    writer.write(buf)
    output_path.write_bytes(buf.getvalue())


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


def test_msg_output_is_txt(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    assert out.suffix == ".txt"
    assert out.name == "email.redacted.txt"


def test_msg_output_exists(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    assert out.exists()


# ── PII removal ───────────────────────────────────────────────────────────────


def test_msg_sender_redacted(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "john.doe@acme.com" not in content


def test_msg_subject_redacted(cfg, tmp_path):
    """Subject 'Q3 Incident Report' — the employee name 'John' in it should be masked."""
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    # Neither employee email should appear in the output
    assert "john.doe@acme.com" not in content
    assert "j.smith@acme.com" not in content


def test_msg_body_email_redacted(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "john.doe@acme.com" not in content


def test_msg_phone_redacted(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text(encoding="utf-8")
    assert "+44 20 7946 0958" not in content


# ── Session behaviour ─────────────────────────────────────────────────────────


def test_msg_no_session_created(cfg, tmp_path):
    import shutil

    src = tmp_path / "email.msg"
    shutil.copy(FIXTURE, src)
    redact_document(src, cfg, tmp_path, write_session=False)
    assert not session_exists(tmp_path)


# ── Extractor error handling ──────────────────────────────────────────────────


def test_msg_empty_raises(tmp_path):
    """A MSG with no body and no PII-bearing headers raises UnsupportedEmailError."""
    empty_msg = tmp_path / "empty.msg"
    # Only include message class — no body, no From/To/Cc/Subject fields
    _make_msg(empty_msg, {0x001A: "IPM.Note"})
    with pytest.raises(UnsupportedEmailError):
        extract_text(empty_msg)
