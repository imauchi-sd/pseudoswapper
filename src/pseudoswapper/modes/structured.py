from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pseudoswapper.detector import Detector
from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.replacer import replace
from pseudoswapper.session import create_session, save_session, session_exists
from pseudoswapper.tokenizer import Tokenizer

_AUTO_ANCHOR_CANDIDATES = [
    "employee_id",
    "user_id",
    "userid",
    "employeeid",
    "username",
    "user_name",
    "full_name",
    "fullname",
    "name",
    "employee",
    "user",
]


def _resolve_anchor(
    columns: list[str],
    cli_anchor: str | None,
    config: dict,
) -> str | None:
    lower_to_col = {c.lower(): c for c in columns}

    if cli_anchor:
        if cli_anchor in columns:
            return cli_anchor
        if cli_anchor.lower() in lower_to_col:
            return lower_to_col[cli_anchor.lower()]

    config_anchor = (config.get("structured") or {}).get("anchor_field")
    if config_anchor:
        if config_anchor in columns:
            return config_anchor
        if config_anchor.lower() in lower_to_col:
            return lower_to_col[config_anchor.lower()]

    for candidate in _AUTO_ANCHOR_CANDIDATES:
        if candidate in lower_to_col:
            return lower_to_col[candidate]

    return None


def _person_n(token: str) -> int | None:
    m = re.search(r"\[PERSON_(\d+)", token, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    # Treat pandas NA string representations as empty
    return "" if s.lower() in ("nan", "none", "<na>") else s


def _force_tokenize_cell(val: str, registry: EntityRegistry, tokenizer: Tokenizer) -> str:
    """Tokenize *val* unconditionally, bypassing NER detection."""
    existing = registry.lookup(val)
    if existing:
        return existing
    if "@" in val:
        return registry.register(val, "EMAIL")
    return tokenizer._assign_person(val)


def _redact_cell(val: str, detector: Detector, tokenizer: Tokenizer) -> str:
    """Detect and tokenize PII in a single cell value.

    When detected spans cover ≥70% of the cell and at least one is PERSON,
    the whole value is treated as a compound person name rather than doing
    span-level replacement. This prevents last-name/first-name fields in
    "Last, First" format from being split into ORG + PERSON tokens.
    """
    entities = detector.analyze(val)
    if not entities:
        return val
    has_person = any(e.entity_type == "PERSON" for e in entities)
    if has_person:
        covered = sum(e.end - e.start for e in entities)
        if covered / len(val) >= 0.7:
            return tokenizer._assign_person(val)
    token_map = tokenizer.assign(entities)
    return replace(val, token_map)


def _process_rows(
    rows: list[dict],
    anchor_field: str | None,
    config: dict,
    tokenizer: Tokenizer,
    registry: EntityRegistry,
    detector: Detector,
    force_fields: list[str] | None = None,
    on_row: Callable[[int, int], None] | None = None,
) -> list[dict]:
    correlated: set[str] = set(
        (config.get("structured") or {}).get("correlated_fields", [])
    )
    forced: set[str] = set(force_fields or [])
    total = len(rows)

    result_rows: list[dict] = []

    for i, row in enumerate(rows):
        if on_row:
            on_row(i, total)
        out = dict(row)

        # ── No anchor field resolved ─────────────────────────────────────
        if anchor_field is None:
            for field, value in row.items():
                val = _cell_str(value)
                if not val:
                    continue
                if field in forced:
                    out[field] = _force_tokenize_cell(val, registry, tokenizer)
                else:
                    out[field] = _redact_cell(val, detector, tokenizer)
            result_rows.append(out)
            continue

        anchor_raw = row.get(anchor_field)
        anchor_str = _cell_str(anchor_raw)

        # ── Null / empty anchor ──────────────────────────────────────────
        if not anchor_str:
            for field in correlated:
                if field == anchor_field or field not in row:
                    continue
                val = _cell_str(row[field])
                if not val:
                    continue
                existing = registry.lookup(val)
                if existing:
                    out[field] = existing
                elif "@" in val:
                    out[field] = registry.register(val, "EMAIL")
                else:
                    out[field] = registry.register(val, "PERSON")
            for field in forced:
                if field == anchor_field or field in correlated or field not in row:
                    continue
                val = _cell_str(row[field])
                if val:
                    out[field] = _force_tokenize_cell(val, registry, tokenizer)
            result_rows.append(out)
            continue

        # ── Normal row — register or retrieve anchor entity ──────────────
        existing_person = registry.lookup(anchor_str)
        if existing_person:
            person_token = existing_person
        else:
            person_token = tokenizer._assign_person(anchor_str)

        out[anchor_field] = person_token
        n = _person_n(person_token)

        # ── Correlated fields ────────────────────────────────────────────
        for field in correlated:
            if field == anchor_field or field not in row:
                continue
            val = _cell_str(row[field])
            if not val:
                continue
            existing = registry.lookup(val)
            if existing:
                out[field] = existing
            elif "@" in val and n is not None:
                out[field] = tokenizer.assign_correlated(val, n)
            else:
                # Non-email correlated value: alias to same person token
                registry.register_alias(val, person_token)
                out[field] = person_token

        # ── Remaining fields — detect then registry lookup ───────────────
        for field, value in row.items():
            if field == anchor_field or field in correlated:
                continue
            val = _cell_str(value)
            if not val:
                continue
            if field in forced:
                out[field] = _force_tokenize_cell(val, registry, tokenizer)
            else:
                out[field] = _redact_cell(val, detector, tokenizer)

        result_rows.append(out)

    return result_rows


def _output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}.redacted{input_path.suffix}"


