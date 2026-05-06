import os
import subprocess
from pathlib import Path
from typing import Optional

import typer

from pseudoswapper.config import DEFAULT_CONFIG_PATH, ConfigError, load_config

app = typer.Typer(
    name="pseudoswapper",
    help="Local sensitive data tokenisation tool. No data leaves your machine.",
    no_args_is_help=True,
)


@app.command()
def document(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Prose file to redact"),
) -> None:
    """Redact sensitive data from a prose document (txt, email, report)."""
    try:
        config = load_config()
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
    file: Path = typer.Argument(..., exists=True, readable=True, help="CSV, JSON, or XLSX file to redact"),
    anchor: Optional[str] = typer.Option(None, "--anchor", "-a", help="Column to use as entity anchor"),
) -> None:
    """Redact sensitive data from a structured file (CSV, JSON, XLSX)."""
    try:
        config = load_config()
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    from pseudoswapper.modes.structured import redact_structured
    try:
        out = redact_structured(file, config, Path.cwd(), cli_anchor=anchor)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Redacted: {out}")


@app.command()
def restore(
    file: Path = typer.Argument(..., exists=True, readable=True, help="AI output file to restore"),
) -> None:
    """Restore original values in AI output using the current session."""
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
