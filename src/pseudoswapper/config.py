from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".pseudoswapper_config.yaml"


class ConfigError(Exception):
    pass


def _require(data: dict, dot_path: str):
    """Raise ConfigError if dot_path is absent or None in data."""
    keys = dot_path.split(".")
    node = data
    for key in keys:
        if not isinstance(node, dict) or key not in node or node[key] is None:
            raise ConfigError(f"Missing required config field: {dot_path}")
        node = node[key]
    return node


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.exists():
        raise ConfigError(
            f"Config file not found: {path}\n"
            f"Copy pseudoswapper_config.example.yaml to {path} and fill in your values."
        )
    with path.open() as f:
        data = yaml.safe_load(f) or {}

    data.setdefault("company_terms", [])
    data.setdefault("employees", [])
    data.setdefault("exclude_terms", [])
    data.setdefault("structured", {})
    data["structured"].setdefault("anchor_field", None)
    data["structured"].setdefault("correlated_fields", [])

    return data


def default_config() -> dict:
    """Return a valid config dict with all fields set to safe defaults."""
    return {
        "company_terms": [],
        "employees": [],
        "exclude_terms": [],
        "structured": {
            "anchor_field": None,
            "correlated_fields": [],
        },
    }
