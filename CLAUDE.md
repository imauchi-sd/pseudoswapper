# CLAUDE.md — Session Briefing: Local Data Redaction Tool

## Python Interpreter

This project uses a `.venv` at the project root (Python 3.12). `.claude/settings.json` prepends
`.venv/bin` to PATH so `python3` resolves correctly in Claude Code sessions.

If a command produces unexpected Python version output or import errors, use the explicit path:
`.venv/bin/python` instead of `python3`.

---

## Project Overview

Build a Python CLI tool for local, session-scoped tokenisation of sensitive data in files before
sharing with external AI assistants. All processing happens locally. No sensitive data leaves the
machine. No external API calls are made during redaction or restoration.

The tool has two primary operations:
- `pseudoswapper document <file>` / `pseudoswapper structured <file>` — detects and replaces
  sensitive data with tokens, holds the mapping in memory
- `pseudoswapper restore <file>` — accepts AI output and reverses tokens back to original values

---

## Core Design Principles

### 1. Session-scoped token maps (no persistence by default)
The mapping dictionary (token → original value) is never written to any user-visible, persistent
file. The YAML config stores *definitions* (what to look for), never *mappings* (what was replaced).

Because `redact` and `restore` are two separate process invocations, the session map is bridged
via a private temp directory (`tempfile.mkdtemp()`, mode 0700) containing `session.json`, with a
`.pseudoswapper_session` pointer file written to the CWD so the restore process can locate it.

**Session lifecycle:** On successful restore, the temp dir and pointer file are deleted
automatically. On restore failure, the session is preserved for retry. `pseudoswapper clear-session`
is an explicit escape hatch to abandon a stuck or unwanted session.

Persistence is explicitly out of scope for v1. If added later, it must be opt-in and encrypted.

### 2. Global entity registry within a session
The same input value must always produce the same token within a session, regardless of where it
appears in the file. This preserves relational structure — e.g. a user ID appearing across 1000
log lines must consistently map to `PERSON_1`, or the AI loses the ability to trace that entity's
actions.

### 3. Person entity model
A person is the unit of tokenisation, not individual strings. When a full name is first registered,
all surface forms are registered together:
- `"John Doe"` → `[PERSON_1]`
- `"John"` → `[PERSON_1_FIRST]`
- `"Doe"` → `[PERSON_1_LAST]`

Longest-match-first replacement prevents partial collisions (full name matched before first/last).

### 4. Token format
Human-readable tokens are preferred over opaque UUIDs so that the AI output remains coherent
and interpretable. Format: `[PERSON_1]`, `[EMAIL_1]`, `[DOMAIN_1]`, `[COMPANY_1]`, `[ORG_1]` etc.

---

## Two Operating Modes

### Mode 1: Document Mode
**For:** Prose documents, articles, reports, emails, freeform text files.

**Detection layers (applied in this order):**
1. YAML config exact-match — highest priority, company-specific terms, known employees
2. Regex — email addresses, phone numbers, URLs, domain names, IP addresses
3. NLP (spaCy) — person names, organisation names, locations (least reliable, applied last)

**Correlation:** Full name / first name / last name correlated via the person entity model.
Emails are treated as independent tokens — no attempt to infer name-email linkage in this mode.
This is a documented limitation, not a bug.

**Processing unit:** Whole document.

---

### Mode 2: Structured Mode
**For:** CSV files, spreadsheets (.xlsx), JSON files, structured log files.

**Key difference:** The *row* (or JSON object) is the unit of correlation. Fields within the same
row are assumed to relate to the same real-world entity.

**Anchor field:** The user designates one field as the entity anchor — the field that uniquely and
stably identifies the entity across all rows. On first encounter of an anchor value, all correlated
fields in that row are registered together under the same entity token. On subsequent rows
containing the same anchor value, all correlated fields resolve back to the same entity token.

**Anchor field requirements (enforce via user guide, not code validation):**
- Must be unique per real-world entity (no shared values across different people)
- Must be stable across all rows (not recycled or reassigned)
- Must always be populated (null anchor = orphaned row, fields tokenised independently)
- Prefer system-assigned IDs (employee GUID, user ID) over human-readable names

**Auto-detection:** Infer anchor field from common column header patterns (`name`, `full_name`,
`employee`, `user`, `username`, `user_id`, `employee_id`). Always overridable via YAML or CLI flag.

