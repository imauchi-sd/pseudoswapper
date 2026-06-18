"""Tests for the Tokenizer (Phase 4)."""
from pseudoswapper.detector import DetectedEntity
from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.tokenizer import PROTECTED_TYPES, Tokenizer


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


# ── Passthrough tests ────────────────────────────────────────────────────────

def test_passthrough_ip_leaves_ip_unreplaced():
    t = Tokenizer(EntityRegistry(), passthrough_types={"IP"})
    result = t.assign([_entity("IP", "10.0.0.1")])
    assert "10.0.0.1" not in result


def test_passthrough_does_not_affect_other_types():
    t = Tokenizer(EntityRegistry(), passthrough_types={"IP"})
    result = t.assign([_entity("IP", "10.0.0.1"), _entity("EMAIL", "a@b.com")])
    assert "10.0.0.1" not in result
    assert result["a@b.com"] == "[EMAIL_1]"


def test_passthrough_multiple_types():
    t = Tokenizer(EntityRegistry(), passthrough_types={"IP", "DOMAIN", "URL"})
    result = t.assign([
        _entity("IP", "10.0.0.1"),
        _entity("DOMAIN", "example.com"),
        _entity("URL", "https://example.com"),
        _entity("PERSON", "Jane Doe"),
    ])
    assert "10.0.0.1" not in result
    assert "example.com" not in result
    assert "https://example.com" not in result
    assert result["Jane Doe"] == "[PERSON_1]"


def test_passthrough_cannot_bypass_protected_types():
    # PERSON, EMAIL, COMPANY, ORG must always be tokenized.
    for protected in PROTECTED_TYPES:
        t = Tokenizer(EntityRegistry(), passthrough_types={protected})
        result = t.assign([_entity(protected, "sensitive-value")])
        assert "sensitive-value" in result, f"{protected} should not be bypassable"


def test_passthrough_silently_ignores_protected_types_in_set():
    t = Tokenizer(EntityRegistry(), passthrough_types={"IP", "PERSON"})
    assert "PERSON" not in t._passthrough
    assert "IP" in t._passthrough


def test_credit_card_is_in_protected_types():
    assert "CREDIT_CARD" in PROTECTED_TYPES


def test_credit_card_passthrough_cannot_bypass():
    t = Tokenizer(EntityRegistry(), passthrough_types={"CREDIT_CARD"})
    result = t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert "4111111111111111" in result


# ── Masking tests ─────────────────────────────────────────────────────────────

def _masking(masking_rules: dict) -> Tokenizer:
    return Tokenizer(EntityRegistry(), masking_rules=masking_rules)


_PERSON_RULE = {"PERSON": {"keep": "initials"}}
_CC_RULE = {"CREDIT_CARD": {"keep_first": 6, "keep_last": 4, "fill_char": "X"}}


def test_person_masking_full_name():
    t = _masking(_PERSON_RULE)
    result = t.assign([_entity("PERSON", "John Doe")])
    assert result["John Doe"] == "1_J.D."


def test_person_masking_sequence_number():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    result = t.assign([_entity("PERSON", "Jane Smith")])
    assert result["Jane Smith"] == "2_J.S."


def test_person_masking_deduplication():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    result = t.assign([_entity("PERSON", "John Doe")])
    assert result["John Doe"] == "1_J.D."
    assert t._registry._counters["PERSON"] == 1


def test_person_masking_single_name():
    t = _masking(_PERSON_RULE)
    result = t.assign([_entity("PERSON", "Cher")])
    assert result["Cher"] == "1_C."


def test_person_masking_three_part_name():
    t = _masking(_PERSON_RULE)
    result = t.assign([_entity("PERSON", "Mary Jane Watson")])
    assert result["Mary Jane Watson"] == "1_M.J.W."


def test_person_masking_registers_first_and_last_aliases():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    assert t._registry.lookup("John") == "1_J."
    assert t._registry.lookup("Doe") == "1_D."


def test_person_masking_first_name_after_full_name_reuses_alias():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    result = t.assign([_entity("PERSON", "John")])
    assert result["John"] == "1_J."
    assert t._registry._counters["PERSON"] == 1


def test_person_masking_not_restorable():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    assert t._registry.reverse_lookup("1_J.D.") is None


def test_person_masking_unique_initials_distinguished_by_number():
    t = _masking(_PERSON_RULE)
    t.assign([_entity("PERSON", "John Doe")])
    result = t.assign([_entity("PERSON", "Jane Doe")])
    # Same initials J.D. but different sequence numbers
    assert result["Jane Doe"] == "2_J.D."


def test_credit_card_masking_standard():
    t = _masking(_CC_RULE)
    result = t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert result["4111111111111111"] == "411111XXXXXX1111"


def test_credit_card_masking_strips_separators():
    t = _masking(_CC_RULE)
    result = t.assign([_entity("CREDIT_CARD", "4111 1111 1111 1111")])
    assert result["4111 1111 1111 1111"] == "411111XXXXXX1111"


def test_credit_card_masking_dashes():
    t = _masking(_CC_RULE)
    result = t.assign([_entity("CREDIT_CARD", "4111-1111-1111-1111")])
    assert result["4111-1111-1111-1111"] == "411111XXXXXX1111"


def test_credit_card_masking_custom_params():
    t = _masking({"CREDIT_CARD": {"keep_first": 4, "keep_last": 4, "fill_char": "*"}})
    result = t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert result["4111111111111111"] == "4111********1111"


def test_credit_card_masking_deduplication():
    t = _masking(_CC_RULE)
    t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    result = t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert result["4111111111111111"] == "411111XXXXXX1111"


def test_credit_card_no_masking_rule_falls_back_to_token():
    t = _make()  # no masking rules
    result = t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert result["4111111111111111"] == "[CREDIT_CARD_1]"


def test_credit_card_not_restorable_when_masked():
    t = _masking(_CC_RULE)
    t.assign([_entity("CREDIT_CARD", "4111111111111111")])
    assert t._registry.reverse_lookup("411111XXXXXX1111") is None


def test_masking_does_not_affect_unmasked_types():
    t = _masking(_PERSON_RULE)
    result = t.assign([
        _entity("PERSON", "John Doe"),
        _entity("EMAIL", "john@example.com"),
        _entity("PHONE", "+1 555 867 5309"),
    ])
    assert result["John Doe"] == "1_J.D."
    assert result["john@example.com"] == "[EMAIL_1]"
    assert result["+1 555 867 5309"] == "[PHONE_1]"
