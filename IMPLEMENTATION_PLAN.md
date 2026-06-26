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
│       ├── config.py                   # YAML loader, ConfigError, _require helper; redact_profiles
│       ├── session.py                  # Temp dir lifecycle, .pseudoswapper_session pointer
│       ├── entity_registry.py          # In-memory token store, serialisation
│       ├── detector.py                 # Presidio AnalyzerEngine wrapper; redact_mode flag
│       ├── recognizers.py              # CompanyTermsRecognizer, EmployeeRecognizer, AmountRecognizer
│       ├── tokenizer.py                # DetectedEntity → token, person entity model; strict_protection
│       ├── replacer.py                 # Longest-match-first text replacement
│       ├── restore.py                  # Token reversal with fuzzy/case-insensitive match
│       ├── modes/
│       │   ├── __init__.py
│       │   ├── document.py             # Document mode orchestrator; EML/MSG dispatch; shared pipeline
│       │   ├── structured.py          # Structured mode (CSV / JSON / XLSX); multi-sheet XLSX
│       │   └── redact.py              # One-time redact: redact_file, redact_batch
│       └── extractors/
│           ├── __init__.py
│           ├── docx.py                # python-docx paragraph extractor + token writer
│           ├── pdf.py                 # pdfplumber text extractor; UnsupportedFileError
│           ├── eml.py                 # RFC 2822 EML extractor (stdlib email module)
│           └── msg.py                 # Outlook MSG extractor (extract-msg)
└── tests/
    ├── __init__.py
    ├── conftest.py                     # Shared config builders, tmp_path helpers
    ├── fixtures/
    │   ├── sample_document.txt         # Fake-but-realistic prose with PII
    │   ├── sample_document.docx        # Same content as .txt; "Doe" in split run for run-split test
    │   ├── sample_document.pdf         # Same content as .txt; generated via reportlab
    │   ├── sample_structured.csv
    │   ├── sample_structured.json
    │   ├── sample_structured.xlsx
    │   ├── sample_email.eml            # RFC 2822 fixture with PII in headers and body
    │   └── sample_email.msg            # Outlook MSG fixture generated via OleWriter
    ├── test_config.py
    ├── test_entity_registry.py
    ├── test_session.py
    ├── test_detector.py
    ├── test_tokenizer.py
    ├── test_replacer.py
    ├── test_restore.py
    ├── test_document.py
    ├── test_structured.py
    ├── test_docx.py                    # 11 tests for .docx document mode support
    ├── test_pdf.py                     # 11 tests for .pdf document mode support
    ├── test_redact.py                  # redact command + batch mode tests
    ├── test_eml.py                     # EML extractor and redact dispatch tests
    └── test_msg.py                     # MSG extractor and redact dispatch tests
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
| `modes/document.py` | Orchestrates document mode: dispatches on file suffix (`.docx`, `.pdf`, `.eml`, `.msg`, plain text) → pre-register YAML employees → detect → tokenize → replace → write `.redacted` output → save session. Accepts optional `_registry`/`_tokenizer` for shared-pipeline batch use. |
| `modes/structured.py` | Orchestrates structured mode: reads CSV/JSON (single-sheet) or all XLSX sheets via `_read_xlsx_sheets`/`_write_xlsx_sheets` → determines anchor field → processes row by row → writes `.redacted` output → saves session. Accepts optional `_registry`/`_tokenizer`. |
| `modes/redact.py` | One-time permanent redaction: `redact_file(file, config)` dispatches to structured or document pipeline with `write_session=False`, `strict_protection=False`, `redact_mode=True`. `redact_batch(directory, config, recursive)` discovers supported files, builds one shared `EntityRegistry` + `Tokenizer`, processes each file, collects per-file results. |
| `extractors/docx.py` | `extract_text(path)` — concatenates all paragraph runs for PII detection. `apply_token_map(src, token_map, out)` — paragraph-level replacement written to a new `.docx` file. |
| `extractors/pdf.py` | `extract_text(path) -> str` — extracts text page-by-page via pdfplumber, joins with `\n\n`. Raises `UnsupportedFileError` for image-only PDFs with no extractable text. |
| `extractors/eml.py` | `extract_text(path) -> str` — parses RFC 2822 with stdlib `email` module; extracts From/To/Cc/Subject header block + prefers `text/plain` body, falls back to HTML-stripped `text/html`. Raises `UnsupportedEmailError` if no readable content. |
| `extractors/msg.py` | `extract_text(path) -> str` — opens Outlook MSG with `extract_msg`; extracts sender, recipients, subject, body. Same output format as EML extractor. Raises `UnsupportedEmailError` if no readable content. |

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
| Financial figure (redact mode) | `[AMOUNT_1]` | spaCy MONEY NER; full token only (no partial masking) |
| EU bank account (redact mode) | `[IBAN_CODE_1]` | Presidio IbanRecognizer |
| MAC address (redact mode) | `[MAC_ADDRESS_1]` | Presidio MacAddressRecognizer |

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

