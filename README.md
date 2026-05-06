# pseudoswapper

A local CLI tool for tokenising sensitive data in files before sharing them with AI assistants.

All processing happens on your machine. No sensitive data or token mappings ever leave your device.

---

## What it does

Before you share a document or data file with an AI assistant, `pseudoswapper` scans it and replaces sensitive values — names, email addresses, phone numbers, domains, company identifiers — with human-readable tokens like `[PERSON_1]`, `[EMAIL_2]`, `[COMPANY_1]`. You share the tokenised file. When the AI returns its output, you run `pseudoswapper restore` and the original values are substituted back in.

The token-to-value mapping is held in a temporary, user-only directory for the duration of the session and deleted automatically after a successful restore. Nothing is written to a persistent file.

---

## Two modes

**Document mode** — for prose: emails, reports, articles, freeform text.
Detects PII using a combination of exact-match config, regex patterns, and NLP (via [Presidio](https://github.com/microsoft/presidio) + spaCy `en_core_web_lg`).

**Structured mode** — for CSV, JSON, and XLSX files.
Uses an anchor field (a unique identifier column like `employee_id` or `full_name`) to correlate all fields in a row to a single entity. The same anchor value always produces the same token across all rows, preserving relational integrity.

---

## Install

Requires Python 3.12.

```bash
git clone <repo-url>
cd pseudoswapper
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
```

Copy and fill in the example config:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

---

## Quick start

```bash
# Redact a prose document
pseudoswapper document report.txt
# → writes report.redacted.txt

# Redact a structured file (anchor auto-detected or from config)
pseudoswapper structured employees.csv
# → writes employees.redacted.csv

# Override the anchor field on the CLI
pseudoswapper structured access_logs.csv --anchor user_id

# After the AI returns its output, restore original values
pseudoswapper restore ai_output.txt
# → writes ai_output.restored.txt

# Inspect or edit the active config
pseudoswapper config --show
pseudoswapper config --edit

# Abandon a stuck session
pseudoswapper clear-session
```

---

## Configuration

`pseudoswapper` reads `~/.pseudoswapper_config.yaml` on every run. Use it to define:

- **`company_terms`** — exact strings to always redact (project names, internal system names, domains)
- **`employees`** — known individuals; guarantees consistent tokenisation even when NLP misses a name
- **`exclude_terms`** — words to exclude from NLP detection (prevents over-redaction of common names)
- **`structured.anchor_field`** — default anchor column for structured mode
- **`structured.correlated_fields`** — columns to correlate to the anchor entity per row

See `pseudoswapper_config.example.yaml` for a fully annotated template.

---

## Session lifecycle

| Event | What happens |
|---|---|
| `pseudoswapper document` or `pseudoswapper structured` succeeds | Session created; `.pseudoswapper_session` pointer written to CWD |
| `pseudoswapper restore` succeeds | Session and pointer file deleted automatically |
| `pseudoswapper restore` fails | Session preserved; fix the issue and retry |
| `pseudoswapper clear-session` | Deletes session and pointer file; abandons current session |
| System reboot | Temp dir gone; pointer file in CWD becomes stale (safe to delete) |

Run `pseudoswapper restore` from the same directory where you ran the redact command.

---

## Security notes

- The **redacted file** is safe to share. The **token mapping** never leaves your machine.
- `~/.pseudoswapper_config.yaml` contains employee names and internal identifiers — treat it as sensitive. Do not commit it to version control.
- `pseudoswapper` makes no network calls during redact or restore.

---

## Known limitations

- spaCy NER may miss names in non-prose contexts (log lines, headers, tables). Mitigate by listing known employees in the config.
- Email-to-name inference is not attempted in Document mode. Use Structured mode with an anchor field for correlated data.
- Single anchor field only — composite identity (e.g. `tenant_id` + `user_id`) is not supported in v1.
- `.docx` and `.pdf` are not supported — convert to `.txt` first.

See [`USER_GUIDE.md`](USER_GUIDE.md) for full documentation including anchor field selection, restoration behaviour, and all known limitations.

---

## Development

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest          # 111 tests, all passing
```

Project layout and phase-by-phase build plan: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
