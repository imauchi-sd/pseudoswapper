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
Detects PII using a combination of exact-match config, regex patterns, and NLP (via [Presidio](https://github.com/microsoft/presidio) + spaCy).

**Structured mode** — for CSV, JSON, and XLSX files.
Uses an anchor field (a unique identifier column like `employee_id`) to correlate all fields in a row to a single entity. The same anchor value always produces the same token, preserving relational integrity across thousands of rows.

---

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/<your-org>/pseudoswapper.git
cd pseudoswapper
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
```

Copy and edit the example config:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

---

## Quick start

```bash
# Redact a prose document
pseudoswapper document report.txt
# → writes report.redacted.txt

# Redact a structured file
pseudoswapper structured employees.csv --anchor employee_id
# → writes employees.redacted.csv

# After the AI returns its output, restore original values
pseudoswapper restore ai_output.txt
# → writes ai_output.restored.txt

# Abandon a stuck session
pseudoswapper clear-session
```

---

## Configuration

`pseudoswapper` reads `~/.pseudoswapper_config.yaml` on every run. Use it to define:

- **`company_terms`** — exact strings to always redact (project names, internal system names, domain names)
- **`employees`** — known individuals; guarantees consistent tokenisation even when NLP misses a name
- **`structured.anchor_field`** — default anchor column for structured mode
- **`structured.correlated_fields`** — columns to correlate to the anchor entity

See `pseudoswapper_config.example.yaml` for a fully annotated template.

```bash
pseudoswapper config --show    # print active config
pseudoswapper config --edit    # open config in $EDITOR
```

---

## Session lifecycle

| Event | What happens |
|---|---|
| `pseudoswapper document` or `pseudoswapper structured` succeeds | Session created; `.pseudoswapper_session` pointer written to CWD |
| `pseudoswapper restore` succeeds | Session and pointer file deleted automatically |
| `pseudoswapper restore` fails | Session preserved; retry or run `clear-session` |
| `pseudoswapper clear-session` | Deletes session and pointer file; abandons current session |
| System reboot | Temp dir gone; pointer file in CWD becomes stale (safe to delete) |

---

## Security notes

- The **redacted file** is safe to share. The **token mapping** never leaves your machine.
- `~/.pseudoswapper_config.yaml` contains employee names and internal identifiers — treat it as sensitive. Do not commit it to version control.
- `pseudoswapper` makes no network calls during redact or restore.

---

## Known limitations

- spaCy NER may miss names in non-prose contexts (log lines, headers, tables). Mitigate by listing known employees in the config.
- Email-to-name inference is not attempted in document mode. Use structured mode with an anchor field for correlated data.
- Single anchor field only — composite identity (e.g. `tenant_id` + `user_id`) is not supported in v1.
- `.docx` and `.pdf` are not supported — convert to `.txt` first.

See `USER_GUIDE.md` for full documentation.

---

## Development

```bash
pip install -e ".[dev]"
python3 -m pytest
```

Project layout and phase-by-phase build plan: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
