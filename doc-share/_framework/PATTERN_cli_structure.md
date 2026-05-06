# Pattern: CLI Structure with Typer + Wizard + Mode Registry

## Problem it solves
A CLI tool that needs multiple subcommands, optional interactive file-selection when arguments are omitted, and the ability to swap out backend strategies (modes) without changing command definitions.

## Shape

```
src/<package>/
├── cli.py             # Typer app + all subcommand definitions (thin layer)
├── wizard.py          # Interactive multi-step setup wizards
├── mode_registry.py   # Maps mode name strings to implementation classes
└── providers/
    ├── base.py        # Abstract base classes HRSource / IdPSource (or equivalent)
    └── <name>.py      # One file per concrete provider implementation
```

### pyproject.toml wiring
```toml
[project.scripts]
<toolname> = "<package>.cli:app"
```
Install with `pip install -e ".[dev]"` so the CLI is available as a real shell command.

## Key decisions from access-review

### Commands are thin
Every `@app.command` does only:
1. Load work dir and config
2. Resolve file paths (via `resolve_path` / `pick_file`)
3. Print a "Ready to run" summary and confirm
4. Call the pure business-logic function
5. Echo the output path

No logic lives in `cli.py` itself. Business logic lives in domain modules (`sot.py`, `audit.py`, etc.).

### File arguments are optional — with interactive fallback
Any `--file` argument can be omitted. When it is, `pick_file()` scans the work folder for matching extensions and presents a numbered list. The user picks a number or types a full path. This removes the need to copy-paste long paths for routine runs.

```python
if export is None:
    export = pick_file(wd, [".xlsx", ".csv"], "export")
```

### Confirm before running
After resolving all paths, print a one-liner showing the equivalent explicit command, then ask `Proceed? [y/N]`. This gives the user a final sanity check and also shows what a non-interactive invocation would look like.

### Mode registry pattern
Modes are string keys that map to implementation class pairs (or single classes). The registry lives in one file; adding a new mode requires only:
1. Implement provider class in `providers/`
2. Add one entry to `REGISTRY` and `ALL_MODES` in `mode_registry.py`

No other files need to change. The CLI's `switch-mode` command reads `ALL_MODES` dynamically.

```python
# mode_registry.py
REGISTRY: dict = {
    "bamboohr_jumpcloud": (BambooHRSource, JumpCloudSource),
}
ALL_MODES: dict[str, str] = {
    "bamboohr_jumpcloud": "Description shown in switch-mode",
    "import_prebuilt":    "Description shown in switch-mode",
}
```

### Wizard for first-run setup
Complex first-run configuration (e.g. creating `workspace.yaml` or per-item config files) is handled by an interactive wizard subcommand, not by asking the user to hand-edit YAML. The wizard prompts for each field, applies heuristics to suggest defaults (e.g. reading a sample export file to guess column names), and writes the YAML.

## What to adapt per project
- Command names and argument names
- Provider class interface (what `HRSource` / `IdPSource` expose)
- Which fields the wizard prompts for
- The set of modes in `ALL_MODES`

## What to keep as-is
- Thin command handlers — no logic in `cli.py`
- Optional file args with `pick_file()` fallback
- Confirm-before-run summary
- One file per provider in `providers/`
- `mode_registry.py` as the single place to register new modes
