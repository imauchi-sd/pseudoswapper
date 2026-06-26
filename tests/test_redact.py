"""Tests for the redact mode (Stage A & B)."""
import shutil
from pathlib import Path

import pytest

from pseudoswapper.config import ConfigError, get_redact_profile
from pseudoswapper.modes.redact import redact_file
from pseudoswapper.session import session_exists
from tests.conftest import make_config


def test_redact_produces_redacted_suffix(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Hello Alice Johnson, your card 4111111111111111 is on file.")
    cfg = make_config()
    out = redact_file(src, cfg)
    assert out.name == "report.redacted.txt"
    assert out.exists()


def test_redact_no_session_created(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("John Doe called about the project.")
    cfg = make_config()
    redact_file(src, cfg)
    assert not session_exists(tmp_path)


def test_credit_card_always_masked_even_when_passthroughed(tmp_path):
    src = tmp_path / "data.txt"
    src.write_text("Card number: 4111111111111111")
    cfg = make_config(masking_rules={"CREDIT_CARD": {}})
    out = redact_file(src, cfg, passthrough_types={"CREDIT_CARD"})
    content = out.read_text()
    assert "4111111111111111" not in content


def test_person_passthroughed_when_requested(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Alice Johnson submitted the report.")
    cfg = make_config(
        employees=[{"full_name": "Alice Johnson"}],
        masking_rules={"PERSON": {}},
    )
    out = redact_file(src, cfg, passthrough_types={"PERSON"})
    content = out.read_text()
    assert "Alice Johnson" in content


def test_email_passthroughed_when_requested(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Contact us at alice@example.com for more info.")
    cfg = make_config()
    out = redact_file(src, cfg, passthrough_types={"EMAIL"})
    content = out.read_text()
    assert "alice@example.com" in content


def test_redact_csv_no_session(tmp_path):
    src = tmp_path / "data.csv"
    src.write_text("full_name,email\nJohn Doe,john@example.com\n")
    cfg = make_config()
    redact_file(src, cfg)
    assert not session_exists(tmp_path)


def test_get_redact_profile_returns_profile():
    cfg = make_config(
        redact_profiles={"incident": {"passthrough": ["PERSON", "EMAIL"]}}
    )
    prof = get_redact_profile(cfg, "incident")
    assert prof["passthrough"] == ["PERSON", "EMAIL"]


def test_get_redact_profile_raises_on_missing():
    cfg = make_config(redact_profiles={})
    with pytest.raises(ConfigError) as exc_info:
        get_redact_profile(cfg, "nonexistent")
    assert "nonexistent" in str(exc_info.value)


# ── Stage B: redact-mode-only entity types ────────────────────────────────────

def test_amount_tokenized_in_redact_mode(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("The salary is $52,340 per year.")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})
    out = redact_file(src, cfg)
    content = out.read_text()
    assert "[AMOUNT_1]" in content or "$52,340" not in content


def test_iban_tokenized_in_redact_mode(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Please transfer to IBAN: GB29NWBK60161331926819")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})
    out = redact_file(src, cfg)
    content = out.read_text()
    assert "GB29NWBK60161331926819" not in content
    assert "[IBAN_CODE_1]" in content


def test_mac_address_tokenized_in_redact_mode(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("Device MAC: 00:1A:2B:3C:4D:5E")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})
    out = redact_file(src, cfg)
    content = out.read_text()
    assert "[MAC_ADDRESS_1]" in content


def test_amount_bypassable(tmp_path):
    src = tmp_path / "report.txt"
    src.write_text("The salary is $52,340 per year.")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})
    out = redact_file(src, cfg, passthrough_types={"AMOUNT"})
    content = out.read_text()
    assert "$52,340" in content


def test_new_types_not_detected_in_document_mode(tmp_path):
    from pseudoswapper.modes.document import redact_document

    src = tmp_path / "report.txt"
    src.write_text("Salary $52,340 and IBAN GB29NWBK60161331926819 noted.")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})
    out = redact_document(src, cfg, tmp_path, write_session=False)
    content = out.read_text()
    assert "[AMOUNT_1]" not in content
    assert "[IBAN_CODE_1]" not in content