**JSON:** Treated identically to structured mode. Traverse object array, identify anchor key,
correlate fields within each object. Support dot-notation paths in config (e.g. `user.id`).

---

## YAML Configuration File

Location: `~/.pseudoswapper_config.yaml`
This file persists across sessions — it contains definitions only, never token mappings.

```yaml
# Exact-match company-specific terms (applied in Document and Structured modes)
company_terms:
  - Acme Corporation
  - Acme Corp
  - acme.com
  - Project Nightingale
  - internal-system-name

# Known employees — pre-registers entities before file scan
# Guarantees consistent tokenisation even if NER misses the name
employees:
  - full_name: John Doe
    email: john.doe@acme.com
    username: jdoe
  - full_name: Jane Smith
    email: j.smith@acme.com
    username: jsmith

# For large rosters, point to a CSV file (full_name required; email, username optional)
# employees_csv: ~/company_employees.csv

# Entity types to leave unreplaced (bypassable only: IP, DOMAIN, URL, PHONE, LOC)
# PERSON, EMAIL, COMPANY, ORG are always tokenized and cannot appear here
# passthrough_types:
#   - IP
#   - DOMAIN

# Words to exclude from NLP detection (prevents over-redaction of common names)
# exclude_terms:
#   - May
#   - Will

# Structured mode settings
structured:
  anchor_field: employee_id         # overrides auto-detection
  correlated_fields:                # fields to correlate to anchor entity per row
    - email
    - username
    - display_name
    - full_name
  force_fields:                     # columns to always tokenize unconditionally
    - "Last name, First name"
```

---

## Detection Coverage

| Layer | Method | Covers |
|---|---|---|
| YAML exact-match | String matching | Company names, project names, internal identifiers, known employees |
| Regex | Pattern matching | Emails, phone numbers, domains, URLs, IP addresses |
| NLP | spaCy `en_core_web_lg` | Person names, org names, locations (best-effort) |

spaCy NER is the least reliable layer and may miss names in non-prose contexts (tables, headers,
log lines). The YAML employee list is the safety net for high-value known individuals.

---

## Email Handling

### Document mode
Emails are independent tokens. `john.doe@acme.com` → `[EMAIL_1]`. No linkage to any person token.
Documented limitation: the AI will not know this email belongs to `[PERSON_1]`.

### Structured mode
Emails within the same row as the anchor entity are correlated. `john.doe@acme.com` in the same
row as anchor `John Doe` → registered as `[EMAIL_PERSON_1]` to signal the linkage.

Secondary signal: attempt to match `firstname.lastname` pattern in the email local part as a
corroboration check within the same row. Best-effort, not guaranteed.

---

## Known Limitations

Document these prominently in USER_GUIDE.md:

1. **NER misses** — spaCy may miss names in non-prose structures. Mitigate with YAML employee list
   or `force_fields` in structured mode.
2. **Email inference is imperfect** — Non-standard formats (`jd@`, `john_d@`) won't auto-correlate
   in Document mode. Structured mode with explicit anchor is the solution.
3. **Composite identity** — Systems requiring two fields to uniquely identify a person (e.g.
   `tenant_id` + `user_id`) are not supported in v1. Single anchor only.
4. **Anchor field trust** — The tool preserves relational structure but cannot verify it. A
   non-unique, unstable, or sparse anchor produces output that is internally consistent but
   factually wrong. The AI receiving it cannot detect this.
5. **Restoration tolerance** — AI output may reformat tokens (case changes, markdown wrapping).
   Restoration logic must use fuzzy/case-insensitive matching to catch common variants.
6. **NER false positives** — Common words that are also names may be over-redacted. YAML can
   explicitly exclude terms if needed (`exclude_terms` list in config).
7. **Opaque ID anchors restore to the ID, not the name** — When an ID field (e.g. `employee_id =
   "E001"`) is the anchor, `[PERSON_1]` restores to `"E001"`. If human-readable name restoration
   is needed, use `full_name` as the anchor field instead.
8. **passthrough_types is a deliberate privacy trade-off** — Bypassed entity types appear as-is in
   the redacted file. Only `PERSON`, `EMAIL`, `COMPANY`, and `ORG` are always protected. Users are
   responsible for assessing whether bypassed types (IP, DOMAIN, URL, PHONE, LOC) are safe to share
   in their specific context.
