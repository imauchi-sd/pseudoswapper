import os
import subprocess
from pathlib import Path
from typing import List, Optional

import typer
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from pseudoswapper.config import DEFAULT_CONFIG_PATH, ConfigError, get_mode, load_config

app = typer.Typer(
    name="pseudoswapper",
    help="Local sensitive data tokenisation tool. No data leaves your machine.",
    no_args_is_help=True,
)

_STRUCTURED_EXTENSIONS = {".csv", ".json", ".xlsx"}

_PROTECTED_TYPE_DESCRIPTIONS: dict[str, str] = {
    "PERSON":      "person names — NLP + pre-registered employees",
    "EMAIL":       "email addresses",
    "COMPANY":     "YAML company_terms + NLP organisation matches",
    "ORG":         "organisation names (NLP)",
    "CREDIT_CARD": "payment card numbers (PAN)",
}

_BYPASSABLE_TYPE_DESCRIPTIONS: dict[str, str] = {
    "PHONE":  "phone numbers",
    "IP":     "IP addresses",
    "DOMAIN": "domain names",
    "URL":    "URLs",
    "LOC":    "locations (NLP)",
}

_RULE_WIDTH = 58


def _rule(char: str = "─") -> None:
    typer.echo(char * _RULE_WIDTH)


def _print_config_summary(config: dict) -> None:
    from pseudoswapper.tokenizer import PROTECTED_TYPES

    passthrough: set[str] = (
        {t.upper() for t in config.get("passthrough_types", [])} - PROTECTED_TYPES
    )

    current_mode = get_mode()
    mode_label = "mask (permanent redaction)" if current_mode == "mask" else "tokenize (reversible)"

    typer.echo("")
    typer.echo("pseudoswapper — detection summary")
    _rule("═")
    typer.echo(f"Active mode:  {mode_label}  (change with 'pseudoswapper mode')")
    _rule()

    # ── Entity types ──────────────────────────────────────────────────────────
    typer.echo("ENTITY TYPES\n")
    typer.echo("  Always tokenized (protected)")
    for t, desc in _PROTECTED_TYPE_DESCRIPTIONS.items():
        typer.echo(f"    {f'[{t}]':<12}{desc}")

    active   = {t: d for t, d in _BYPASSABLE_TYPE_DESCRIPTIONS.items() if t not in passthrough}
    bypassed = {t: d for t, d in _BYPASSABLE_TYPE_DESCRIPTIONS.items() if t in passthrough}

    if active:
        typer.echo("\n  Tokenized")
        for t, desc in active.items():
            typer.echo(f"    {f'[{t}]':<12}{desc}")

    if bypassed:
        typer.echo("\n  Bypassed — will appear as-is in redacted output")
        for t, desc in bypassed.items():
            typer.echo(f"    {f'[{t}]':<12}{desc}")

    # ── Exact-match terms ─────────────────────────────────────────────────────
    typer.echo("")
    _rule()
    company_terms = config.get("company_terms", [])
    typer.echo(f"EXACT-MATCH TERMS  ({len(company_terms)} configured)")
    if company_terms:
        for term in company_terms:
            typer.echo(f"  {term}")
    else:
        typer.echo("  (none)")

    # ── Pre-registered employees ──────────────────────────────────────────────
    typer.echo("")
    _rule()
    employees = config.get("employees", [])
    typer.echo(f"PRE-REGISTERED EMPLOYEES  ({len(employees)})")
    if employees:
        for emp in employees:
            name = emp.get("full_name", "")
            extras = [emp[k] for k in ("email", "username") if emp.get(k)]
            suffix = ("   " + "   ".join(extras)) if extras else ""
            typer.echo(f"  {name}{suffix}")
    else:
        typer.echo("  (none)")

    # ── Excluded from NLP ─────────────────────────────────────────────────────
    typer.echo("")
    _rule()
    exclude = config.get("exclude_terms", [])
    typer.echo(f"EXCLUDED FROM NLP  ({len(exclude)} terms)")
    typer.echo(f"  {', '.join(str(t) for t in exclude)}" if exclude else "  (none)")

    # ── Masking rules ─────────────────────────────────────────────────────────
    typer.echo("")
    _rule()
    masking_rules = config.get("masking_rules", {})
    typer.echo(f"MASKING RULES  ({len(masking_rules)} configured)")
    if masking_rules:
        for mtype, rule in masking_rules.items():
            if mtype == "PERSON":
                typer.echo(f"  {f'[{mtype}]':<16}initials + sequence number  (e.g. 5_J.D.)")
            elif mtype == "CREDIT_CARD":
                kf = (rule or {}).get("keep_first", 6)
                kl = (rule or {}).get("keep_last", 4)
                fc = (rule or {}).get("fill_char", "X")
                typer.echo(f"  {f'[{mtype}]':<16}first {kf} + last {kl} digits, fill='{fc}'")
            else:
                typer.echo(f"  {f'[{mtype}]':<16}{rule}")
    else:
        typer.echo("  (none — all protected types are tokenized)")

    # ── Structured mode ───────────────────────────────────────────────────────
    typer.echo("")
    _rule()
    st = config.get("structured", {})
    anchor     = st.get("anchor_field") or "(auto-detect)"
    correlated = st.get("correlated_fields", [])
    force      = st.get("force_fields", [])
    typer.echo("STRUCTURED MODE")
    typer.echo(f"  Anchor field:      {anchor}")
    typer.echo(f"  Correlated fields: {', '.join(correlated) if correlated else '(none)'}")
    typer.echo(f"  Force-tokenized:   {', '.join(force) if force else '(none)'}")
    typer.echo("")


