import unittest.mock as mock

import pytest
from typer.testing import CliRunner

from pseudoswapper.cli import app
from pseudoswapper.config import ConfigError, _require, default_config, get_mode, load_config, set_mode


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


def test_load_config_includes_passthrough_types(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("passthrough_types:\n  - IP\n  - DOMAIN\n")
    result = load_config(cfg)
    assert "IP" in result["passthrough_types"]
    assert "DOMAIN" in result["passthrough_types"]


def test_load_config_passthrough_defaults_to_empty(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("")
    assert load_config(cfg)["passthrough_types"] == []


def test_default_config_has_passthrough_types_key():
    assert "passthrough_types" in default_config()
    assert default_config()["passthrough_types"] == []


# --- config --summary ---

def _invoke_summary(config_dict: dict) -> str:
    runner = CliRunner()
    with mock.patch("pseudoswapper.cli.load_config", return_value=config_dict):
        result = runner.invoke(app, ["config", "--summary"])
    assert result.exit_code == 0
    return result.output


def test_summary_shows_protected_types():
    out = _invoke_summary(default_config())
    assert "Always tokenized (protected)" in out
    assert "[PERSON]" in out
    assert "[EMAIL]" in out
    assert "[COMPANY]" in out
    assert "[ORG]" in out


def test_summary_shows_all_bypassable_types_when_none_bypassed():
    out = _invoke_summary(default_config())
    assert "[IP]" in out
    assert "[DOMAIN]" in out
    assert "[URL]" in out
    assert "[PHONE]" in out
    assert "[LOC]" in out
    assert "Bypassed" not in out


def test_summary_shows_bypassed_section_when_passthrough_set():
    cfg = default_config()
    cfg["passthrough_types"] = ["IP", "DOMAIN"]
    out = _invoke_summary(cfg)
    assert "Bypassed" in out
    assert "[IP]" in out
    assert "[DOMAIN]" in out
    # Non-bypassed types should still appear under Tokenized
    assert "[URL]" in out


def test_summary_bypassed_section_omits_protected_types():
    cfg = default_config()
    cfg["passthrough_types"] = ["PERSON", "EMAIL", "IP"]  # PERSON/EMAIL must be ignored
    out = _invoke_summary(cfg)
    # Protected types should appear under "Always tokenized", not under "Bypassed"
    assert out.index("Always tokenized") < out.index("[PERSON]")
    assert "Bypassed" in out
    assert "[IP]" in out


def test_summary_shows_company_terms():
    cfg = default_config()
    cfg["company_terms"] = ["Acme Corp", "Project Nightingale"]
    out = _invoke_summary(cfg)
    assert "EXACT-MATCH TERMS  (2 configured)" in out
    assert "Acme Corp" in out
    assert "Project Nightingale" in out


def test_summary_shows_employees():
    cfg = default_config()
    cfg["employees"] = [
        {"full_name": "John Doe", "email": "j@a.com", "username": "jdoe"},
        {"full_name": "Jane Smith"},
    ]
    out = _invoke_summary(cfg)
    assert "PRE-REGISTERED EMPLOYEES  (2)" in out
    assert "John Doe" in out
    assert "j@a.com" in out
    assert "jdoe" in out
    assert "Jane Smith" in out


def test_summary_shows_exclude_terms():
    cfg = default_config()
    cfg["exclude_terms"] = ["Will", "May"]
    out = _invoke_summary(cfg)
    assert "EXCLUDED FROM NLP  (2 terms)" in out
    assert "Will" in out
    assert "May" in out


def test_summary_shows_structured_settings():
    cfg = default_config()
    cfg["structured"]["anchor_field"] = "employee_id"
    cfg["structured"]["correlated_fields"] = ["email", "username"]
    cfg["structured"]["force_fields"] = ["Last name, First name"]
    out = _invoke_summary(cfg)
    assert "employee_id" in out
    assert "email, username" in out
    assert "Last name, First name" in out


def test_summary_shows_auto_detect_when_no_anchor():
    out = _invoke_summary(default_config())
    assert "(auto-detect)" in out


def test_summary_shows_active_mode():
    out = _invoke_summary(default_config())
    assert "Active mode:" in out


def test_summary_shows_masking_rules_when_configured():
    cfg = default_config()
    cfg["masking_rules"] = {
        "PERSON": {"keep": "initials"},
        "CREDIT_CARD": {"keep_first": 6, "keep_last": 4, "fill_char": "X"},
    }
    out = _invoke_summary(cfg)
    assert "MASKING RULES  (2 configured)" in out
    assert "initials + sequence number" in out
    assert "first 6 + last 4 digits" in out


def test_summary_shows_no_masking_rules_when_empty():
    out = _invoke_summary(default_config())
    assert "MASKING RULES  (0 configured)" in out
    assert "none" in out


# --- get_mode / set_mode ---

def test_get_mode_defaults_to_tokenize(tmp_path):
    with mock.patch("pseudoswapper.config.PREFS_PATH", tmp_path / "prefs.yaml"):
        assert get_mode() == "tokenize"


def test_set_mode_mask_persists(tmp_path):
    with mock.patch("pseudoswapper.config.PREFS_PATH", tmp_path / "prefs.yaml"):
        set_mode("mask")
        assert get_mode() == "mask"


def test_set_mode_tokenize_reverts(tmp_path):
    with mock.patch("pseudoswapper.config.PREFS_PATH", tmp_path / "prefs.yaml"):
        set_mode("mask")
        set_mode("tokenize")
        assert get_mode() == "tokenize"


def test_set_mode_invalid_raises(tmp_path):
    with mock.patch("pseudoswapper.config.PREFS_PATH", tmp_path / "prefs.yaml"):
        with pytest.raises(ConfigError, match="Invalid mode"):
            set_mode("redact")


def test_set_mode_does_not_clobber_work_dir(tmp_path):
    prefs_path = tmp_path / "prefs.yaml"
    with mock.patch("pseudoswapper.config.PREFS_PATH", prefs_path):
        from pseudoswapper.config import set_work_dir, get_work_dir
        set_work_dir(tmp_path)
        set_mode("mask")
        assert get_work_dir() == tmp_path.resolve()
        assert get_mode() == "mask"


# --- mode CLI command ---

def _prefs_patch(tmp_path):
    return mock.patch("pseudoswapper.config.PREFS_PATH", tmp_path / "prefs.yaml")


def test_mode_cmd_no_args_shows_current(tmp_path):
    runner = CliRunner()
    with _prefs_patch(tmp_path):
        result = runner.invoke(app, ["mode"])
    assert result.exit_code == 0
    assert "tokenize" in result.output


def test_mode_cmd_show_flag(tmp_path):
    runner = CliRunner()
    with _prefs_patch(tmp_path):
        result = runner.invoke(app, ["mode", "--show"])
    assert result.exit_code == 0
    assert "tokenize" in result.output


def test_mode_cmd_set_mask(tmp_path):
    runner = CliRunner()
    with _prefs_patch(tmp_path):
        result = runner.invoke(app, ["mode", "mask"])
        assert result.exit_code == 0
        assert "mask" in result.output
        assert get_mode() == "mask"


def test_mode_cmd_set_tokenize(tmp_path):
    runner = CliRunner()
    with _prefs_patch(tmp_path):
        set_mode("mask")
        result = runner.invoke(app, ["mode", "tokenize"])
        assert result.exit_code == 0
        assert "tokenize" in result.output
        assert get_mode() == "tokenize"


def test_mode_cmd_invalid_value_exits_nonzero(tmp_path):
    runner = CliRunner()
    with _prefs_patch(tmp_path):
        result = runner.invoke(app, ["mode", "redact"])
    assert result.exit_code != 0
    assert "Invalid mode" in result.output