### Phase 1 — Scaffold `[x]`

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
- `load_config()` returns expected dict for valid YAML — PASS
- `ConfigError` raised when required fields are absent — PASS
- `default_config()` returns a valid config (no error when loaded) — PASS
- 12 tests total, all passing

**Implementation notes**
- `pyproject.toml` build backend corrected from `setuptools.backends.legacy:build` to `setuptools.build_meta` (the former requires setuptools 68+ with a newer calling convention that pip 26 on the system couldn't resolve)
- `requires-python` relaxed from `>=3.11` to `>=3.9` to match the system Python
- Heavy dependencies (`spacy`, `presidio-analyzer`, `presidio-anonymizer`, `pandas`, `openpyxl`) are declared in `pyproject.toml` but were not installed for Phase 1 — they are not needed until Phase 3+. Only `typer`, `pyyaml`, and `pytest` were installed.
- Python environment subsequently resolved: Python 3.12 installed via Homebrew, project `.venv` created at `.venv/` using `python3.12 -m venv .venv`. All future `pip install` commands run inside this venv.

---

### Phase 2 — Entity registry + session `[x]`

**Deliverables**
- `src/pseudoswapper/entity_registry.py`
  - Per-type counters (`PERSON`, `EMAIL`, `PHONE`, etc.)
  - `register(value, entity_type)` → token string
  - `lookup(value)` → token or `None`
  - `reverse_lookup(token)` → original value or `None`
  - `register_alias(alias, token)` — maps surface forms (first/last name) to an existing token without incrementing the counter
  - `to_dict()` / `from_dict()` for serialisation
- `src/pseudoswapper/session.py`
  - `create_session(registry, cwd)` — mkdtemp(mode=0700), write `session.json`, write `.pseudoswapper_session`
  - `load_session(cwd)` → `EntityRegistry`
  - `save_session(registry, cwd)` — overwrites session.json in the existing temp dir (used after redact updates the registry mid-session)
  - `clear_session(cwd)` — deletes temp dir + pointer file
  - `session_exists(cwd)` → bool
- `tests/test_entity_registry.py`
- `tests/test_session.py`

**Tests**
- Same input value always returns the same token within a session
- Counters increment correctly per entity type
- Counters are independent across entity types
- Round-trip: `to_dict()` → `from_dict()` preserves all mappings and counter state
- `create_session` → `load_session` round-trip produces equivalent registry
- Temp dir created with mode 0700 (no group/other read permissions)
- `save_session` updates an existing session without creating a new one
- `clear_session` removes both temp dir and pointer file
- `session_exists` returns `False` after clear
- `clear_session` is a no-op when no session exists (no error raised)
- `load_session` raises `FileNotFoundError` with a descriptive message when no pointer or temp dir
- 22 tests total, all passing

**Implementation notes**
- `register_alias` was added beyond the original spec to support the person entity model (Phase 4). The tokenizer calls `register_alias("John", "[PERSON_1_FIRST]")` and `register_alias("Doe", "[PERSON_1_LAST]")` after registering a full name — the surface-form token strings are distinct from the canonical token, but no counter is consumed for them.
- `save_session` was added (also beyond original spec) to support the case where a redact command needs to update the registry after creation (e.g. structured mode processes rows incrementally).

---

### Phase 3 — Detection layer `[x]`

> **Python environment:** resolved. Python 3.12 installed via Homebrew (`/opt/homebrew/bin/python3.12`). Project `.venv` created with 3.12 and activated. `pip install -e ".[dev]"` installs spaCy and Presidio. `en_core_web_lg` downloaded separately via `python -m spacy download en_core_web_lg`.

**Deliverables**
- `src/pseudoswapper/recognizers.py`
  - `CompanyTermsRecognizer` — Presidio `PatternRecognizer` for `company_terms` list (exact-match, score 0.99)
  - `EmployeeRecognizer` — Presidio `PatternRecognizer` for employee full names and usernames (score 0.95)
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
- Excluded terms skipped
- Detected entity span text matches character offsets in original
- 10 tests total, all passing

**Implementation notes**
- Both recognizers override `analyze()` with `re.compile(re.escape(term), re.IGNORECASE)` rather than relying on Presidio's built-in deny-list logic, which was unreliable for exact-match use.
- Overlap deduplication: results sorted by `(score, span_length)` descending; first result to claim a character position wins. This ensures high-confidence custom recognizers beat lower-confidence NLP results.
- Presidio entity type names are mapped to internal token-type names in `_ENTITY_TYPE_MAP` (e.g. `EMAIL_ADDRESS` → `EMAIL`, `ORGANIZATION` → `ORG`).
- `exclude_terms` are stored lowercase in a set and checked against `span_text.lower()` after deduplication.

---

### Phase 4 — Tokenizer + replacer `[x]`

**Deliverables**
- `src/pseudoswapper/tokenizer.py`
  - `Tokenizer(registry)` — takes `EntityRegistry` as dependency
  - `assign(entities)` → `dict[str, str]` (original → token)
  - Person entity model: on first full-name encounter, registers `[PERSON_N]`, `[PERSON_N_FIRST]`, `[PERSON_N_LAST]`
  - Correlated email logic for structured mode: `assign_correlated(email, person_n)`
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
- `assign_correlated` registers email as `[EMAIL_PERSON_N]`
- 12 tests total, all passing

**Tests (replacer)**
- Full name replaced before first name when both appear in text
- All occurrences of a value are replaced (not just first)
- Values with regex special characters replaced correctly (dots, parens, `+`)
- Original text unchanged when token map is empty
- 9 tests total, all passing

**Implementation notes**
- Surface-form tokens (`[PERSON_N_FIRST]`, `[PERSON_N_LAST]`) are derived from the canonical token using `base = token[:-1]` (strips trailing `]`), then `f"{base}_FIRST]"`. This avoids parsing the counter number.
- Surface forms are only registered if the name string is not already in the registry. This handles cases where "John" was seen independently before "John Doe" appeared.
- `replacer.replace()` builds a single compiled regex from all keys, so replacement is a single pass — no risk of a token being re-matched as a value.
- `assign_correlated` uses `register_alias` rather than `register`, so no counter is consumed for correlated emails.

---

### Phase 5 — Document mode + restore `[x]`

**Deliverables**
- `src/pseudoswapper/modes/document.py` — full orchestration (see data flow above)
- `src/pseudoswapper/restore.py`
  - `restore(text, registry)` → restored text
  - Regex to find all `[TOKEN_N]` and `[TOKEN_N_SUFFIX]` patterns
  - Case-insensitive reverse lookup
- Wire `document`, `restore`, and `clear-session` commands in `cli.py` (replace `NotImplementedError`)
- `tests/test_document.py`
- `tests/test_restore.py`

**Tests (document mode)**
- Output file written with `.redacted` suffix alongside input, in same directory as input
- YAML company terms replaced with `[COMPANY_N]` tokens
- YAML employee full names replaced with `[PERSON_N]` tokens
- YAML employee usernames replaced (pre-registered as alias to same person token)
- Email addresses replaced with `[EMAIL_N]` tokens
- Session created after redact
- Same person token emitted for all occurrences of a name
- Two distinct employees get distinct person tokens
- Session registry contains all detected values after redact
- Full sample fixture produces no known PII in output
- 11 tests total, all passing

**Tests (restore)**
- All tokens replaced with originals
- Unknown tokens left in place (not crashed)
- Case-variant tokens restored (`[person_1]`, `[PERSON_1]`, `[Person_1]` all match)
- Tokens wrapped in backticks and bold markdown restored correctly
- Multiple occurrences of same token all restored
- Surface-form tokens (`[PERSON_N_FIRST]`, `[PERSON_N_LAST]`) restored correctly
- Output file written with `.restored` suffix
- Session deleted after successful restore
- Session preserved when no session exists (raises `FileNotFoundError`)
- 12 tests total, all passing

**Integration (round-trip)**
- `redact_document()` → `restore_file()` → original PII values present in restored text — PASS

**Implementation notes**
- Employee pre-registration calls `tokenizer._assign_person(full_name)` to get the canonical token, then calls `registry.register_alias(username, token)` to link the username to the same entity.
- `document.py` calls `save_session` if a session already exists (idempotent re-run), `create_session` otherwise.
- `restore()` builds a `{token.upper(): original}` dict from the registry's reverse map before the regex sub, so a single dict lookup handles all case variants from AI output.
- Token pattern: `\[[^\[\]\s]+\]` with `IGNORECASE` — matches any bracket content without spaces or nested brackets, tolerating AI markdown reformatting.
- `clear-session` command wired in Phase 5 (moved forward from Phase 7 deliverables). `config --show` and `config --edit` were already wired in Phase 1.

---

### Phase 6 — Structured mode `[x]`

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

### Phase 7 — Final polish `[x]`

**Deliverables**
- `USER_GUIDE.md` — 8 sections: what the tool does, mode selection, YAML config setup, anchor field selection (with good/bad anchor table), running the tool, restoring AI output (session lifecycle, token tolerance, clear-session), known limitations (L1–L9), security notes
- ~~`pseudoswapper config --show` and `pseudoswapper config --edit` commands wired in `cli.py`~~ — done in Phase 1
- ~~`pseudoswapper clear-session` command wired in `cli.py`~~ — done in Phase 5
- Error messages reviewed — all `ConfigError`, missing session, and bad file paths produce clean user-facing messages with no stack traces (verified in cli.py)
- `README.md` — updated: accurate install steps, quick start covering all commands, configuration summary, session lifecycle table, known limitations, pointer to USER_GUIDE.md, development section with test count

**Implementation notes**
- USER_GUIDE.md includes a documented design note (L5) explaining that opaque-ID anchors (`employee_id = "E001"`) restore `[PERSON_1]` to the ID value, not the full name — and the mitigation (use `full_name` as anchor when human-readable restoration is required). This was discovered during Phase 6 round-trip testing.
- Error handling in `cli.py` uses a consistent pattern: `ConfigError` is caught at config load; all other exceptions from domain functions are caught generically and emitted on stderr with `err=True`. No raw tracebacks reach the user in normal operation.

---

### Stage 1 — DOCX support `[x]`

**New dependency:** `python-docx >= 1.1` (added to `pyproject.toml`)

**Deliverables**
- `src/pseudoswapper/extractors/__init__.py` — package marker
- `src/pseudoswapper/extractors/docx.py`
  - `extract_text(path) -> str` — opens `.docx` with python-docx, concatenates all run texts per paragraph (body + table cells + headers + footers), joins paragraphs with `\n`; used as the detection input
  - `apply_token_map(src, token_map, out)` — opens the original `.docx`, applies longest-match-first token replacement at the paragraph level (clears all runs, writes a single new run per modified paragraph), saves to `out`
- `src/pseudoswapper/modes/document.py` — refactored: `redact_document()` now dispatches on file suffix; `.docx` calls `_redact_docx()`; plain text calls `_redact_plain()`; `_output_path()` accepts optional `force_suffix` argument (unused by docx but scaffolds Stage 2 PDF)
- `tests/fixtures/sample_document.docx` — mirrors `sample_document.txt`; paragraph 3 ("John Doe joined the call...") has "Doe" in a separate bold run to exercise the run-split case
- `tests/test_docx.py` — 11 tests

**The run-split problem:** `.docx` stores text in `<w:r>` XML run elements. A name like "John Doe" can span two runs if formatting changes mid-name. Run-by-run replacement misses cross-run names. Solution: concatenate all runs per paragraph for detection, then apply replacement to the whole paragraph string and write back as a single run. This loses intra-paragraph run-level formatting in replaced paragraphs (documented limitation).

**Tests**
- Output file is `.redacted.docx`, exists alongside input — PASS
- Output is a valid `.docx` file (parseable by python-docx) — PASS
- Output written alongside input — PASS
- Employee name replaced with `[PERSON_N]` token — PASS
- Company term replaced with `[COMPANY_N]` token — PASS
- Email replaced with `[EMAIL_N]` token — PASS
- Same token emitted for same name across multiple paragraphs — PASS
- Two distinct employees get distinct person tokens — PASS
- Run-split name ("John " + "Doe" in separate runs) detected and replaced — PASS
- Passthrough IP preserved while name is replaced — PASS
- Full fixture contains no known PII — PASS
- 11 tests, all passing. Existing 130 tests unaffected (141 total).

---

### Stage 2 — PDF support `[x]`

**New dependency:** `pdfplumber >= 0.10` (added to `pyproject.toml`). `pymupdf` (fitz) was evaluated and rejected: AGPL license is incompatible with distribution. `pdfplumber` (MIT) is sufficient.

**Deliverables**
- `src/pseudoswapper/extractors/pdf.py`
  - `extract_text(path) -> str` — opens PDF with pdfplumber, extracts text page by page, joins with `\n\n`
  - Raises `UnsupportedFileError` if all pages yield empty text (scanned/image-only PDF)
- `src/pseudoswapper/modes/document.py` — `_redact_pdf()` added; `redact_document()` dispatch extended with `.pdf` branch; output suffix forced to `.txt` via `_output_path(file, force_suffix=".txt")`
- `tests/fixtures/sample_document.pdf` — generated with `reportlab`; mirrors `sample_document.txt` content
- `tests/test_pdf.py` — 11 tests

**Output format decision:** PDF input always produces `.redacted.txt`. PDFs store drawing instructions, not a document model — writing back a redacted PDF with original layout would require rebuilding the entire document (prohibitive complexity with no layout benefit for AI consumption). Plain text output is the correct trade-off. `report.pdf` → `report.redacted.txt`.

**Tests**
- Output file is `report.redacted.txt` (suffix forced to `.txt`) — PASS
- Output is readable UTF-8 text — PASS
- Output written alongside input — PASS
- Employee name replaced with `[PERSON_N]` token — PASS
- Company term replaced with `[COMPANY_N]` token — PASS
- Email replaced with `[EMAIL_N]` token — PASS
- Same token emitted for same name across multiple pages — PASS
- Two distinct employees get distinct person tokens — PASS
- Passthrough IP preserved while name is replaced — PASS
- Image-only PDF raises `UnsupportedFileError` — PASS
- Full fixture contains no known PII — PASS
- 11 tests, all passing. Total suite: 152 tests, all passing.

---

---

## Phase 2 — Incident Response & One-Time Redaction

Reference decisions: DESIGN.md Decision 9–14.

Driven by real incident response workflow: post-AiTM analysis requiring multi-sheet Excel exposure
reports, email artifacts, and one-time permanent redaction for internal distribution.

---

### Stage A — `redact` command + multi-sheet XLSX `[x]`

**New dependency:** none

**Deliverables**

- `src/pseudoswapper/modes/redact.py` — new mode orchestrator
  - `redact_file(file, config, passthrough_types, profile)` — single entry point; dispatches on
    file suffix to document or structured pipeline; never writes a session
  - Shared `EntityRegistry` passed through the pipeline so output token/mask is consistent across
    the file
- `src/pseudoswapper/modes/structured.py` — multi-sheet XLSX support
  - `_read_xlsx_sheets(file)` → `dict[sheet_name, (rows, columns)]`
  - `_write_xlsx_sheets(sheets, out_path)` — `pd.ExcelWriter` writing all sheets back
  - `redact_structured` updated to call multi-sheet path for `.xlsx`/`.xls`; single-sheet path
    unchanged for CSV and JSON
- `src/pseudoswapper/config.py` — `redact_profiles` block loaded and validated
  - `get_redact_profile(config, name)` → `dict` or raises `ConfigError` if not found
- `src/pseudoswapper/cli.py`
  - New `redact` command with `--passthrough` (accepts any type including PERSON/EMAIL/COMPANY/ORG)
    and `--profile` flags
  - `_resolve_redact_passthrough(config, profile, cli_flags)` — merges profile passthrough with CLI
    flags, always strips CREDIT_CARD from result
- `pseudoswapper_config.example.yaml` — `redact_profiles` block added with commented example
- `tests/test_redact.py`
- `tests/test_structured.py` — extended with multi-sheet cases

**Token format additions**

| Type | Token |
|---|---|
| `AMOUNT` | `[AMOUNT_1]` |
| `IBAN_CODE` | `[IBAN_CODE_1]` |
| `MAC_ADDRESS` | `[MAC_ADDRESS_1]` |

**Tests**

- `redact` command produces output file with `.redacted` suffix, no session created
- CREDIT_CARD always masked even when listed in `--passthrough`
- PERSON passthroughed when `--passthrough PERSON` supplied — name appears as-is in output
- Named profile loaded from config; passthrough flags merged with profile (union)
- Unknown profile name raises `ConfigError` with helpful message
- Multi-sheet XLSX: all sheets present in output workbook
- Multi-sheet XLSX: same entity in two sheets receives the same mask (shared registry)
- Multi-sheet XLSX: sheets with no PII written back unchanged
- Sheet count in output matches sheet count in input
- Single-sheet CSV and JSON behaviour unchanged by multi-sheet refactor

---

### Stage B — New entity types (`AMOUNT`, `IBAN_CODE`, `MAC_ADDRESS`) `[x]`

**New dependency:** none (all three use already-loaded model or already-present Presidio
recognizers)

**Deliverables**

- `src/pseudoswapper/detector.py`
  - `_REDACT_EXTRA_ENTITIES` — separate list containing `MONEY` (spaCy), `IBAN_CODE`,
    `MAC_ADDRESS`; added to `_SUPPORTED_ENTITIES` only when `redact_mode=True` is passed to
    `_build_engine`
  - `_ENTITY_TYPE_MAP` extended: `"MONEY"` → `"AMOUNT"`, `"IBAN_CODE"` → `"IBAN_CODE"`,
    `"MAC_ADDRESS"` → `"MAC_ADDRESS"`
  - `Detector.__init__` gains optional `redact_mode: bool = False` parameter
- `src/pseudoswapper/tokenizer.py`
  - `REDACT_BYPASSABLE_TYPES` frozenset: `{"AMOUNT", "IBAN_CODE", "MAC_ADDRESS"}` — merged with
    existing bypassable set when in redact mode
- `tests/test_detector.py` — extended with redact_mode cases

**Tests**

- `$52,340` detected as `AMOUNT` in redact mode; not detected in standard mode
- `GB29NWBK60161331926819` detected as `IBAN_CODE`
- `00:1A:2B:3C:4D:5E` detected as `MAC_ADDRESS`
- AMOUNT token: `[AMOUNT_1]`; consistent token on repeated occurrence
- AMOUNT bypassable: `--passthrough AMOUNT` leaves figure as-is
- IBAN and MAC_ADDRESS bypassable independently

---

### Stage C — EML support `[x]`

**New dependency:** none (Python stdlib `email` module)

**Deliverables**

- `src/pseudoswapper/extractors/eml.py`
  - `extract_text(path) -> str` — parse RFC 2822 file; extract From, To, Cc, Subject as a header
    block; prefer `text/plain` body part; fall back to HTML-stripped `text/html`; join with `\n\n`
  - `UnsupportedEmailError` — raised when no body content is extractable
- `src/pseudoswapper/modes/document.py` — `.eml` branch added to `redact_document` dispatch;
  output forced to `.txt`
- `tests/fixtures/sample_email.eml` — realistic fake EML with From, To, Subject, plain-text body
  containing names, emails, and a financial figure
- `tests/test_eml.py`

**Tests**

- Names and emails in headers redacted
- Subject line redacted
- Body PII redacted
- Output is `.redacted.txt`
- Multipart EML (text/plain + text/html): plain part used, HTML part ignored
- HTML-only EML: HTML stripped, plain text extracted and redacted
- Empty body raises `UnsupportedEmailError`

---

### Stage D — MSG support `[x]`

**New dependency:** `extract-msg >= 0.48` (pure Python, MIT licensed; added to `pyproject.toml`)

**Deliverables**

- `src/pseudoswapper/extractors/msg.py`
  - `extract_text(path) -> str` — open MSG with `extract_msg.Message`; extract sender, recipients,
    subject, body; same header block format as EML extractor; prefer plain text body, fall back to
    HTML-stripped HTML body
- `src/pseudoswapper/modes/document.py` — `.msg` branch added to dispatch; output forced to `.txt`
- `tests/fixtures/sample_email.msg` — generated programmatically or via extract-msg test helpers
- `tests/test_msg.py`

**Tests**

- Mirrors EML test suite: headers redacted, subject redacted, body PII redacted, output `.txt`
- MSG with HTML body: HTML stripped, content redacted
- MSG with no readable body: `UnsupportedEmailError` raised

---

### Stage E — Batch mode `[x]`

**New dependency:** none

**Deliverables**

- `src/pseudoswapper/modes/document.py` — `_build_pipeline` gains `_registry` / `_tokenizer`
  parameters; all `_redact_*` functions thread them through; `redact_document` exposes them
- `src/pseudoswapper/modes/structured.py` — `redact_structured` gains `_registry` / `_tokenizer`
  parameters; when provided, skips `EntityRegistry` / `Tokenizer` construction and employee
  pre-registration (already done at batch start)
- `src/pseudoswapper/modes/redact.py`
  - `redact_file` gains `_registry` / `_tokenizer` parameters; passes them to `redact_structured`
    and `redact_document`
  - `SUPPORTED_BATCH_EXTENSIONS` — frozenset of extensions eligible for batch discovery
  - `redact_batch(directory, config, passthrough_types, recursive, on_file)` — builds one shared
    `EntityRegistry` + `Tokenizer`, calls `_pre_register_employees` once, loops over discovered
    files calling `redact_file` with the shared pipeline, collects per-file results, returns
    `{processed, succeeded, failed, results}` summary; per-file errors do not abort the batch
- `src/pseudoswapper/cli.py` — `redact_cmd` argument renamed from `file` to `target`;
  `--recursive/-r` flag added; command branches: directory → `redact_batch` with `on_file`
  callback printing per-file tick/cross lines and a summary; file → existing single-file path
- `tests/test_redact.py` — 8 new batch tests added (all supported files processed; same entity
  same mask across files; `.redacted` files skipped; unsupported extensions skipped; one-error-
  does-not-abort; recursive subdirectory; empty directory; `on_file` callback)

**Tests**

- Directory with all supported files: all produce `.redacted` outputs — PASS
- Same entity across two `.txt` files produces the same mask (shared registry) — PASS
- `.redacted.txt` files in directory are skipped — PASS
- Unsupported extensions (e.g. `.png`) skipped, no error — PASS
- One corrupt file does not abort batch; `failed=1`, `succeeded=N-1` — PASS
- `--recursive` finds files in subdirectories; without flag they are skipped — PASS
- Empty directory: `processed=0, succeeded=0, failed=0`, no error — PASS
- `on_file` callback invoked once per file — PASS
- 229 tests total, all passing

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
