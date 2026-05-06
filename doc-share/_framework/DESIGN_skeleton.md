# Design Document — <project-name>

This document captures the architecture, data flows, configuration schema, and key design decisions for the `<toolname>` CLI tool. It is the authoritative reference for contributors and for understanding why the tool is built the way it is.

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Module Responsibilities](#module-responsibilities)
4. [Workflow: <primary-workflow>](#workflow-primary)
5. [Configuration Schema](#configuration-schema)
6. [Design Decisions](#design-decisions)
7. [Implementation Roadmap](#implementation-roadmap)
8. [Known Limitations and Deferred Items](#known-limitations-and-deferred-items)

---

## Overview

<!-- 2-3 sentences: what the tool does, what problem it replaces, what it does NOT do -->

Everything runs locally. No data is transmitted to any external service.

---

## Project Structure

```
<project-root>/
├── pyproject.toml                  # package definition; installs CLI as "<toolname>"
├── workspace.yaml                  # org config — filled in per installation (not committed)
├── workspace.yaml.example          # committed template for workspace.yaml
├── apps/                           # or equivalent item config directory
│   ├── _template.yaml              # documented template for per-item configs
│   └── <item-name>.yaml
├── references/                     # read-only ground truth (VBA, specs, sample schemas)
├── src/<package>/
│   ├── cli.py                      # Typer entry point; all subcommands (thin layer)
│   ├── config.py                   # loads and validates workspace.yaml + item configs
│   ├── workdir.py                  # work folder state: save/load/clear + resolve_path
│   ├── wizard.py                   # interactive setup wizards
│   ├── mode_registry.py            # maps mode name strings to implementation classes
│   ├── providers/                  # one file per backend provider
│   │   ├── base.py
│   │   └── <name>.py
│   └── <domain>.py                 # core business logic (no I/O in pure functions)
└── tests/
    ├── fixtures/                   # redacted sample files
    └── test_<module>.py
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `cli.py` | Command definitions only — no logic. Resolves paths, confirms, calls domain functions. |
| `config.py` | Loads and validates YAML configs. Raises `ConfigError` on missing fields. |
| `workdir.py` | Persists work folder to `.toolstate`. `resolve_path` and `pick_file`. |
| `wizard.py` | Interactive multi-step prompts for first-run setup. |
| `mode_registry.py` | Maps mode name strings to provider class pairs. |
| `providers/<name>.py` | Reads one specific data source format. Implements base class interface. |
| `<domain>.py` | Pure business logic. Functions take dicts/DataFrames, return dicts/DataFrames. |

---

## Workflow: <primary-workflow>

<!-- Step-by-step: what the user runs, what files are read, what logic is applied, what is written. -->

---

## Configuration Schema

### workspace.yaml (org-level)

```yaml
# Required for all modes
company:
  name: "<org name>"
  domains:
    - "<primary domain>"

# Optional
sot_mode: bamboohr_jumpcloud    # default; see mode_registry.py for options
```

### apps/<name>.yaml (per-item)

```yaml
# Required
app_name: "<name>"
# ... (fill in per-project required fields)

# Optional with defaults
file_formats: [csv]
encoding: auto
```

---

## Design Decisions

<!-- Each entry: decision made, alternatives considered, reason chosen. -->

---

## Implementation Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Project scaffold, config loading, CLI skeleton | ⬜ Not started |
| 2 | Working directory state machine | ⬜ Not started |
| 3 | Core business logic | ⬜ Not started |
| 4 | Report / output generation | ⬜ Not started |
| 5 | Wizard for first-run setup | ⬜ Not started |
| 6 | Mode registry and second provider | ⬜ Not started |

---

## Known Limitations and Deferred Items

<!-- Things intentionally left out of scope, with the reason. -->
