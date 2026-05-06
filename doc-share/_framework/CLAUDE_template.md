# <project-name> — Claude Instructions

## After completing any implementation work

Before ending a session, always update:

1. **`DESIGN.md` → Implementation Roadmap** — mark the phase ✅ Done if it just finished; leave ⬜ Not started for future ones.
2. **`.claude/memory/project_<name>.md`** — update "Current state" line and the "Phases complete" list.
3. **`.claude/memory/MEMORY.md`** — update the one-line summary to reflect the new phase count.

If the implementation revealed a divergence from the design doc (field names, logic, etc.), fix the affected section in `DESIGN.md` and/or `ADMIN_GUIDE.md` at the same time.

## Project conventions

- CLI entry point: `<toolname>` (installed via `pip install -e ".[dev]"`)
- Tests: `python3 -m pytest` — all tests must pass before a phase is marked done
- Reference files are in `references/` and are read-only ground truth
- `workspace.yaml` is gitignored (contains org-specific data); `workspace.yaml.example` is the committed template

## Patterns in use

This project follows the patterns documented in `_framework/`. Read them before making structural changes:

- `PATTERN_cli_structure.md` — command layout, wizard, mode registry
- `PATTERN_workdir.md` — working directory state machine
- `PATTERN_config.md` — two-level YAML config
- `PATTERN_testing.md` — fixture-based testing, no mocks

---
<!-- Replace all <placeholders> before committing this file. -->
