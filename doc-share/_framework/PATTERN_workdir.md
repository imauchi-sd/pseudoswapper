# Pattern: Working Directory State Machine

## Problem it solves
Users work with files that live in a specific folder (e.g. monthly export dumps). Without a working directory, they must type full paths on every command. With one set, bare filenames resolve automatically.

## Shape

```
workdir.py
├── save_work_dir(workspace, path)   # persist to state file
├── load_work_dir(workspace)         # read back, returns None if unset
├── clear_work_dir(workspace)        # delete state file
├── resolve_path(p, work_dir)        # join if relative, pass through if absolute
└── pick_file(work_dir, exts, label) # interactive numbered file picker
```

### State file
State is stored in a hidden YAML file (`.arhelper`, `.toolstate`, etc.) **next to `workspace.yaml`**, not in the user's home dir or a global location. This keeps it scoped to one installation of the tool.

```python
_STATE_FILENAME = ".arhelper"

def _state_path(workspace: Path) -> Path:
    return Path(workspace).resolve().parent / _STATE_FILENAME
```

Add the state file to `.gitignore`.

### State file format (minimal)
```yaml
work_dir: /Users/name/monthly-exports/2025-Q1
```

## Key decisions from access-review

### resolve_path is a no-op for absolute paths
If the user passes an absolute path, it is returned unchanged. If they pass a bare filename and a work dir is set, the filename is joined to the work dir. If no work dir is set, the filename is returned as-is (resolves from CWD).

```python
def resolve_path(p, work_dir):
    if p is None or work_dir is None or p.is_absolute():
        return p
    return work_dir / p
```

### pick_file falls back gracefully
If no matching files exist in the work dir, the user is prompted to type a full path rather than being shown an empty numbered list.

### Commands expose set/show/clear as explicit subcommands
Users manage the work dir through named commands (`set-work-dir`, `show-work-dir`, `clear-work-dir`) rather than a config file they edit by hand. This makes the state discoverable and reversible.

## What to adapt per project
- State filename (`.arhelper` → something project-specific)
- What other state keys live in the same file (e.g. last-used mode, last run timestamp)

## What to keep as-is
- State file next to `workspace.yaml`, not global
- `resolve_path` logic (absolute passthrough, relative join, None passthrough)
- `pick_file` with numbered list + plain-path fallback
- `set / show / clear` as named CLI subcommands
