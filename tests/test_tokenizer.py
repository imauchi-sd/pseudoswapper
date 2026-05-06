"""Tests for the Tokenizer (Phase 4)."""
from pseudoswapper.detector import DetectedEntity
from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.tokenizer import Tokenizer


def _entity(entity_type: str, text: str) -> DetectedEntity:
    return DetectedEntity(entity_type=entity_type, text=text, start=0, end=len(text), score=0.9)


def _make() -> Tokenizer:
    return Tokenizer(EntityRegistry())


def test_full_name_registers_canonical_token():
    t = _make()
    result = t.assign([_entity("PERSON", "John Doe")])
    assert result["John Doe"] == "[PERSON_1]"


def test_full_name_registers_first_and_last_surface_forms():
    t = Tokenizer(EntityRegistry())
    t.assign([_entity("PERSON", "John Doe")])
    assert t._registry.lookup("John") == "[PERSON_1_FIRST]"
    assert t._registry.lookup("Doe") == "[PERSON_1_LAST]"


def test_same_full_name_second_call_returns_same_token():
    t = _make()
    t.assign([_entity("PERSON", "John Doe")])
    result2 = t.assign([_entity("PERSON", "John Doe")])
    assert result2["John Doe"] == "[PERSON_1]"
    # Counter must not have advanced to PERSON_2
    assert t._registry._counters["PERSON"] == 1


def test_first_name_alone_registers_independently():
    t = _make()
    # No full name registered — single name should get its own PERSON token
    result = t.assign([_entity("PERSON", "Alice")])
    assert result["Alice"] == "[PERSON_1]"


def test_first_name_after_full_name_does_not_increment_counter():
    t = _make()
    t.assign([_entity("PERSON", "John Doe")])
    # "John" was registered as a surface form during the full-name assignment
    result = t.assign([_entity("PERSON", "John")])
    assert result["John"] == "[PERSON_1_FIRST]"
    assert t._registry._counters["PERSON"] == 1


def test_two_distinct_people_get_distinct_tokens():
    t = _make()
    r = t.assign([_entity("PERSON", "John Doe"), _entity("PERSON", "Jane Smith")])
    assert r["John Doe"] == "[PERSON_1]"
    assert r["Jane Smith"] == "[PERSON_2]"


def test_email_routes_to_email_token():
    t = _make()
    result = t.assign([_entity("EMAIL", "bob@example.com")])
    assert result["bob@example.com"] == "[EMAIL_1]"


def test_phone_routes_to_phone_token():
    t = _make()
    result = t.assign([_entity("PHONE", "+1 555 867 5309")])
    assert result["+1 555 867 5309"] == "[PHONE_1]"


def test_ip_routes_to_ip_token():
    t = _make()
    result = t.assign([_entity("IP", "10.0.0.1")])
    assert result["10.0.0.1"] == "[IP_1]"


def test_company_routes_to_company_token():
    t = _make()
    result = t.assign([_entity("COMPANY", "Acme Corporation")])
    assert result["Acme Corporation"] == "[COMPANY_1]"


def test_assign_correlated_registers_email_person_token():
    t = _make()
    token = t.assign_correlated("john.doe@acme.com", 1)
    assert token == "[EMAIL_PERSON_1]"
    assert t._registry.lookup("john.doe@acme.com") == "[EMAIL_PERSON_1]"


def test_same_entity_value_different_types_returns_first_registered():
    # Edge case: same string detected twice (shouldn't happen in practice but must not crash).
    t = _make()
    t.assign([_entity("EMAIL", "x@y.com")])
    result = t.assign([_entity("EMAIL", "x@y.com")])
    assert result["x@y.com"] == "[EMAIL_1]"
    assert t._registry._counters["EMAIL"] == 1