def _read_file(file: Path) -> tuple[list[dict], list[str]]:
    suffix = file.suffix.lower()
    if suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(file, dtype=str, keep_default_na=False)
        return df.to_dict("records"), list(df.columns)
    elif suffix == ".json":
        data = json.loads(file.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        cols = list(rows[0].keys()) if rows else []
        return rows, cols
    elif suffix in (".xlsx", ".xls"):
        import pandas as pd
        df = pd.read_excel(file, dtype=str, keep_default_na=False)
        return df.to_dict("records"), list(df.columns)
    else:
        raise ValueError(f"Unsupported file type: {file.suffix}")


def _write_file(rows: list[dict], columns: list[str], out_path: Path) -> None:
    suffix = out_path.suffix.lower()
    if suffix == ".csv":
        import pandas as pd
        pd.DataFrame(rows, columns=columns).to_csv(out_path, index=False)
    elif suffix == ".json":
        out_path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    elif suffix in (".xlsx", ".xls"):
        import pandas as pd
        pd.DataFrame(rows, columns=columns).to_excel(out_path, index=False)
    else:
        raise ValueError(f"Unsupported output type: {out_path.suffix}")


def redact_structured(
    file: Path,
    config: dict,
    cwd: Path,
    cli_anchor: str | None = None,
    force_fields: list[str] | None = None,
    passthrough_types: set[str] | None = None,
    on_row: Callable[[int, int], None] | None = None,
) -> Path:
    """Run structured mode: read → anchor resolution → row processing → write → save session."""
    from pseudoswapper.modes.document import _pre_register_employees

    registry = EntityRegistry()
    tokenizer = Tokenizer(registry, passthrough_types=passthrough_types)
    detector = Detector(config)
    _pre_register_employees(config, tokenizer)

    rows, columns = _read_file(file)
    anchor_field = _resolve_anchor(columns, cli_anchor, config)

    config_force_fields: list[str] = (config.get("structured") or {}).get("force_fields", [])
    resolved_force_fields = force_fields if force_fields is not None else config_force_fields

    processed = _process_rows(rows, anchor_field, config, tokenizer, registry, detector, resolved_force_fields, on_row=on_row)

    out = _output_path(file)
    _write_file(processed, columns, out)

    if session_exists(cwd):
        save_session(registry, cwd)
    else:
        create_session(registry, cwd)

    return out
