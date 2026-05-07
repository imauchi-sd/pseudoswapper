from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".pseudoswapper_config.yaml"
PREFS_PATH = Path.home() / ".pseudoswapper_prefs.yaml"

# CSV columns that map to employee dict keys. Any column not in this list is ignored.
_EMPLOYEE_CSV_COLUMNS = {"full_name", "email", "username"}


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


def load_employees_csv(path: Path) -> list[dict]:
    """Load an employee list from a CSV file.

    Required column: full_name. Optional: email, username.
    Rows missing full_name are silently skipped.
    Returns a list of dicts compatible with the YAML employees format.
    """
    import csv

    if not path.exists():
        raise ConfigError(f"Employees CSV not found: {path}")

    employees: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return employees
        # Normalise header names to lowercase for flexible matching
        headers = {h.strip().lower(): h for h in reader.fieldnames}
        if "full_name" not in headers:
            raise ConfigError(
                f"Employees CSV {path} must have a 'full_name' column "
                f"(found: {list(reader.fieldnames)})"
            )
        for row in reader:
            # Re-key using normalised names
            norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
            full_name = norm.get("full_name", "")
            if not full_name:
                continue
            emp: dict = {"full_name": full_name}
            if norm.get("email"):
                emp["email"] = norm["email"]
            if norm.get("username"):
                emp["username"] = norm["username"]
            employees.append(emp)

    return employees


def _merge_employees(base: list[dict], extra: list[dict]) -> list[dict]:
    """Merge two employee lists, deduplicating by full_name (extra wins on conflict)."""
    merged = {e["full_name"]: e for e in base if e.get("full_name")}
    for emp in extra:
        if emp.get("full_name"):
            merged[emp["full_name"]] = emp
    return list(merged.values())


def load_config(path: Path = DEFAULT_CONFIG_PATH, employees_csv: Path | None = None) -> dict:
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

    # Load CSV referenced in the config file, if present
    config_csv = data.pop("employees_csv", None)
    if config_csv:
        csv_path = Path(config_csv).expanduser()
        data["employees"] = _merge_employees(
            data["employees"], load_employees_csv(csv_path)
        )

    # CLI-supplied CSV takes priority over config-file CSV
    if employees_csv is not None:
        data["employees"] = _merge_employees(
            data["employees"], load_employees_csv(employees_csv)
        )

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


def _load_prefs() -> dict:
    if not PREFS_PATH.exists():
        return {}
    with PREFS_PATH.open() as f:
        return yaml.safe_load(f) or {}


def _save_prefs(prefs: dict) -> None:
    with PREFS_PATH.open("w") as f:
        yaml.dump(prefs, f, default_flow_style=False)


def get_work_dir() -> Path | None:
    wd = _load_prefs().get("work_dir")
    return Path(wd).expanduser().resolve() if wd else None


def set_work_dir(path: Path) -> None:
    prefs = _load_prefs()
    prefs["work_dir"] = str(path.resolve())
    _save_prefs(prefs)


def clear_work_dir() -> None:
    prefs = _load_prefs()
    prefs.pop("work_dir", None)
    _save_prefs(prefs)
