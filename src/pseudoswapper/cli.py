import os
import subprocess
from pathlib import Path
from typing import List, Optional

import typer

from pseudoswapper.config import DEFAULT_CONFIG_PATH, ConfigError, load_config

app = typer.Typer(
    name="pseudoswapper",
    help="Local sensitive data tokenisation tool. No data leaves your machine.",
    no_args_is_help=True,
)

_STRUCTURED_EXTENSIONS = {".csv", ".json", ".xlsx"}


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
            return list(pd.read_csv(file, nrows=0, dtype=str).columns)
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


@app.command()
def document(
    file: Optional[Path] = typer.Argument(None, help="Prose file to redact"),
    employees_csv: Optional[Path] = typer.Option(
        None, "--employees-csv", "-e",
        help="CSV file of employees to pre-register (full_name, email, username columns).",
    ),
) -> None:
    """Redact sensitive data from a prose document (txt, email, report)."""
    file = _require_file(file, "document")

    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    from pseudoswapper.modes.document import redact_document
    try:
        out = redact_document(file, config, Path.cwd())
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
) -> None:
    """Redact sensitive data from a structured file (CSV, JSON, XLSX)."""
    file = _require_file(file, "structured")

    resolved_force_fields = list(force_fields) if force_fields else _prompt_force_fields(file)

    try:
        config = load_config(employees_csv=employees_csv)
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    from pseudoswapper.modes.structured import redact_structured
    try:
        out = redact_structured(file, config, Path.cwd(), cli_anchor=anchor, force_fields=resolved_force_fields)
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


@app.command(name="config")
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Print the active config"),
    edit: bool = typer.Option(False, "--edit", help="Open config in $EDITOR"),
) -> None:
    """View or edit the pseudoswapper config file."""
    if not show and not edit:
        typer.echo("Use --show to print config or --edit to open it in $EDITOR.")
        raise typer.Exit(1)

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