def _pick_file(work_dir: Path, mode: str) -> Path:
    """Interactively pick a file from *work_dir* filtered by *mode*."""
    if not work_dir.exists() or not work_dir.is_dir():
        typer.echo(f"Error: Work directory not found: {work_dir}", err=True)
        raise typer.Exit(1)

    candidates: list[Path] = []
    for f in sorted(work_dir.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower()
        if mode == "structured":
            if ext not in _STRUCTURED_EXTENSIONS or ".redacted" in f.name:
                continue
        elif mode == "document":
            if ext in _STRUCTURED_EXTENSIONS or ".redacted" in f.name:
                continue
        elif mode in ("dsar", "redact"):
            if ".redacted" in f.name:
                continue
        # mode == "restore": show all non-hidden files
        candidates.append(f)

    if not candidates:
        hint = {
            "structured": " (.csv, .json, .xlsx)",
            "document": " (non-structured text files)",
            "restore": "",
        }.get(mode, "")
        typer.echo(
            f"No eligible files found in work directory: {work_dir}{hint}", err=True
        )
        raise typer.Exit(1)

    typer.echo(f"\nFiles in {work_dir}:")
    for i, f in enumerate(candidates, 1):
        typer.echo(f"  {i}. {f.name}")

    raw = typer.prompt("\nSelect file number")
    try:
        idx = int(raw) - 1
        if not 0 <= idx < len(candidates):
            raise ValueError
    except ValueError:
        typer.echo("Invalid selection.", err=True)
        raise typer.Exit(1)

    return candidates[idx]


def _require_file(file: Optional[Path], mode: str) -> Path:
    """Return *file* if given, otherwise invoke the work-dir file picker."""
    if file is not None:
        if not file.exists():
            typer.echo(f"Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        if not file.is_file():
            typer.echo(f"Error: Not a file: {file}", err=True)
            raise typer.Exit(1)
        return file

    from pseudoswapper.config import get_work_dir
    work_dir = get_work_dir()
    if work_dir is None:
        typer.echo(
            "No file specified and no work directory set.\n"
            "Run 'pseudoswapper workdir --set PATH' to set one.",
            err=True,
        )
        raise typer.Exit(1)

    return _pick_file(work_dir, mode)


def _read_columns(file: Path) -> list[str]:
    suffix = file.suffix.lower()
    try:
        if suffix == ".csv":
            import pandas as pd
            from pseudoswapper.modes.structured import _detect_csv_skiprows
            skiprows = _detect_csv_skiprows(file)
            return list(pd.read_csv(file, nrows=0, skiprows=skiprows, dtype=str, encoding="utf-8-sig").columns)
        if suffix == ".json":
            import json
            data = json.loads(file.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else [data]
            return list(rows[0].keys()) if rows else []
        if suffix in (".xlsx", ".xls"):
            import pandas as pd
            return list(pd.read_excel(file, nrows=0, dtype=str).columns)
    except Exception:
        pass
    return []


def _prompt_force_fields(file: Path) -> list[str]:
    columns = _read_columns(file)
    if not columns:
        return []

    typer.echo(f"\nColumns in {file.name}:")
    for i, col in enumerate(columns, 1):
        typer.echo(f"  {i}. {col}")

    raw = typer.prompt(
        "\nSelect columns to force-tokenize (e.g. 1,4 — or Enter to skip)",
        default="",
        show_default=False,
    )
    if not raw.strip():
        return []

    selected: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part) - 1
            if 0 <= idx < len(columns):
                selected.append(columns[idx])
            else:
                typer.echo(f"  Ignoring out-of-range: {part}", err=True)
        except ValueError:
            typer.echo(f"  Ignoring invalid entry: '{part}'", err=True)
    return selected


def _resolve_redact_passthrough(
    config: dict,
    profile: Optional[str],
    cli_flags: Optional[List[str]],
) -> set[str]:
    from pseudoswapper.config import ConfigError, get_redact_profile
    profile_passthrough: set[str] = set()
    if profile:
        prof = get_redact_profile(config, profile)
        profile_passthrough = {t.upper() for t in prof.get("passthrough", [])}
    combined = profile_passthrough | {t.upper() for t in (cli_flags or [])}
    combined.discard("CREDIT_CARD")
    return combined


def _resolve_passthrough(config: dict, cli_flags: Optional[List[str]]) -> set[str]:
    """Merge YAML passthrough_types with CLI --passthrough flags into a single set."""
    from pseudoswapper.tokenizer import PROTECTED_TYPES
    combined = set(config.get("passthrough_types", [])) | set(cli_flags or [])
    return combined - PROTECTED_TYPES


def _resolve_masking_rules(config: dict, cli_mask: Optional[bool]) -> dict:
    """Return the masking_rules to apply: CLI flag > saved mode pref > default (tokenize).

    When active, masking_rules come from config. When inactive, an empty dict is returned
    so the Tokenizer falls back to pure tokenization.
    """
    if cli_mask is True:
        return config.get("masking_rules") or {}
    if cli_mask is False:
        return {}
    return config.get("masking_rules") or {} if get_mode() == "mask" else {}


@app.command()
def document(
    file: Optional[Path] = typer.Argument(None, help="Prose file to redact"),
    employees_csv: Optional[Path] = typer.Option(
        None, "--employees-csv", "-e",
        help="CSV file of employees to pre-register (full_name, email, username columns).",
    ),
    passthrough: Optional[List[str]] = typer.Option(
        None, "--passthrough",
        help=(
            "Entity type to leave unreplaced (repeatable). "
            "Valid values: IP, DOMAIN, URL, PHONE, LOC. "
            "Protected types (PERSON, EMAIL, COMPANY, ORG) are always tokenized."
        ),
    ),
    mask: Optional[bool] = typer.Option(
        None, "--mask/--no-mask",
        help=(
            "Apply masking rules from config (permanent redaction). "
            "Overrides the saved mode preference. "
            "Use 'pseudoswapper mode' to set a persistent default."
        ),
    ),
) -> None:
    """Redact sensitive data from a prose document (txt, email, report)."""
    file = _require_file(file, "document")

    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    passthrough_types = _resolve_passthrough(config, passthrough)
    masking_rules = _resolve_masking_rules(config, mask)

    from pseudoswapper.modes.document import redact_document
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            progress.add_task(f"Redacting {file.name}…", total=None)
            out = redact_document(
                file, config, Path.cwd(),
                passthrough_types=passthrough_types,
                masking_rules=masking_rules,
            )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Redacted: {out}")


@app.command()
def structured(
    file: Optional[Path] = typer.Argument(None, help="CSV, JSON, or XLSX file to redact"),
    anchor: Optional[str] = typer.Option(None, "--anchor", "-a", help="Column to use as entity anchor"),
    employees_csv: Optional[Path] = typer.Option(
        None, "--employees-csv", "-e",
        help="CSV file of employees to pre-register (full_name, email, username columns).",
    ),
    force_fields: Optional[List[str]] = typer.Option(
        None, "--force-fields",
        help="Column to always tokenize, bypassing NER (repeatable). If omitted, an interactive prompt is shown.",
    ),
    passthrough: Optional[List[str]] = typer.Option(
        None, "--passthrough",
        help=(
            "Entity type to leave unreplaced (repeatable). "
            "Valid values: IP, DOMAIN, URL, PHONE, LOC. "
            "Protected types (PERSON, EMAIL, COMPANY, ORG) are always tokenized."
        ),
    ),
    mask: Optional[bool] = typer.Option(
        None, "--mask/--no-mask",
        help=(
            "Apply masking rules from config (permanent redaction). "
            "Overrides the saved mode preference. "
            "Use 'pseudoswapper mode' to set a persistent default."
        ),
    ),
) -> None:
    """Redact sensitive data from a structured file (CSV, JSON, XLSX)."""
    file = _require_file(file, "structured")

    resolved_force_fields = list(force_fields) if force_fields else _prompt_force_fields(file)

    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    passthrough_types = _resolve_passthrough(config, passthrough)
    masking_rules = _resolve_masking_rules(config, mask)

    from pseudoswapper.modes.structured import redact_structured
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task(f"Processing {file.name}", total=None)

            def _on_row(i: int, total: int) -> None:
                if i == 0:
                    progress.update(task, total=total)
                progress.advance(task)

            out = redact_structured(
                file, config, Path.cwd(),
                cli_anchor=anchor,
                force_fields=resolved_force_fields,
                passthrough_types=passthrough_types,
                on_row=_on_row,
                masking_rules=masking_rules,
            )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Redacted: {out}")


@app.command()
def restore(
    file: Optional[Path] = typer.Argument(None, help="AI output file to restore"),
) -> None:
    """Restore original values in AI output using the current session."""
    file = _require_file(file, "restore")

    from pseudoswapper.restore import restore_file
    try:
        out = restore_file(file, Path.cwd())
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Restored: {out}")


@app.command(name="workdir")
def workdir_cmd(
    set_path: Optional[Path] = typer.Option(None, "--set", help="Set the work directory"),
    show: bool = typer.Option(False, "--show", help="Show the current work directory"),
    clear: bool = typer.Option(False, "--clear", help="Clear the work directory setting"),
) -> None:
    """Set or view the work directory used when no file is specified."""
    from pseudoswapper.config import clear_work_dir, get_work_dir, set_work_dir

    if set_path is not None:
        if not set_path.exists() or not set_path.is_dir():
            typer.echo(f"Error: Not a valid directory: {set_path}", err=True)
            raise typer.Exit(1)
        set_work_dir(set_path)
        typer.echo(f"Work directory set to: {set_path.resolve()}")
    elif show:
        wd = get_work_dir()
        typer.echo(f"Work directory: {wd}" if wd else "No work directory set.")
    elif clear:
        clear_work_dir()
        typer.echo("Work directory cleared.")
    else:
        typer.echo("Use --set PATH, --show, or --clear.")
        raise typer.Exit(1)


@app.command(name="clear-session")
def clear_session_cmd() -> None:
    """Abandon the current session and delete all session artifacts."""
    from pseudoswapper.session import clear_session
    clear_session(Path.cwd())
    typer.echo("Session cleared.")


@app.command(name="mode")
def mode_cmd(
    mode_value: Optional[str] = typer.Argument(
        None,
        help="'tokenize' — reversible tokens (default).  'mask' — permanent redaction using masking_rules from config.",
    ),
    show: bool = typer.Option(False, "--show", help="Show the current mode preference."),
) -> None:
    """Switch between tokenize and mask mode, or view the current setting.

    Tokenize mode (default): detected entities are replaced with reversible tokens
    like [PERSON_1] that can be restored after AI processing.

    Mask mode: entities with masking_rules in config are permanently redacted
    (e.g. names → '5_J.D.', card numbers → '411111XXXXXX1111').
    Other entity types still fall back to tokenization.

    The --mask / --no-mask flag on 'document' and 'structured' overrides this
    setting for a single run without changing the saved preference.
    """
    from pseudoswapper.config import ConfigError, set_mode

    if mode_value is None:
        current = get_mode()
        typer.echo(f"Mode: {current}")
        if not show:
            typer.echo("Use 'pseudoswapper mode tokenize' or 'pseudoswapper mode mask' to switch.")
        return

    if mode_value not in ("tokenize", "mask"):
        typer.echo(
            f"Error: Invalid mode '{mode_value}'. Must be 'tokenize' or 'mask'.", err=True
        )
        raise typer.Exit(1)

    try:
        set_mode(mode_value)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    label = "reversible tokenization" if mode_value == "tokenize" else "permanent redaction (masking)"
    typer.echo(f"Mode set to: {mode_value}  ({label})")


@app.command(name="config")
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Print the active config as YAML"),
    edit: bool = typer.Option(False, "--edit", help="Open config in $EDITOR"),
    summary: bool = typer.Option(
        False, "--summary",
        help="Show a human-readable summary of what will be tokenized",
    ),
) -> None:
    """View or edit the pseudoswapper config file."""
    if not show and not edit and not summary:
        typer.echo("Use --show, --summary, or --edit.")
        raise typer.Exit(1)

    if summary:
        try:
            config = load_config()
        except ConfigError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        _print_config_summary(config)

    if show:
        try:
            config = load_config()
            import yaml
            typer.echo(yaml.dump(config, default_flow_style=False))
        except ConfigError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    if edit:
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(DEFAULT_CONFIG_PATH)])


