"""Tests for the restore module (Phase 5)."""
from pathlib import Path

import pytest

from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.restore import restore, restore_file
from pseudoswapper.session import create_session, session_exists, load_session


def _registry_with(*pairs) -> EntityRegistry:
    """Build a registry from (original_value, entity_type) pairs."""
    reg = EntityRegistry()
    for value, etype in pairs:
        reg.register(value, etype)
    return reg


# ── Pure restore() function ──────────────────────────────────────────────────

def test_all_tokens_replaced():
    reg = _registry_with(("John Doe", "PERSON"), ("john@acme.com", "EMAIL"))
    text = "Hello [PERSON_1], your email is [EMAIL_1]."
    assert restore(text, reg) == "Hello John Doe, your email is john@acme.com."


def test_unknown_token_left_in_place():
    reg = EntityRegistry()
    text = "See [PERSON_99] for details."
    assert restore(text, reg) == text


def test_case_variant_token_restored():
    reg = _registry_with(("Alice", "PERSON"))
    for variant in ("[person_1]", "[PERSON_1]", "[Person_1]", "[PERSON_1]"):
        result = restore(variant, reg)
        assert result == "Alice", f"Failed for variant {variant!r}"


def test_token_wrapped_in_backticks_restored():
    reg = _registry_with(("John Doe", "PERSON"))
    text = "The contact is `[PERSON_1]` — reach out directly."
    assert restore(text, reg) == "The contact is `John Doe` — reach out directly."


def test_token_wrapped_in_bold_markdown_restored():
    reg = _registry_with(("John Doe", "PERSON"))
    text = "Assigned to **[PERSON_1]** for review."
    assert restore(text, reg) == "Assigned to **John Doe** for review."


def test_multiple_occurrences_of_same_token_all_restored():
    reg = _registry_with(("Alice", "PERSON"))
    text = "[PERSON_1] sent a message. [PERSON_1] followed up."
    assert restore(text, reg) == "Alice sent a message. Alice followed up."


def test_surface_form_tokens_restored():
    from pseudoswapper.tokenizer import Tokenizer
    from pseudoswapper.detector import DetectedEntity
    reg = EntityRegistry()
    tok = Tokenizer(reg)
    tok._assign_person("John Doe")
    # Registry now holds PERSON_1, PERSON_1_FIRST, PERSON_1_LAST
    text = "[PERSON_1] ([PERSON_1_FIRST] is fine to contact)."
    result = restore(text, reg)
    assert result == "John Doe (John is fine to contact)."


# ── restore_file() orchestration ─────────────────────────────────────────────

def test_restore_file_writes_output_with_restored_suffix(tmp_path):
    reg = _registry_with(("Alice", "PERSON"))
    create_session(reg, tmp_path)

    ai_out = tmp_path / "response.txt"
    ai_out.write_text("[PERSON_1] approved the request.")

    out = restore_file(ai_out, tmp_path)
    assert out.name == "response.restored.txt"
    assert out.read_text() == "Alice approved the request."


def test_session_deleted_after_successful_restore(tmp_path):
    reg = _registry_with(("Alice", "PERSON"))
    create_session(reg, tmp_path)

    ai_out = tmp_path / "response.txt"
    ai_out.write_text("[PERSON_1] approved.")
    restore_file(ai_out, tmp_path)

    assert not session_exists(tmp_path)


def test_session_preserved_when_no_session_exists(tmp_path):
    ai_out = tmp_path / "response.txt"
    ai_out.write_text("[PERSON_1] approved.")
    with pytest.raises(FileNotFoundError):
        restore_file(ai_out, tmp_path)
    # No session existed — nothing to preserve, but also no crash after the error
    assert not session_exists(tmp_path)


def test_restore_file_raises_when_no_session(tmp_path):
    ai_out = tmp_path / "response.txt"
    ai_out.write_text("some text")
    with pytest.raises(FileNotFoundError):
        restore_file(ai_out, tmp_path)


# ── Round-trip integration ───────────────────────────────────────────────────

def test_document_restore_round_trip(tmp_path):
    """Full round-trip: redact a document then restore AI output."""
    from pseudoswapper.modes.document import redact_document
    from tests.conftest import make_config

    original = "Contact John Doe at john.doe@acme.com — he works at Acme Corporation."
    cfg = make_config(
        company_terms=["Acme Corporation"],
        employees=[{"full_name": "John Doe", "email": "john.doe@acme.com", "username": "jdoe"}],
    )

    src = tmp_path / "memo.txt"
    src.write_text(original)
    redacted_path = redact_document(src, cfg, tmp_path)

    # Simulate AI returning the redacted content unchanged (tokens survive verbatim)
    ai_output = tmp_path / "ai_response.txt"
    ai_output.write_text(redacted_path.read_text())

    restored_path = restore_file(ai_output, tmp_path)
    restored = restored_path.read_text()

    assert "John Doe" in restored
    assert "john.doe@acme.com" in restored
    assert "Acme Corporation" in restored
