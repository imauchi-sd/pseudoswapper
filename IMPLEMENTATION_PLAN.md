# Implementation Plan — pseudoswapper

Tracker for the phased build of the local data redaction CLI tool.
Reference documents: `CLAUDE.md` (spec), `DESIGN.md` (decisions), `doc-share/_framework/` (patterns).

---

## Project Structure

```
pseudoswapper/
├── pyproject.toml
├── pseudoswapper_config.example.yaml
├── .gitignore                          # includes .pseudoswapper_session
├── src/
│   └── pseudoswapper/
│       ├── __init__.py
│       ├── cli.py                      # Typer entry point — thin layer only
│       ├── config.py                   # YAML loader, ConfigError, _require helper
│       ├── session.py                  # Temp dir lifecycle, .pseudoswapper_session pointer
│       ├── entity_registry.py          # In-memory token store, serialisation
│       ├── detector.py                 # Presidio AnalyzerEngine wrapper
│       ├── recognizers.py              # CompanyTermsRecognizer, EmployeeRecognizer
│       ├── tokenizer.py                # DetectedEntity → token, person entity model
│       ├── replacer.py                 # Longest-match-first text replacement
│       ├── restore.py                  # Token reversal with fuzzy/case-insensitive match
│       └── modes/
│           ├── __init__.py
│           ├── document.py             # Document mode orchestrator
│           └── structured.py          # Structured mode (CSV / JSON / XLSX)
└── tests/
    ├── __init__.py
    ├── conftest.py                     # Shared config builders, tmp_path helpers
    ├── fixtures/
    │   ├── sample_document.txt         # Fake-but-realistic prose with PII
    │   ├── sample_structured.csv
    │   ├── sample_structured.json
    │   └── sample_structured.xlsx
    ├── test_config.py
    ├── test_entity_registry.py
    ├── test_session.py
    ├── test_detector.py
    ├── test_tokenizer.py
    ├── test_replacer.py
    ├── test_restore.py
    ├── test_document.py
    └── test_structured.py
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `cli.py` | Command definitions only. Loads config, finds/creates session, resolves paths, calls domain functions, echoes output path. No logic. |
| `config.py` | Loads and validates `~/.pseudoswapper_config.yaml`. Raises `ConfigError` on missing required fields. Provides `_require(data, dot.path)` helper. |
| `session.py` | Creates temp dir via `tempfile.mkdtemp()` (mode 0700). Writes `session.json` there. Writes `.pseudoswapper_session` pointer in CWD. Cleans up on restore. |
| `entity_registry.py` | In-memory dict of value → token. Per-type counters. `to_dict()` / `from_dict()` for session serialisation. Reverse map for restore. |
| `detector.py` | Wraps Presidio `AnalyzerEngine`. Initialises with standard recognizers + custom ones from config. `analyze(text)` returns `list[DetectedEntity]` with type, original text, and character offsets. |
| `recognizers.py` | Two `PatternRecognizer` subclasses built from YAML: `CompanyTermsRecognizer` (exact-match on `company_terms`) and `EmployeeRecognizer` (exact-match on employee names and usernames). |
| `tokenizer.py` | Takes `list[DetectedEntity]` + raw text → `dict[original_text → token]`. Owns the person entity model: on first encounter of a full name, registers first/last surface forms too. Owns correlated email logic for structured mode. |
| `replacer.py` | Takes text + token map → redacted text. Sorts replacements longest-first so full names are caught before their parts. |
| `restore.py` | Finds all `[TOKEN_N]` patterns in text via regex. Looks up each in the entity registry's reverse map. Case-insensitive matching to tolerate AI reformatting. |
| `modes/document.py` | Orchestrates document mode: read file → pre-register YAML employees → detect → tokenize → replace → write `.redacted` output → save session. |
| `modes/structured.py` | Orchestrates structured mode: reads CSV/JSON/XLSX → determines anchor field → processes row by row → writes `.redacted` output → saves session. |

---

## Token Format

| Detected type | Token | Notes |
|---|---|---|
| Full name | `[PERSON_1]` | Canonical form |
| First name alone | `[PERSON_1_FIRST]` | Surface form of same entity |
| Last name alone | `[PERSON_1_LAST]` | Surface form of same entity |
| Email (document mode) | `[EMAIL_1]` | Independent, no person linkage |
| Email (structured, correlated) | `[EMAIL_PERSON_1]` | Signals linkage to PERSON_1 |
| Phone | `[PHONE_1]` | |
| IP address | `[IP_1]` | |
| Domain | `[DOMAIN_1]` | |
| URL | `[URL_1]` | |
| Organisation (NLP) | `[ORG_1]` | |
| Location (NLP) | `[LOC_1]` | |
| YAML company term | `[COMPANY_1]` | Highest-priority recognizer |

---

## Data Flows

### Document mode
```
read file
  → pre-register YAML employees into EntityRegistry
  → Detector.analyze(text)              # Presidio → list[DetectedEntity]
  → Tokenizer.assign(entities, text)    # → dict{original → [TOKEN_N]}
  → Replacer.replace(text, token_map)   # longest-match-first
  → write file.redacted.txt
  → Session.save()                      # EntityRegistry → temp JSON
  → write .pseudoswapper_session