@app.command(name="dsar-redaction")
def dsar_redaction_cmd(
    file: Optional[Path] = typer.Argument(None, help="File to redact (any supported format)"),
    subject_config: Optional[Path] = typer.Option(
        None, "--subject-config", "-s",
        help=(
            "Path to a DSAR subject YAML file. "
            "If omitted, looks for dsar_subject.yaml in the current directory "
            "and launches an interactive setup wizard if it does not exist."
        ),
    ),
    employees_csv: Optional[Path] = typer.Option(
        None, "--employees-csv", "-e",
        help="CSV file of employees to pre-register (full_name, email, username columns).",
    ),
    anchor: Optional[str] = typer.Option(
        None, "--anchor", "-a",
        help="Anchor column for structured files (CSV/JSON/XLSX). Auto-detected if omitted.",
    ),
) -> None:
    """Redact all PII except the data subject's own information (DSAR use case).

    Always runs in mask mode — other people's names, card numbers, and other PII
    are permanently redacted. The data subject's own values (as defined in the
    subject config) are preserved exactly as they appear in the source document.

    Supports the same file formats as the 'document' and 'structured' commands.
    Structured files (CSV, JSON, XLSX) are auto-detected by extension.

    Subject config YAML fields (all optional; at least one required):

      full_name, first_name, last_name, email, employee_id, phone, credit_card
    """
    from pseudoswapper.dsar import (
        DSARSubjectError,
        extract_subject_values,
        load_subject,
        prompt_and_save_subject,
        resolve_subject_path,
    )

    file = _require_file(file, "dsar")

    subject_path = resolve_subject_path(subject_config, Path.cwd())

    if subject_path.exists():
        try:
            subject_data = load_subject(subject_path)
        except DSARSubjectError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Subject config: {subject_path}")
    else:
        if subject_config is not None:
            typer.echo(f"Error: Subject config not found: {subject_config}", err=True)
            raise typer.Exit(1)
        typer.echo(f"No subject config found at: {subject_path}")
        subject_data = prompt_and_save_subject(subject_path)

    subject_values = extract_subject_values(subject_data)

    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # DSAR always uses mask mode. Fall back to sensible defaults if the user
    # has not configured masking_rules in their main config.
    masking_rules: dict = config.get("masking_rules") or {"PERSON": {}, "CREDIT_CARD": {}}

    is_structured = file.suffix.lower() in _STRUCTURED_EXTENSIONS

    try:
        if is_structured:
            from pseudoswapper.modes.structured import redact_structured

            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task(f"Processing {file.name}", total=None)

                def _on_row(i: int, total: int) -> None:
                    if i == 0:
                        progress.update(task, total=total)
                    progress.advance(task)

                out = redact_structured(
                    file, config, Path.cwd(),
                    cli_anchor=anchor,
                    passthrough_types=set(),
                    on_row=_on_row,
                    masking_rules=masking_rules,
                    subject_values=subject_values,
                )
        else:
            from pseudoswapper.modes.document import redact_document

            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                TimeElapsedColumn(),
                transient=True,
            ) as progress:
                progress.add_task(f"Redacting {file.name}…", total=None)
                out = redact_document(
                    file, config, Path.cwd(),
                    passthrough_types=set(),
                    masking_rules=masking_rules,
                    subject_values=subject_values,
                )
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Redacted: {out}")


