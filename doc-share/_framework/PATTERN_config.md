# Pattern: Two-Level YAML Configuration

## Problem it solves
A tool that operates on multiple named items (apps, targets, integrations) needs both org-wide settings and per-item settings, without mixing them. Keeping them separate lets each level be validated independently and lets items be added without touching global config.

## Shape

```
workspace.yaml              # org-level config (one per installation, not committed)
workspace.yaml.example      # committed template with all fields documented
apps/
├── _template.yaml          # committed template for per-item configs
└── <item-name>.yaml        # one file per item, added by the user
```

### Loading chain
```
config.py
├── load_workspace(path)           # reads + validates workspace.yaml
├── load_app_config(name, dir)     # reads + validates apps/<name>.yaml
├── list_app_configs(dir)          # returns all item names (excludes _template)
└── set_<field>(workspace, value)  # targeted in-place update, preserves comments
```

## Key decisions from access-review

### Required vs optional fields validated at load time
`load_workspace` and `load_app_config` raise a typed `ConfigError` (not a generic exception) for any missing or null required field. Optional fields are filled with defaults via `setdefault()` after validation. Commands catch `ConfigError` and print a clear message — users see what field is missing, not a stack trace.

```python
class ConfigError(Exception): ...

def _require(data, key_path):
    # dot-separated path, e.g. "company.domains"
    # raises ConfigError if absent or None
```

### Mode-conditional required fields
Some fields are only required for certain modes. Validate them only when the active mode requires them:

```python
if sot_mode == "bamboohr_jumpcloud":
    for field in ["jumpcloud.email_header", ...]:
        _require(data, field)
```

### In-place YAML updates preserve comments
When the tool needs to write back a single field (e.g. `set_sot_mode`), use regex replacement on the raw text rather than `yaml.dump()`. `yaml.dump()` strips comments and reorders keys.

```python
def set_sot_mode(workspace_path, mode):
    text = workspace_path.read_text()
    if re.search(r"^sot_mode:.*$", text, re.MULTILINE):
        text = re.sub(r"^sot_mode:.*$", f"sot_mode: {mode}", text, re.MULTILINE)
    else:
        # insert near top, before first non-comment line
        ...
    workspace_path.write_text(text)
```

### `workspace.yaml` is gitignored; `.example` is committed
The actual config contains org-specific data (domain names, field names from real exports). Commit only the template with placeholder values and inline comments describing each field.

### Per-item configs live in `apps/` (or equivalent)
Each item gets its own YAML. The directory is discovered at runtime from the workspace location (`Path(workspace).parent / "apps"`), so no path needs to be hardcoded. `_template.yaml` is excluded from `list_app_configs()` by name.

## What to adapt per project
- Field names and required fields for your domain
- Directory name (`apps/` → `targets/`, `integrations/`, etc.)
- Which fields are mode-conditional

## What to keep as-is
- `ConfigError` as a typed exception
- `_require(data, dot.path)` helper
- `setdefault()` for optional fields after required-field validation
- In-place regex update for targeted writes
- `.example` file committed; actual config gitignored
- `_template.yaml` for per-item configs, excluded from discovery
