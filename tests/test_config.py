import pytest

from pseudoswapper.config import ConfigError, _require, default_config, load_config


# --- load_config ---

def test_load_config_returns_dict_for_valid_yaml(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "company_terms:\n  - Acme Corp\n"
        "employees:\n  - full_name: John Doe\n    email: john.doe@acme.com\n"
    )
    result = load_config(cfg)
    assert "Acme Corp" in result["company_terms"]
    assert result["employees"][0]["full_name"] == "John Doe"


def test_load_config_raises_on_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_config_empty_file_returns_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("")
    result = load_config(cfg)
    assert result["company_terms"] == []
    assert result["employees"] == []
    assert result["exclude_terms"] == []
    assert result["structured"]["correlated_fields"] == []
    assert result["structured"]["anchor_field"] is None


def test_load_config_fills_missing_optional_fields(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("company_terms:\n  - Acme\n")
    result = load_config(cfg)
    assert result["exclude_terms"] == []
    assert "structured" in result
    assert result["structured"]["anchor_field"] is None


def test_load_config_preserves_structured_settings(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "structured:\n  anchor_field: employee_id\n  correlated_fields:\n    - email\n"
    )
    result = load_config(cfg)
    assert result["structured"]["anchor_field"] == "employee_id"
    assert "email" in result["structured"]["correlated_fields"]


# --- _require ---

def test_require_returns_value_for_present_key():
    assert _require({"a": {"b": 42}}, "a.b") == 42


def test_require_raises_for_missing_key():
    with pytest.raises(ConfigError, match="a.c"):
        _require({"a": {"b": 1}}, "a.c")


def test_require_raises_for_null_value():
    with pytest.raises(ConfigError, match="anchor_field"):
        _require({"anchor_field": None}, "anchor_field")


def test_require_raises_for_missing_nested_key():
    with pytest.raises(ConfigError, match="structured.anchor_field"):
        _require({"structured": {}}, "structured.anchor_field")


# --- default_config ---

def test_default_config_has_all_required_keys():
    config = default_config()
    assert "company_terms" in config
    assert "employees" in config
    assert "exclude_terms" in config
    assert "structured" in config
    assert "anchor_field" in config["structured"]
    assert "correlated_fields" in config["structured"]


def test_default_config_all_lists_are_empty():
    config = default_config()
    assert config["company_terms"] == []
    assert config["employees"] == []
    assert config["exclude_terms"] == []
    assert config["structured"]["correlated_fields"] == []


def test_default_config_returns_independent_copies():
    a = default_config()
    b = default_config()
    a["company_terms"].append("Acme")
    assert b["company_terms"] == []
