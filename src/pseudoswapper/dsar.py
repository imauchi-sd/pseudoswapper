from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml

DSAR_SUBJECT_FIELDS: list[tuple[str, str]] = [
    ("full_name",    "Full Name"),
    ("first_name",   "First Name"),
    ("last_name",    "Last Name"),
    ("email",        "Email Address"),
    ("employee_id",  "Employee ID"),
    ("phone",        "Phone Number"),
    ("credit_card",  "Credit Card Number"),
]

DEFAULT_SUBJECT_FILENAME = "dsar_subject.yaml"

_RULE_WIDTH = 42


class DSARSubjectError(Exception):
    pass


def load_subject(path: Path) -> dict:
    """Load and validate a DSAR subject YAML file."""
    if not path.exists():
        raise DSARSubjectError(f"Subject config not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise DSARSubjectError(f"Invalid YAML in subject config: {e}")
    if not isinstance(data, dict):
        raise DSARSubjectError("Subject config must be a YAML mapping.")
    _validate_subject(data)
    return data


def _validate_subject(data: dict) -> None:
    known_keys = {k for k, _ in DSAR_SUBJECT_FIELDS}
    has_value = any(
        data.get(k) and str(data[k]).strip()
        for k in known_keys
    )
    if not has_value:
        raise DSARSubjectError(
            "Subject config must have at least one non-empty field: "
            + ", ".join(k for k, _ in DSAR_SUBJECT_FIELDS)
        )


def prompt_and_save_subject(save_path: Path) -> dict:
    """Interactively collect subject PII values and save to *save_path*."""
    typer.echo("\nDSAR Subject Setup")
    typer.echo("─" * _RULE_WIDTH)
    typer.echo("Enter the data subject's known PII values.")
    typer.echo("All fields are optional — at least one is required.\n")

    data: dict = {}
    for key, label in DSAR_SUBJECT_FIELDS:
        val = typer.prompt(f"  {label}", default="", show_default=False).strip()
        if val:
            data[key] = val

    try:
        _validate_subject(data)
    except DSARSubjectError as e:
        typer.echo(f"\nError: {e}", err=True)
        raise typer.Exit(1)

    save_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    typer.echo(f"\nSubject config saved: {save_path}")
    return data


def resolve_subject_path(subject_config: Optional[Path], cwd: Path) -> Path:
    """Return the subject config path to use.

    Explicit --subject-config takes precedence; otherwise look for the default
    filename in CWD (the caller should check .exists() and prompt if absent).
    """
    if subject_config is not None:
        return subject_config
    return cwd / DEFAULT_SUBJECT_FILENAME


def extract_subject_values(data: dict) -> frozenset[str]:
    """Return all PII strings from subject data, including derived name components.

    full_name is split into first/last components if those fields are not
    explicitly provided, so surface forms like "Jane" or "Doe" are also preserved
    when the document contains the subject's name in parts.
    """
    values: set[str] = set()

    for key, _ in DSAR_SUBJECT_FIELDS:
        val = data.get(key)
        if val and str(val).strip():
            values.add(str(val).strip())

    full_name = str(data.get("full_name") or "").strip()
    if full_name:
        parts = full_name.split()
        if len(parts) >= 2:
            if not str(data.get("first_name") or "").strip():
                values.add(parts[0])
            if not str(data.get("last_name") or "").strip():
                values.add(parts[-1])

    return frozenset(values)