# ── Stage E: batch folder mode ────────────────────────────────────────────────

def test_batch_processes_all_supported_files(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    f1 = tmp_path / "report.txt"
    f1.write_text("Contact John Doe for details.")
    f2 = tmp_path / "data.csv"
    f2.write_text("full_name,email\nJohn Doe,john@example.com\n")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})

    summary = redact_batch(tmp_path, cfg)

    assert summary["processed"] == 2
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0
    assert (tmp_path / "report.redacted.txt").exists()
    assert (tmp_path / "data.redacted.csv").exists()


def test_batch_same_entity_same_mask_across_files(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    cfg = make_config(
        employees=[{"full_name": "Alice Johnson"}],
        masking_rules={"PERSON": {}, "CREDIT_CARD": {}},
    )
    f1 = tmp_path / "email1.txt"
    f1.write_text("Please contact Alice Johnson for approval.")
    f2 = tmp_path / "email2.txt"
    f2.write_text("Alice Johnson confirmed the request.")

    summary = redact_batch(tmp_path, cfg)

    assert summary["succeeded"] == 2
    out1 = (tmp_path / "email1.redacted.txt").read_text()
    out2 = (tmp_path / "email2.redacted.txt").read_text()
    # Extract the token/mask that replaced "Alice Johnson" in each file
    import re
    tokens1 = re.findall(r'\[PERSON_\d+\]|\d+_[A-Z]\.', out1)
    tokens2 = re.findall(r'\[PERSON_\d+\]|\d+_[A-Z]\.', out2)
    assert tokens1 and tokens2
    assert tokens1[0] == tokens2[0]


def test_batch_skips_already_redacted_files(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    f1 = tmp_path / "report.txt"
    f1.write_text("Contact John Doe for details.")
    f2 = tmp_path / "report.redacted.txt"
    f2.write_text("Contact [PERSON_1] for details.")
    cfg = make_config()

    summary = redact_batch(tmp_path, cfg)

    assert summary["processed"] == 1


def test_batch_skips_unsupported_extensions(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    f1 = tmp_path / "data.txt"
    f1.write_text("John Doe is here.")
    f2 = tmp_path / "image.png"
    f2.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
    cfg = make_config()

    summary = redact_batch(tmp_path, cfg)

    assert summary["processed"] == 1


def test_batch_one_error_does_not_abort(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    f1 = tmp_path / "valid.txt"
    f1.write_text("John Doe approved the request.")
    f2 = tmp_path / "corrupt.docx"
    f2.write_bytes(b"not a real docx file content")
    cfg = make_config()

    # Should not raise even though corrupt.docx will fail
    summary = redact_batch(tmp_path, cfg)

    assert summary["succeeded"] == 1
    assert summary["failed"] == 1
    assert summary["processed"] == 2


def test_batch_recursive_finds_subdirectory_files(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    f1 = subdir / "nested.txt"
    f1.write_text("Jane Smith is the contact.")
    cfg = make_config()

    # Without recursive: should not find the file
    summary_flat = redact_batch(tmp_path, cfg, recursive=False)
    assert summary_flat["processed"] == 0

    # With recursive: should find the file
    summary_recursive = redact_batch(tmp_path, cfg, recursive=True)
    assert summary_recursive["processed"] == 1


def test_batch_empty_directory_returns_zero(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    cfg = make_config()

    summary = redact_batch(tmp_path, cfg)

    assert summary["processed"] == 0
    assert summary["succeeded"] == 0
    assert summary["failed"] == 0


def test_batch_on_file_callback_called_for_each(tmp_path):
    from pseudoswapper.modes.redact import redact_batch
    f1 = tmp_path / "file1.txt"
    f1.write_text("Alice Johnson is here.")
    f2 = tmp_path / "file2.txt"
    f2.write_text("Bob Smith called today.")
    cfg = make_config(masking_rules={"PERSON": {}, "CREDIT_CARD": {}})

    calls: list[tuple] = []

    def _on_file(file, success, msg):
        calls.append((file, success, msg))

    summary = redact_batch(tmp_path, cfg, on_file=_on_file)

    assert len(calls) == 2
    assert summary["processed"] == 2
