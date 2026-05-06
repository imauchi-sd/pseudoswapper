"""Tests for the Replacer (Phase 4)."""
from pseudoswapper.replacer import replace


def test_empty_token_map_returns_original():
    text = "Nothing to replace here."
    assert replace(text, {}) == text


def test_single_replacement():
    result = replace("Hello John Doe.", {"John Doe": "[PERSON_1]"})
    assert result == "Hello [PERSON_1]."


def test_all_occurrences_replaced():
    text = "John Doe called. John Doe left a message."
    result = replace(text, {"John Doe": "[PERSON_1]"})
    assert result == "[PERSON_1] called. [PERSON_1] left a message."


def test_full_name_before_first_name():
    # "John Doe" must be matched first even though "John" appears in it.
    text = "John Doe and John attended."
    token_map = {"John Doe": "[PERSON_1]", "John": "[PERSON_1_FIRST]"}
    result = replace(text, token_map)
    assert result == "[PERSON_1] and [PERSON_1_FIRST] attended."


def test_regex_special_characters_in_key():
    # Email addresses contain dots and @ — these must be escaped.
    text = "Contact bob@example.com for info."
    result = replace(text, {"bob@example.com": "[EMAIL_1]"})
    assert result == "Contact [EMAIL_1] for info."


def test_ip_address_dots_escaped():
    text = "Server at 10.0.0.1 is down."
    result = replace(text, {"10.0.0.1": "[IP_1]"})
    assert result == "Server at [IP_1] is down."


def test_parentheses_in_key():
    text = "Call +1 (555) 867-5309 now."
    result = replace(text, {"+1 (555) 867-5309": "[PHONE_1]"})
    assert result == "Call [PHONE_1] now."


def test_multiple_entity_types_replaced():
    text = "John Doe sent mail from john@acme.com at 10.0.0.1."
    token_map = {
        "John Doe": "[PERSON_1]",
        "john@acme.com": "[EMAIL_1]",
        "10.0.0.1": "[IP_1]",
    }
    result = replace(text, token_map)
    assert result == "[PERSON_1] sent mail from [EMAIL_1] at [IP_1]."


def test_no_partial_match_when_longer_key_present():
    # "Acme" must not be replaced when only "Acme Corporation" is in the map.
    text = "Acme and Acme Corporation are different strings."
    token_map = {"Acme Corporation": "[COMPANY_1]"}
    result = replace(text, token_map)
    assert result == "Acme and [COMPANY_1] are different strings."
