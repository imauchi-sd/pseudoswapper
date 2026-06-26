# pseudoswapper

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A local CLI tool for tokenising sensitive data in files before sharing them with AI assistants.

All processing happens on your machine. No sensitive data or token mappings ever leave your device. Designed for temporary, one-off use — each redact → restore cycle is self-contained and leaves no persistent artefacts. Unlike tools that use encryption keys to support long-term reversible anonymisation, pseudoswapper requires no key management: the mapping exists only for the duration of a single session and is deleted automatically after restore.

---

## What it does

Before you share a document or data file with an AI assistant — or any untrusted or public tool — `pseudoswapper` scans it and replaces sensitive values — names, email addresses, phone numbers, domains, company identifiers — with human-readable tokens like `[PERSON_1]`, `[EMAIL_2]`, `[COMPANY_1]`. You share the tokenised file. When the AI returns its output, you run `pseudoswapper restore` and the original values are substituted back in. An optional mask mode permanently redacts values where recovery is not needed — for example, showing only the first 6 and last 4 digits of a payment card number, or replacing person names with initials + a sequence number (e.g. `5_J.D.`).

The token-to-value mapping is held in a temporary, user-only directory for the duration of the session and deleted automatically after a successful restore. Nothing is written to a persistent file.

---

## When to use it

- You want to ask an AI assistant (ChatGPT, Claude, Gemini, Copilot) to review, summarise, or analyse a document that contains real names, email addresses, or internal identifiers
- You need to upload a file to an online conversion, translation, or analysis service and don't want to expose its contents
- You're sharing data with a contractor or external collaborator via a tool or platform you don't fully control
- You're running a log file, support ticket, or incident report through a third-party debugging or analysis service
- You want to share the structure and content of a dataset for analysis without revealing who or what it relates to
- You are responding to a DSAR (Data Subject Access Request) and need to provide a document to the requestor while permanently masking all other individuals' PII within the same file

---

## Commands