9. **DOCX intra-paragraph formatting loss** — When a paragraph contains a replaced token, all
   run-level formatting within that paragraph (e.g. a bold word, an italic phrase) is lost. The
   paragraph's style (font size, spacing, heading level) is preserved. Planned Stage 1 limitation.
10. **PDF output is always plain text** — PDF input is extracted to text and the redacted output is
    written as `.redacted.txt`. PDF layout, columns, and tables are not preserved. Scanned/image
    PDFs (no embedded text) produce an error — OCR is out of scope. Planned Stage 2 limitation.

---

## Expected File Structure

```
pseudoswapper/
├── pyproject.toml
├── pseudoswapper_config.example.yaml
├── USER_GUIDE.md
├── src/pseudoswapper/
│   ├── __init__.py
│   ├── cli.py                  # Typer entry point — thin layer only
│   ├── config.py               # YAML config loader, ConfigError, _require helper
│   ├── session.py              # Temp dir lifecycle, .pseudoswapper_session pointer
│   ├── entity_registry.py      # In-memory token store, serialisation
│   ├── recognizers.py          # CompanyTermsRecognizer, EmployeeRecognizer
│   ├── detector.py             # Presidio AnalyzerEngine wrapper
│   ├── tokenizer.py            # DetectedEntity → token, person entity model
│   ├── replacer.py             # Longest-match-first text replacement
│   ├── restore.py              # Token reversal with fuzzy/case-insensitive match
│   ├── modes/
│   │   ├── __init__.py
│   │   ├── document.py         # Document mode orchestrator
│   │   └── structured.py       # Structured mode (CSV / JSON / XLSX)
│   └── extractors/             # Planned: rich-format extraction (Stage 1 + 2)
│       ├── __init__.py
│       ├── docx.py             # python-docx extractor + paragraph writer
│       └── pdf.py              # pdfplumber text extractor
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── sample_document.txt
    │   ├── sample_document.docx    # planned Stage 1
    │   ├── sample_document.pdf     # planned Stage 2
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
    ├── test_structured.py
    ├── test_docx.py               # planned Stage 1
    └── test_pdf.py                # planned Stage 2
```

---

## CLI Interface

```bash
# Document mode
pseudoswapper document report.txt
pseudoswapper document report.txt --employees-csv ~/employees.csv
pseudoswapper document incident.log --passthrough IP --passthrough DOMAIN

# Structured mode
pseudoswapper structured access_logs.csv --anchor user_id
pseudoswapper structured employees.json --anchor user.id
pseudoswapper structured data.xlsx --anchor employee_id
pseudoswapper structured data.xlsx --anchor employee_id --force-fields "Last name, First name"
pseudoswapper structured access_logs.csv --anchor user_id --passthrough IP

# Restore (mode-agnostic)
pseudoswapper restore ai_output.txt

# Session management
pseudoswapper clear-session          # abandon a session and delete all artifacts

# Work directory (omit file argument to pick interactively)
pseudoswapper workdir --set ~/Documents/sensitive-files
pseudoswapper workdir --show
pseudoswapper workdir --clear

# Config helpers
pseudoswapper config --summary       # human-readable view of what will be tokenized
pseudoswapper config --show          # raw YAML dump
pseudoswapper config --edit          # open in $EDITOR
```

Output files should be written alongside the input file with a `.redacted` suffix.
Example: `report.txt` → `report.redacted.txt`

---

## Dependencies

```
typer>=0.12
pyyaml>=6.0
presidio-analyzer>=2.2
presidio-anonymizer>=2.2
spacy>=3.7
en_core_web_lg          # python -m spacy download en_core_web_lg
pandas>=2.0
openpyxl>=3.1           # for .xlsx support via pandas
```

Planned additions (rich format support):

```
python-docx>=1.1        # Stage 1: .docx extraction and round-trip writing
pdfplumber>=0.10        # Stage 2: .pdf text extraction (MIT license)
```

`pymupdf` (fitz) was evaluated for Stage 2 and rejected: its AGPL license is incompatible with
distribution. `pdfplumber` is sufficient and MIT licensed.

---

## Out of Scope for v1

- Persistent encrypted token maps
- GUI of any kind
- Cloud sync or any network calls during redact/restore
- Automatic email-to-name inference beyond same-row structured mode correlation
- Composite anchor fields (multi-field identity)
- Binary file formats beyond .xlsx — `.docx` and `.pdf` are planned (see below); all others require
  manual conversion to `.txt` first

---

## Planned Extensions: Rich Format Support