```

### Structured mode
```
read file (CSV/JSON/XLSX) → DataFrame/list[dict]
  → pre-register YAML employees
  → determine anchor field (CLI arg → YAML config → auto-detect)
  → for each row:
      anchor_value = row[anchor_field]
      if anchor_value in registry:
          entity = registry.lookup(anchor_value)
      else:
          entity = register new PERSON entity for anchor_value
          register correlated fields (email → EMAIL_PERSON_N, etc.)
      replace all field values in row with tokens
  → write file.redacted.csv (or .json / .xlsx)
  → Session.save()
  → write .pseudoswapper_session
```

### Restore
```
load .pseudoswapper_session → temp session path
  → Session.load() → EntityRegistry (with reverse map)
  → find all [TOKEN_N] patterns in AI output text (regex)
  → for each token: fuzzy case-insensitive lookup in reverse map
  → replace tokens with originals
  → write file.restored.txt
  → delete session + .pseudoswapper_session
```

---

## Implementation Phases

### Phase 1 — Scaffold `[ ]`

**Deliverables**
- `pyproject.toml` — package metadata, dependencies, `[project.scripts]` entry point, `[dev]` extras
- `src/pseudoswapper/__init__.py` — version string only
- `src/pseudoswapper/cli.py` — all commands defined with correct signatures, bodies raise `NotImplementedError`
- `src/pseudoswapper/config.py` — `ConfigError`, `_require(data, dot.path)`, `load_config()`, `default_config()`
- `pseudoswapper_config.example.yaml` — fully documented template (all fields, inline comments)
- `.gitignore` — includes `.pseudoswapper_session`, `*.pyc`, `__pycache__`, `.venv`
- `tests/conftest.py` — `make_config()` builder returning minimal valid config dict
- `tests/test_config.py` — config loading and `ConfigError` on missing required fields

**Tests**
- `load_config()` returns expected dict for valid YAML
- `ConfigError` raised when required fields are absent
- `default_config()` returns a valid config (no error when loaded)

---

### Phase 2 — Entity registry + session `[ ]`

**Deliverables**
- `src/pseudoswapper/entity_registry.py`
  - Per-type counters (`PERSON`, `EMAIL`, `PHONE`, etc.)
  - `register(value, entity_type)` → token string
  - `lookup(value)` → token or `None`
  - `reverse_lookup(token)` → original value or `None`
  - `to_dict()` / `from_dict()` for serialisation
- `src/pseudoswapper/session.py`
  - `create_session(registry, cwd)` — mkdtemp(mode=0700), write `session.json`, write `.pseudoswapper_session`
  - `load_session(cwd)` → `EntityRegistry`
  - `clear_session(cwd)` — deletes temp dir + pointer file
  - `session_exists(cwd)` → bool
- `tests/test_entity_registry.py`
- `tests/test_session.py`

**Tests**
- Same input value always returns the same token within a session
- Counters increment correctly per entity type
- Round-trip: `to_dict()` → `from_dict()` preserves all mappings
- `create_session` → `load_session` round-trip produces equivalent registry
- `clear_session` removes both temp dir and pointer file
- `session_exists` returns `False` after clear

---

### Phase 3 — Detection layer `[ ]`

**Deliverables**
- `src/pseudoswapper/recognizers.py`
  - `CompanyTermsRecognizer` — Presidio `PatternRecognizer` for `company_terms` list (exact-match, highest priority)
  - `EmployeeRecognizer` — Presidio `PatternRecognizer` for employee full names and usernames from config
- `src/pseudoswapper/detector.py`
  - `Detector(config)` — initialises Presidio `AnalyzerEngine` with standard recognizers + custom ones
  - `analyze(text)` → `list[DetectedEntity]` (type, span, original text)
- `tests/fixtures/sample_document.txt` — fake-but-realistic prose with emails, phone, IP, names, company terms
- `tests/test_detector.py`

**Tests**
- Email addresses detected
- Phone numbers detected
- IP addresses detected
- Person names detected (via Presidio/spaCy)
- Company terms from config detected
- Employee names from config detected
- Overlapping spans handled (no double-detection)

---

### Phase 4 — Tokenizer + replacer `[ ]`

**Deliverables**
- `src/pseudoswapper/tokenizer.py`
  - `Tokenizer(registry)` — takes `EntityRegistry` as dependency
  - `assign(entities, text)` → `dict[str, str]` (original → token)
  - Person entity model: on first full-name encounter, registers `[PERSON_N]`, `[PERSON_N_FIRST]`, `[PERSON_N_LAST]`
  - Correlated email logic for structured mode: `assign_correlated(email, person_token_n)`
- `src/pseudoswapper/replacer.py`
  - `replace(text, token_map)` → redacted text
  - Sorts replacements by length descending before applying (longest-match-first)
  - Escapes regex special characters in keys
- `tests/test_tokenizer.py`
- `tests/test_replacer.py`

**Tests (tokenizer)**
- Full name registers all three surface forms
- Same full name on second call returns same token (no new counter increment)
- First name alone (without prior full name) registers as independent `[PERSON_N]`
- Entity type routing: email → `[EMAIL_N]`, phone → `[PHONE_N]`, etc.

**Tests (replacer)**
- Full name replaced before first name when both appear in text
- All occurrences of a value are replaced (not just first)
- Values with regex special characters replaced correctly
- Original text unchanged when token map is empty

---

### Phase 5 — Document mode + restore `[ ]`

**Deliverables**
- `src/pseudoswapper/modes/document.py` — full orchestration (see data flow above)
- `src/pseudoswapper/restore.py`
  - `restore(text, registry)` → restored text
  - Regex to find all `[TOKEN_N]` and `[TOKEN_N_SUFFIX]` patterns
  - Case-insensitive reverse lookup
- Wire `document` and `restore` commands in `cli.py` (replace `NotImplementedError`)
- `tests/test_document.py`
- `tests/test_restore.py`

**Tests (document mode)**
- Output file written with `.redacted` suffix alongside input
- All PII in sample fixture replaced with tokens
- YAML employee list pre-registered (token consistent even if NER misses the name)
- Session file created after redact

**Tests (restore)**
- All tokens replaced with originals
- Case-variant tokens restored (`[person_1]`, `[PERSON_1]` both match)
- Tokens wrapped in markdown (`` `[PERSON_1]` ``) restored correctly
- Session deleted after successful restore
- Session preserved after failed restore

**Integration (round-trip)**
- `document(sample_document.txt)` → `restore(output)` → matches all original PII values

---

### Phase 6 — Structured mode `[ ]`

**Deliverables**
- `src/pseudoswapper/modes/structured.py`
  - CSV, JSON, XLSX ingestion (via pandas + openpyxl)
  - Anchor field resolution: CLI arg → YAML config → auto-detect from common column name patterns
  - Row-by-row processing with global entity registry (same anchor value → same token across all rows)
  - Correlated field registration via `Tokenizer.assign_correlated()`
  - Output: `.redacted.csv` / `.redacted.json` / `.redacted.xlsx`
- Wire `structured` command in `cli.py`
- `tests/fixtures/sample_structured.csv` — fake employee data with anchor field + correlated fields
- `tests/fixtures/sample_structured.json`
- `tests/fixtures/sample_structured.xlsx`
- `tests/test_structured.py`

**Tests**
- Anchor field resolved from CLI arg, YAML config, and auto-detect (in priority order)
- Same anchor value in multiple rows produces same person token across all rows
- Correlated email registered as `[EMAIL_PERSON_N]`
- Null anchor value: fields in that row tokenised independently (no crash)
- CSV, JSON, and XLSX all produce equivalent output structure
- Round-trip: structured redact → restore → original values recovered

---

### Phase 7 — Final polish `[ ]`

**Deliverables**
- `USER_GUIDE.md` — covers: what the tool does, choosing a mode, YAML config setup, anchor field selection, running the tool, restoring AI output, known limitations, security notes (see `DESIGN.md` outline)
- `pseudoswapper config --show` and `pseudoswapper config --edit` commands wired in `cli.py`
- `pseudoswapper clear-session` command wired in `cli.py`
- Error messages reviewed: all `ConfigError`, missing session, and bad file paths produce clear user-facing messages (no stack traces)
- `README.md` — one-page install + quickstart

---

## Key Design Constraints (do not revisit)

- **CLI framework:** Typer (not Click). Commands are thin — no logic in `cli.py`.
- **Detection:** Presidio `AnalyzerEngine` (wraps spaCy `en_core_web_lg`). Not direct spaCy.
- **Session:** `tempfile.mkdtemp()` mode 0700. Pointer file in CWD. Never persisted to user-visible location.
- **Config:** YAML file at `~/.pseudoswapper_config.yaml`. Definitions only, never mappings.
- **Replacement order:** Always longest-match-first to prevent partial collisions.
- **Restore tolerance:** Case-insensitive regex; AI markdown wrapping must be handled.
- **Testing:** Real fixture files, no mocking of file I/O. `python3 -m pytest`. Inline config dicts.
- **Install:** `pip install -e ".[dev]"` — CLI available as real shell command via `pyproject.toml` entry point.
