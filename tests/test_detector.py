"""Tests for the detection layer (Phase 3)."""
import pytest

from pseudoswapper.detector import DetectedEntity, Detector
from tests.conftest import make_config


SAMPLE_TEXT = (
    "Contact John Doe at john.doe@acme.com or call +1 (555) 867-5309. "
    "The server IP is 192.168.1.10 and the domain is acme.com. "
    "Visit https://intranet.acme.com for details. "
    "Project Nightingale is our top priority at Acme Corporation."
)


@pytest.fixture(scope="module")
def detector() -> Detector:
    cfg = make_config(
        company_terms=["Acme Corporation", "Acme Corp", "Project Nightingale", "acme.com"],
        employees=[
            {"full_name": "John Doe", "email": "john.doe@acme.com", "username": "jdoe"},
        ],
    )
    return Detector(cfg)


def _types(entities: list[DetectedEntity]) -> set[str]:
    return {e.entity_type for e in entities}


def _texts(entities: list[DetectedEntity]) -> set[str]:
    return {e.text for e in entities}


def test_email_detected(detector):
    results = detector.analyze("Send a message to john.doe@acme.com please.")
    assert any(e.entity_type == "EMAIL" for e in results)
    assert any("john.doe@acme.com" in e.text for e in results)


def test_phone_detected(detector):
    results = detector.analyze("Call me at +1 (555) 867-5309 any time.")
    assert any(e.entity_type == "PHONE" for e in results)


def test_ip_detected(detector):
    results = detector.analyze("The server is at 192.168.1.10.")
    assert any(e.entity_type == "IP" for e in results)


def test_person_name_detected(detector):
    # Presidio/spaCy should detect "Alice Chen" as a PERSON in prose.
    results = detector.analyze("Alice Chen sent the report yesterday.")
    assert any(e.entity_type == "PERSON" for e in results)


def test_company_term_detected(detector):
    results = detector.analyze("This was approved by Acme Corporation last week.")
    assert any(e.entity_type == "COMPANY" for e in results)
    assert any(e.text == "Acme Corporation" for e in results)


def test_employee_name_detected(detector):
    # Employee recognizer should fire even without NLP context.
    results = detector.analyze("jdoe submitted the PR.")
    types = _types(results)
    assert "PERSON" in types


def test_no_overlapping_spans(detector):
    results = detector.analyze(SAMPLE_TEXT)
    positions: list[tuple[int, int]] = [(e.start, e.end) for e in results]
    # Check that no two spans overlap.
    for i, (s1, e1) in enumerate(positions):
        for j, (s2, e2) in enumerate(positions):
            if i == j:
                continue
            assert not (s1 < e2 and s2 < e1), (
                f"Overlapping spans: {results[i]} and {results[j]}"
            )


def test_full_sample_covers_key_entities(detector):
    with open("tests/fixtures/sample_document.txt") as f:
        text = f.read()
    results = detector.analyze(text)
    found_types = _types(results)
    assert "EMAIL" in found_types
    assert "PHONE" in found_types
    assert "IP" in found_types
    assert "COMPANY" in found_types


def test_exclude_terms_skipped():
    cfg = make_config(
        company_terms=["Acme Corporation"],
        exclude_terms=["Acme Corporation"],
    )
    detector = Detector(cfg)
    results = detector.analyze("Acme Corporation is a company.")
    assert not any(e.text == "Acme Corporation" for e in results)


def test_detected_entity_has_correct_span():
    cfg = make_config()
    d = Detector(cfg)
    text = "Email me at bob@example.com for details."
    results = d.analyze(text)
    email_hits = [e for e in results if e.entity_type == "EMAIL"]
    assert email_hits
    for hit in email_hits:
        assert text[hit.start:hit.end] == hit.text