@app.command(name="redact")
def redact_cmd(
    target: Optional[Path] = typer.Argument(None, help="File or directory to permanently redact"),
    passthrough: Optional[List[str]] = typer.Option(
        None, "--passthrough",
        help=(
            "Entity type to leave unreplaced (repeatable). "
            "Accepts any type including PERSON, EMAIL, COMPANY, ORG. "
            "CREDIT_CARD is always redacted regardless of this flag."
        ),
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p",
        help="Named redaction profile from config redact_profiles section.",
    ),
    employees_csv: Optional[Path] = typer.Option(
        None, "--employees-csv", "-e",
        help="CSV file of employees to pre-register (full_name, email, username columns).",
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r",
        help="Recurse into subdirectories (directory mode only).",
    ),
) -> None:
    """Permanently redact sensitive data with no session and no restore path.

    Unlike 'document' and 'structured', output files are the final artifact —
    there is no restore step. CREDIT_CARD is always redacted. All other entity
    types (including PERSON, EMAIL, COMPANY, ORG) can be passthroughed via
    --passthrough or a named --profile defined in config.

    Supports all file formats: txt, docx, pdf, csv, json, xlsx (all sheets).

    When TARGET is a directory, all supported files in it are redacted in one
    pass using a shared entity registry (same name → same mask across files).
    Use --recursive to include subdirectories.
    """
    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    try:
        passthrough_types = _resolve_redact_passthrough(config, profile, passthrough)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Directory mode
    if target is not None and target.is_dir():
        from pseudoswapper.modes.redact import SUPPORTED_BATCH_EXTENSIONS, redact_batch
        typer.echo(f"Redacting files in: {target}")
        typer.echo(f"Extensions: {', '.join(sorted(SUPPORTED_BATCH_EXTENSIONS))}")
        if recursive:
            typer.echo("Mode: recursive")
        typer.echo("")

        results_store: list[tuple[str, bool, str]] = []

        def _on_file(file: Path, success: bool, msg: str) -> None:
            tick = "✓" if success else "✗"
            typer.echo(f"  {tick} {file.name}  →  {msg}")
            results_store.append((file.name, success, msg))

        try:
            summary = redact_batch(
                target, config,
                passthrough_types=passthrough_types,
                recursive=recursive,
                on_file=_on_file,
            )
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        typer.echo("")
        typer.echo(f"Done: {summary['succeeded']} succeeded, {summary['failed']} failed, {summary['processed']} total")
        if summary["failed"]:
            raise typer.Exit(1)
        return

    # Single-file mode (existing behaviour)
    file = _require_file(target, "redact")

    from pseudoswapper.modes.redact import redact_file

    is_structured = file.suffix.lower() in _STRUCTURED_EXTENSIONS

    try:
        if is_structured:
            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                transient=True,
            ) as progress:
                task = progress.add_task(f"Redacting {file.name}", total=None)

                def _on_row(i: int, total: int) -> None:
                    if i == 0:
                        progress.update(task, total=total)
                    progress.advance(task)

                out = redact_file(file, config, passthrough_types=passthrough_types, on_row=_on_row)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                TimeElapsedColumn(),
                transient=True,
            ) as progress:
                progress.add_task(f"Redacting {file.name}…", total=None)
                out = redact_file(file, config, passthrough_types=passthrough_types)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Redacted: {out}")