**`document`** — for prose: emails, reports, articles, freeform text, Word documents (`.docx`), and PDFs (`.pdf`).
Detects PII using a combination of exact-match config, regex patterns, and NLP (via [Presidio](https://github.com/microsoft/presidio) + spaCy `en_core_web_lg`).
For `.docx` files, replacement is applied at the paragraph level and the output is a valid `.redacted.docx` file.
For `.pdf` files, text is extracted and the output is a `.redacted.txt` file (layout is not preserved).

**`structured`** — for CSV, JSON, and XLSX files.
Uses an anchor field (a unique identifier column like `employee_id` or `full_name`) to correlate all fields in a row to a single entity. The same anchor value always produces the same token across all rows, preserving relational integrity. Multi-sheet XLSX files are fully supported — all sheets are redacted and written back to the output workbook using a shared entity registry.

**`redact`** — for one-time permanent sanitisation without a session.
Accepts a single file or a folder. Supports all file types from `document`/`structured` plus `.eml` and `.msg` email files. Uses a relaxed protection model so names and emails can be left visible for internal teams (configurable with `--passthrough` or a named profile). Detects three additional entity types useful in incident response: financial figures (`AMOUNT`), EU bank accounts (`IBAN_CODE`), and MAC addresses (`MAC_ADDRESS`). When a folder is supplied, all supported files are processed in one pass using a shared entity registry — the same name produces the same mask across every file in the batch.

**`dsar-redaction`** — for Data Subject Access Request compliance.
Permanently masks all PII in a document *except* the data subject's own information. The requestor's name, email, and other configured values are preserved exactly as-is; all other detected PII is permanently masked (same format as mask mode). Supports all file formats accepted by `document` and `structured`. A per-subject YAML config stores the requestor's known PII values — the tool prompts to create one interactively if it does not already exist.

---

## Install

Requires Python 3.12.

```bash
git clone https://github.com/imauchi-sd/pseudoswapper
cd pseudoswapper
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m spacy download en_core_web_lg
```

Copy and fill in the example config:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

For platform-specific instructions (Mac, Windows, Linux) and alternative install methods, see the [Installation section in USER_GUIDE.md](USER_GUIDE.md#installation).

---

## Quick start

```bash
# Set a work directory so you can omit file paths (optional but convenient)
pseudoswapper workdir --set ~/Documents/sensitive-files

# Redact a prose document — pick from work directory if no path given
pseudoswapper document report.txt
pseudoswapper document            # → prompts file selection from work directory

# Redact a structured file (anchor auto-detected or from config)
# An interactive prompt lists columns and asks which to force-tokenize (Enter to skip)
pseudoswapper structured employees.csv
pseudoswapper structured          # → prompts selection of .csv/.json/.xlsx files

# Override the anchor field on the CLI
pseudoswapper structured access_logs.csv --anchor user_id

# Force-tokenize specific columns, bypassing NER (repeatable; skips interactive prompt)
pseudoswapper structured employees.xlsx --force-fields "Last name, First name" --force-fields "Email"

# Leave certain entity types unreplaced (e.g. keep IPs visible in a security log)
# Protected types (PERSON, EMAIL, COMPANY, ORG) are always tokenized regardless
pseudoswapper document incident.log --passthrough IP
pseudoswapper document incident.log --passthrough IP --passthrough DOMAIN
pseudoswapper structured access_logs.csv --anchor user_id --passthrough IP --passthrough URL

# Supply an employee roster per-invocation (both modes)
pseudoswapper document report.txt --employees-csv ~/company_employees.csv
pseudoswapper structured access_logs.csv --anchor user_id --employees-csv ~/company_employees.csv

# Switch permanently between reversible tokenisation and permanent masking (saved in prefs)
pseudoswapper mode mask
pseudoswapper mode tokenize
pseudoswapper mode            # → shows current setting

# Or override mode for a single run without changing the saved preference
pseudoswapper document report.txt --mask
pseudoswapper structured employees.csv --mask
pseudoswapper document report.txt --no-mask   # force tokenize even if mode=mask

# After the AI returns its output, restore original values
pseudoswapper restore ai_output.txt
pseudoswapper restore             # → prompts file selection from work directory
# → writes ai_output.restored.txt

# One-time permanent redaction — no session, no restore path
# Single file (any supported format including .eml and .msg)
pseudoswapper redact incident_report.txt
pseudoswapper redact phishing_sample.eml
pseudoswapper redact affected_accounts.xlsx

# Leave names and emails visible so the security team can act on the report
pseudoswapper redact incident_report.txt --passthrough PERSON --passthrough EMAIL

# Use a named profile from config
pseudoswapper redact report.xlsx --profile incident_report

# Batch: process all supported files in a folder
pseudoswapper redact ~/incident-artifacts/
pseudoswapper redact ~/incident-artifacts/ --recursive

# DSAR: mask all PII except the data subject's own information
# Supply a pre-built subject config:
pseudoswapper dsar-redaction report.pdf --subject-config dsar_subject.yaml
# Or let the tool prompt you for the subject's details and save dsar_subject.yaml:
pseudoswapper dsar-redaction report.pdf
# Works with structured files too (auto-detected by extension):
pseudoswapper dsar-redaction access_logs.csv --subject-config dsar_subject.yaml

# Show a human-readable summary of what will be tokenized
pseudoswapper config --summary

# Inspect or edit the raw config YAML
pseudoswapper config --show
pseudoswapper config --edit

# Manage work directory
pseudoswapper workdir --show
pseudoswapper workdir --clear

# Abandon a stuck session
pseudoswapper clear-session
```

---

## Configuration

`pseudoswapper` reads `~/.pseudoswapper_config.yaml` on every run. Use it to define:

- **`company_terms`** — exact strings to always redact (project names, internal system names, domains)
- **`employees`** — known individuals listed inline; guarantees consistent tokenisation even when NLP misses a name
- **`employees_csv`** — path to a CSV file of employees (use instead of or alongside `employees` for large rosters); must have a `full_name` column, optionally `email` and `username`
- **`exclude_terms`** — words to exclude from NLP detection (prevents over-redaction of common names)
- **`passthrough_types`** — entity types to leave unreplaced (e.g. `IP`, `DOMAIN`, `URL`, `PHONE`, `LOC`); useful when certain technical values carry analytical value. Protected types (`PERSON`, `EMAIL`, `COMPANY`, `ORG`) cannot be bypassed. Also overridable per-run via `--passthrough` on the CLI.
- **`masking_rules`** — entity types to permanently redact rather than tokenise. Masked values are not restorable. Supported types: `PERSON` (replaces names with initials + sequence, e.g. `5_J.D.`) and `CREDIT_CARD` (retains first/last digits, e.g. `411111XXXXXX1111`). `CREDIT_CARD` is a new protected type added alongside `PERSON`, `EMAIL`, `COMPANY`, and `ORG` — it cannot be bypassed via `passthrough_types`.
- **`redact_profiles`** — named passthrough configurations for `pseudoswapper redact`. Each profile lists entity types that should remain visible. `CREDIT_CARD` is always excluded regardless of what a profile lists.
- **`structured.anchor_field`** — default anchor column for structured mode
- **`structured.correlated_fields`** — columns to correlate to the anchor entity per row
- **`structured.force_fields`** — columns to always tokenize unconditionally, bypassing NLP (useful for name columns with non-Western names or non-standard formatting)

You can also pass a CSV per-invocation with `--employees-csv` on any redact command — this takes priority over the config key.

See `pseudoswapper_config.example.yaml` for a fully annotated template, and `employees_sample.csv` for the expected CSV format.

**Work directory and mode preferences** (`~/.pseudoswapper_prefs.yaml`) — set via `pseudoswapper workdir --set PATH` and `pseudoswapper mode [tokenize|mask]`. This file is written by the tool and is separate from your config file.

---

## Session lifecycle

| Event | What happens |
|---|---|
| `pseudoswapper document` or `pseudoswapper structured` succeeds | Session created; `.pseudoswapper_session` pointer written to CWD |
| `pseudoswapper redact` succeeds (file or folder) | No session created — output files only; no restore path |
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

See [`PRIVACY.md`](PRIVACY.md) for the full privacy policy and user responsibility disclaimers. To report a security vulnerability, see [`SECURITY.md`](SECURITY.md).

---

## Known limitations

- spaCy NER may miss names in non-prose contexts (log lines, headers, tables). Mitigate by listing known employees in the config or using `force_fields` in structured mode to guarantee tokenization of specific columns.
- Email-to-name inference is not attempted in Document mode. Use Structured mode with an anchor field for correlated data.
- Single anchor field only — composite identity (e.g. `tenant_id` + `user_id`) is not supported in v1.
- `.docx` is supported natively — output is a `.redacted.docx` file. Intra-paragraph run-level formatting (bold/italic on specific words) is lost in paragraphs that contain a replaced token.
- `.pdf` is supported natively — output is always a `.redacted.txt` file (layout not preserved). Scanned/image-only PDFs with no embedded text are not supported.
- `.eml` and `.msg` are supported in `redact` mode only — attachments are not extracted inline; save attachments separately and include them in a batch folder redaction.
- `AMOUNT` detection (financial figures) relies on spaCy's English-language `MONEY` NER and may miss non-English monetary expressions.

See [`USER_GUIDE.md`](USER_GUIDE.md) for full documentation including anchor field selection, restoration behaviour, and all known limitations.

---

## Support

If this tool saves you time, consider buying me a coffee.

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/imauchisd)

---

## Development

```bash
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest          # 229 tests, all passing
```

**Python interpreter:** the project requires the `.venv` at the project root (Python 3.12). Always activate it before running any `python` or `pytest` commands.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for contribution guidelines and the data safety checklist that applies to all commits.
