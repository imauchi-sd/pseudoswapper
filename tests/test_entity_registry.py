import pytest

from pseudoswapper.entity_registry import EntityRegistry


def test_register_returns_token():
    reg = EntityRegistry()
    token = reg.register("John Doe", "PERSON")
    assert token == "[PERSON_1]"


def test_same_value_returns_same_token():
    reg = EntityRegistry()
    t1 = reg.register("John Doe", "PERSON")
    t2 = reg.register("John Doe", "PERSON")
    assert t1 == t2


def test_counters_increment_per_type():
    reg = EntityRegistry()
    t1 = reg.register("John Doe", "PERSON")
    t2 = reg.register("Jane Smith", "PERSON")
    t3 = reg.register("john@example.com", "EMAIL")
    assert t1 == "[PERSON_1]"
    assert t2 == "[PERSON_2]"
    assert t3 == "[EMAIL_1]"


def test_counters_independent_across_types():
    reg = EntityRegistry()
    reg.register("a@b.com", "EMAIL")
    reg.register("c@d.com", "EMAIL")
    token = reg.register("Alice", "PERSON")
    assert token == "[PERSON_1]"


def test_lookup_returns_token_for_known_value():
    reg = EntityRegistry()
    reg.register("alice@corp.com", "EMAIL")
    assert reg.lookup("alice@corp.com") == "[EMAIL_1]"


def test_lookup_returns_none_for_unknown():
    reg = EntityRegistry()
    assert reg.lookup("unknown") is None


def test_reverse_lookup_returns_original():
    reg = EntityRegistry()
    reg.register("10.0.0.1", "IP")
    assert reg.reverse_lookup("[IP_1]") == "10.0.0.1"


def test_reverse_lookup_returns_none_for_unknown_token():
    reg = EntityRegistry()
    assert reg.reverse_lookup("[PERSON_99]") is None


def test_register_alias_maps_alias_to_token():
    reg = EntityRegistry()
    token = reg.register("John Doe", "PERSON")
    reg.register_alias("John", token)
    reg.register_alias("Doe", token)
    assert reg.lookup("John") == token
    assert reg.lookup("Doe") == token


def test_to_dict_from_dict_round_trip():
    reg = EntityRegistry()
    reg.register("Jane Smith", "PERSON")
    reg.register("jane@example.com", "EMAIL")
    reg.register_alias("Jane", "[PERSON_1]")

    data = reg.to_dict()
    reg2 = EntityRegistry.from_dict(data)

    assert reg2.lookup("Jane Smith") == "[PERSON_1]"
    assert reg2.lookup("jane@example.com") == "[EMAIL_1]"
    assert reg2.lookup("Jane") == "[PERSON_1]"
    assert reg2.reverse_lookup("[PERSON_1]") == "Jane Smith"
    assert reg2.reverse_lookup("[EMAIL_1]") == "jane@example.com"


def test_from_dict_preserves_counters():
    reg = EntityRegistry()
    reg.register("A", "PERSON")
    reg.register("B", "PERSON")

    reg2 = EntityRegistry.from_dict(reg.to_dict())
    # Next register should increment from 3
    token = reg2.register("C", "PERSON")
    assert token == "[PERSON_3]"