Document mode will be extended to handle `.docx` (Stage 1) and `.pdf` (Stage 2) natively. The
detection and tokenisation pipeline is unchanged — only extraction and output writing differ. The
dispatch lives in `modes/document.py` as a simple `if/elif/else` on the file suffix.

---

### Stage 1: `.docx` support

**New dependency:** `python-docx >= 1.1`

**New module:** `src/pseudoswapper/extractors/docx.py`

Two responsibilities:
- `extract_paragraphs(path) -> list[str]` — returns full paragraph strings (all XML runs within
  each paragraph concatenated) for use as the detection input
- `apply_token_map(src, token_map, out)` — opens the original `.docx`, walks every paragraph in
  the body, table cells, headers, and footers; applies token replacement at the paragraph level;
  saves to `out` as a new `.docx` file

**The run-split problem.** `.docx` text is stored in `<w:r>` (run) XML elements. A single name
like "John Doe" can span two runs if formatting changes mid-phrase (e.g. "Doe" is bolded):

```xml
<w:r><w:t>John </w:t></w:r>
<w:r><w:rPr><w:b/></w:rPr><w:t>Doe</w:t></w:r>
```

Run-by-run replacement is blind to cross-run names. The solution is paragraph-level replacement:
concatenate all run texts, apply the token map, then write back as a single new run inheriting the
paragraph's style object. This loses intra-paragraph run-level formatting (e.g. a bold word within
a paragraph becomes un-bolded in replaced paragraphs), which is acceptable because the output is
consumed by an AI, not a human reader.

**Output format:** `.redacted.docx` — same format, paragraph-level structure preserved.
`_output_path` in `document.py` already produces the correct suffix with no changes.

**Changes to existing code:**
- `modes/document.py` — add suffix dispatch: `.docx` calls `extractors/docx.extract_paragraphs`
  for detection text, then `extractors/docx.apply_token_map` for the output file
- `cli.py` — no changes; `.docx` is already excluded from `_STRUCTURED_EXTENSIONS` and will
  appear in the document mode file picker automatically

**Known limitations (documented in USER_GUIDE.md):**
- Intra-paragraph run-level formatting (bold/italic on individual words) is lost in any paragraph
  containing a replaced token
- Cross-paragraph names are not correlated (NER does not span paragraphs in practice)
- Comments and tracked changes are not scanned

---

### Stage 2: `.pdf` support

**New dependency:** `pdfplumber >= 0.10`

`pymupdf` (fitz) was considered and rejected: AGPL license is incompatible with distribution.
`pdfplumber` (MIT) is sufficient for text extraction.

**New module:** `src/pseudoswapper/extractors/pdf.py`

Single responsibility: `extract_text_from_pdf(path) -> str`
- Opens with `pdfplumber`, extracts text page by page
- Joins pages with `\n\n`
- Raises `UnsupportedFileError` if all pages yield empty text (scanned/image PDF — no OCR in v1)

**Output format: always `.redacted.txt`**, regardless of input extension.

PDFs store drawing instructions, not a document model. Round-trip editing (extract → replace →
write back as PDF with original layout) is not feasible. Three alternatives were considered:

| Option | Verdict |
|---|---|
| Black-box redaction (paint rectangles over sensitive regions) | Rejected — AI cannot read redacted content |
| Rebuild PDF via reportlab with replaced text | Rejected — loses layout anyway, high complexity |
| Plain text output | **Chosen** — AI gets full content; restore works identically |

**`_output_path` override:** The existing helper produces `report.pdf` → `report.redacted.pdf`.
For PDF inputs, the output suffix must be forced to `.txt`: `report.pdf` → `report.redacted.txt`.
This override is isolated to `modes/document.py` in the `.pdf` dispatch branch.

**Changes to existing code:**
- `modes/document.py` — add `.pdf` dispatch branch; call `extractors/pdf.extract_text_from_pdf`;
  override output suffix to `.txt` for PDF inputs
- `cli.py` — no changes; `.pdf` is already excluded from `_STRUCTURED_EXTENSIONS`

**Known limitations (documented in USER_GUIDE.md):**
- Output is always `.txt` — PDF layout and formatting are not preserved
- Multi-column layouts may extract in wrong reading order (pdfplumber mitigates but does not
  eliminate this)
- Scanned/image PDFs produce an error; OCR is out of scope for v1
- Table content embedded in PDFs may have cell-ordering artifacts
