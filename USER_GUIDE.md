# pseudoswapper — User Guide

## Table of Contents

1. [What this tool does and doesn't do](#1-what-this-tool-does-and-doesnt-do)
2. [Choosing a mode](#2-choosing-a-mode)
3. [Setting up the config file](#3-setting-up-the-config-file)
4. [Anchor field selection (Structured mode)](#4-anchor-field-selection-structured-mode)
5. [Running the tool](#5-running-the-tool)
6. [Restoring AI output](#6-restoring-ai-output)
7. [Known limitations](#7-known-limitations)
8. [Security notes](#8-security-notes)
9. [Troubleshooting](#9-troubleshooting)
10. [DSAR redaction](#10-dsar-redaction)
11. [One-time redaction (redact command)](#11-one-time-redaction-redact-command)

---

## 1. What this tool does and doesn't do

### The problem it solves

You have a document or data file containing sensitive information — employee names, email addresses, internal project names, server IPs — and you want to share it with an AI assistant, an online service, or any other untrusted or public tool for analysis, summarisation, or refactoring. Manually removing and re-inserting those values is tedious and error-prone.

`pseudoswapper` automates both halves:

1. **Redact** — scan the file, replace each sensitive value with a human-readable token (`[PERSON_1]`, `[EMAIL_2]`, `[COMPANY_1]`), write the tokenised file.
2. **Restore** — after the tool returns its output, swap all tokens back to the original values.

It is designed for temporary, one-off use. Each redact → restore cycle is self-contained: the mapping exists only for the duration of the session and is deleted automatically after restore. No encryption keys to manage, nothing left on disk.

### What never leaves your machine

- The original sensitive values
- The token-to-value mapping

The mapping is held in a private temporary directory (mode `0700`, inaccessible to other OS users) for the duration of one redact → restore cycle. It is deleted automatically after a successful restore. Nothing is written to a persistent, user-visible file.

### Relational integrity

Consistent tokenisation across a file is not cosmetic — it is what makes AI output useful. If a user ID appears in 1000 log lines and each occurrence gets a different token, the AI cannot trace that user's actions. `pseudoswapper` guarantees that the same input value always produces the same token within a session. An ID that appears 1000 times is always `[PERSON_1]`, so the AI can reason about it coherently.

### What it doesn't do

- It does not make network calls at any point during redact or restore.
- It does not persist token mappings between sessions (v1).
- It does not support scanned or image-only PDFs (no embedded text layer) — convert to text first.
- It does not guarantee 100% detection coverage for NLP-discovered entities (see [Known limitations](#7-known-limitations)).

---

## 2. Choosing a mode

### Document mode — for prose, Word documents, and PDFs

Use document mode for freeform text: emails, reports, articles, meeting notes, support tickets, log excerpts copy-pasted into a text file. Word documents (`.docx`) and PDFs (`.pdf`) are also supported natively.

- `.docx` — output is a valid `.redacted.docx` file with paragraph-level structure preserved
- `.pdf` — text is extracted from the PDF and output is a `.redacted.txt` file; layout is not preserved. Scanned/image-only PDFs (no embedded text) are not supported.

Detection uses three layers in priority order:

| Layer | What it finds |
|---|---|
| YAML exact-match | Company names, project names, internal identifiers, known employees |
| Regex | Email addresses, phone numbers, URLs, domain names, IP addresses |
| NLP (spaCy) | Person names, organisation names, locations (best-effort) |

**Limitation:** In document mode, an email address and the person it belongs to are tokenised independently (`[PERSON_1]` and `[EMAIL_1]`). The AI will not automatically know they are linked. Use Structured mode with an anchor field if that linkage matters.

### Structured mode — for tables and structured data

Use structured mode for CSV files, JSON arrays, and Excel spreadsheets.

The key difference: each row is treated as a self-contained entity bundle. You nominate one column as the **anchor field** — the stable, unique identifier for each real-world entity. All rows sharing the same anchor value are guaranteed to produce the same token, and correlated fields (email, username, display name) within the same row are registered alongside the anchor.

**Use structured mode when:**
- Your file is a CSV, spreadsheet, or JSON array
- You have a column that uniquely identifies each person (employee ID, user ID, full name)
- You want the AI to know that a name and an email address belong to the same person

### DSAR redaction — for compliance use cases

Use `dsar-redaction` when you are responding to a Data Subject Access Request and need to provide a document to the requestor while permanently masking all other individuals' PII within the same file.

- The requestor's own PII (name, email, employee ID, etc.) is preserved exactly as-is
- All other detected PII is permanently masked — same format as mask mode
- Always runs in mask mode regardless of the global mode preference
- Supports all file formats accepted by `document` and `structured` (auto-detected by extension)

See [Section 10](#10-dsar-redaction) for a full walkthrough.

### One-time redaction (`redact`) — for incident reports and internal distribution

Use `pseudoswapper redact` when you need to permanently sanitise a file for sharing with internal teams and there is no restore path. Unlike `document`/`structured`, the `redact` command:

- Never writes a session — there is nothing to restore
- Allows named individuals and email addresses to remain visible (configurable with `--passthrough` or a profile), so the security or operations team can act on the report
- Detects additional data types relevant to incident response: financial figures (`AMOUNT`), EU bank accounts (`IBAN_CODE`), and MAC addresses (`MAC_ADDRESS`)
- Accepts `.eml` and `.msg` email files directly
- Accepts a folder path to process multiple files in one pass (batch mode)

See [Section 11](#11-one-time-redaction-redact-command) for a full walkthrough.

### Quick decision guide

```
Is this a DSAR response — preserve one person's PII, mask everyone else's?
  → YES: use pseudoswapper dsar-redaction

Do you need a reversible session you can restore after sharing with an AI?
  → YES: use pseudoswapper document (prose, .docx, .pdf)
         or pseudoswapper structured (.csv, .json, .xlsx)

Do you need to permanently sanitise for an internal audience with no restore needed?
  → YES: use pseudoswapper redact
         (supports .txt, .docx, .pdf, .eml, .msg, .csv, .json, .xlsx; also accepts a folder)
```

### Tokenize vs mask

Both Document and Structured mode can run in one of two redaction styles:

**Tokenize (default)** — detected entities become reversible tokens like `[PERSON_1]`. After the AI returns its output, run `pseudoswapper restore` to swap tokens back to the original values. Use this when you need to read the AI's output with real names and values reinstated.

**Mask** — entities configured in `masking_rules` are permanently redacted. Person names become `5_J.D.` (sequence number + initials); payment card numbers become `411111XXXXXX1111` (first 6 + last 4 digits). Masked values cannot be restored — the session file has no record of them. Use this when permanent redaction is sufficient and you do not need to reinstate the original values.

Set the preference once:
```bash
pseudoswapper mode mask      # permanent redaction going forward
pseudoswapper mode tokenize  # back to reversible tokens
pseudoswapper mode           # show current setting
```

Or override for a single run without changing the saved preference:
```bash
pseudoswapper document report.txt --mask
pseudoswapper document report.txt --no-mask
```

The mode preference is stored in `~/.pseudoswapper_prefs.yaml` and is separate from the config file.

---

## 3. Setting up the config file

### Location

`~/.pseudoswapper_config.yaml`

Copy the example template to get started:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

Then edit it:

```bash
pseudoswapper config --edit       # opens in $EDITOR
pseudoswapper config --show       # prints the active config as raw YAML
pseudoswapper config --summary    # human-readable summary of what will be tokenized
```

`--summary` is the quickest way to verify your config after making changes — it shows entity type coverage, all configured terms and employees, and structured mode settings in a single view.

### company_terms

List exact strings that should always be redacted — highest priority, case-insensitive match.

```yaml
company_terms:
  - Acme Corporation
  - Acme Corp
  - acme.com
  - Project Nightingale
  - internal-codename
```

Use this for company names, project codenames, internal domain names, and any proprietary identifiers that the NLP layer might miss.

### employees

Pre-register known individuals. This guarantees consistent tokenisation even when NLP misses a name (e.g. in tables, headers, or short strings with no prose context).

```yaml
employees:
  - full_name: John Doe
    email: john.doe@acme.com
    username: jdoe
  - full_name: Jane Smith
    email: j.smith@acme.com
    username: jsmith
```

Only `full_name` is required. Including `username` ensures that short identifiers like `jdoe` are replaced even when they appear without context.

### employees_csv — loading a large employee roster from a CSV file

For organisations with more employees than is practical to list inline, you can point to a CSV file instead:

```yaml
employees_csv: ~/company_employees.csv
```

The CSV must have a `full_name` column. `email` and `username` are optional. Any other columns are ignored.

```
full_name,email,username
John Doe,john.doe@acme.com,jdoe
Jane Smith,j.smith@acme.com,jsmith
Alice Johnson,alice.johnson@acme.com,ajohnson
```

`employees_csv` and the inline `employees` list are merged. If the same `full_name` appears in both, the CSV entry takes precedence.

A sample file (`employees_sample.csv`) is included in the project root as a starting template.

You can also supply a CSV per-invocation using the `--employees-csv` CLI flag (see [Section 5](#5-running-the-tool)). The CLI flag takes priority over the `employees_csv` config key.

### structured settings

```yaml
structured:
  anchor_field: employee_id       # which column identifies each entity
  correlated_fields:
    - email
    - username
    - display_name
    - full_name
  force_fields:                   # columns to always tokenize, bypassing NER
    - "Last name, First name"
    - department_email
```

`force_fields` is optional. When set, every non-empty cell in those columns is tokenized unconditionally — no NLP detection is run on them. Use this for name or email columns where spaCy's entity recognition is unreliable (non-Western names, "Last, First" formatting, short strings with no prose context). Values already established by the anchor or correlated-field logic are not overwritten.

See [Section 4](#4-anchor-field-selection-structured-mode) for guidance on anchor field selection.

### redact_profiles

Save named passthrough configurations for repeated `redact` workflows. Each profile lists entity types that should remain visible in the output — useful for incident response where the security team needs to see email addresses and names to act on the report.

```yaml
redact_profiles:
  incident_report:
    passthrough: [PERSON, EMAIL, COMPANY, ORG]
  financial_audit:
    passthrough: [PERSON, EMAIL]
```

`CREDIT_CARD` is always removed from any profile's passthrough list — it is protected in all modes.

Usage: `pseudoswapper redact report.xlsx --profile incident_report`

CLI `--passthrough` flags are merged with the profile (union semantics) — the profile does not override the flags.

### exclude_terms

If the NLP layer over-redacts common words (e.g. "Will" being treated as a person name), list them here:

```yaml
exclude_terms:
  - May
  - Will
  - Mark
```

### passthrough_types

Some entity types carry analytical value and are better left unreplaced. The most common case is IP addresses in security incident logs — you want the AI to reason about specific hosts while still protecting all personal information.

```yaml
passthrough_types:
  - IP
  - DOMAIN
```

Valid values: `IP`, `DOMAIN`, `URL`, `PHONE`, `LOC`.

The following types are **always tokenized** regardless of this setting: `PERSON`, `EMAIL`, `COMPANY`, `ORG`. Listing a protected type here has no effect.

You can also override this per-run using `--passthrough` on the CLI (see [Section 5](#5-running-the-tool)). CLI flags are merged with the YAML list — they do not replace it.

### masking_rules

Specifies which entity types to permanently redact instead of tokenise. Masked values are not restorable — they are not stored in the session.

```yaml
masking_rules:
  PERSON:
    keep: initials          # "John Doe" (5th person detected) → "5_J.D."
  CREDIT_CARD:
    keep_first: 6           # digits to keep at the start
    keep_last: 4            # digits to keep at the end
    fill_char: "X"          # character to fill the middle — "4111111111111111" → "411111XXXXXX1111"
```

`PERSON` masking format: `{sequence}_{initials}` — e.g. the 5th unique name detected with initials J.D. becomes `5_J.D.`. The sequence number makes names with identical initials distinguishable, and the format is not recognised as a person name by NLP so multi-pass documents are safe.

`CREDIT_CARD` is a new protected type (alongside `PERSON`, `EMAIL`, `COMPANY`, `ORG`). Without a masking rule it is tokenised to `[CREDIT_CARD_1]`; with a masking rule it is permanently masked to the configured digit pattern. It cannot be bypassed via `passthrough_types`.

The `masking_rules` config block defines *how* to mask. Whether masking is actually applied is controlled by the `pseudoswapper mode` command or the `--mask`/`--no-mask` per-run flag — the config block has no effect while mode is `tokenize`.

### Security note

`~/.pseudoswapper_config.yaml` contains employee names and internal identifiers. Treat it as sensitive:
- Do not commit it to version control
- Do not share it alongside redacted files
- Keep it out of any backup systems that sync to the cloud

---

## 4. Anchor field selection (Structured mode)

The anchor field is the single most important configuration decision for structured mode. Getting it wrong produces output that is internally consistent but factually incorrect — and the AI receiving it cannot detect this.

### What makes a good anchor

| Requirement | Why it matters |
|---|---|
| **Unique per entity** | Two employees sharing an anchor value collapse to one token. All their rows become indistinguishable. |
| **Stable across all rows** | If an anchor value changes mid-dataset (reassigned IDs, name changes), the same person gets multiple tokens. |
| **Always populated** | Rows with a null anchor are processed independently — their fields are not correlated to any entity. |

### Prefer system-assigned IDs over human-readable names

System-assigned IDs (`employee_id`, `user_id`, `guid`) satisfy all three requirements by design. Human-readable names may not:

- **Not unique:** Two employees named "John Smith" collapse to one token.
- **Not stable:** Names change (marriage, legal change). IDs don't.
- **Not always present:** Name fields are sometimes blank; ID fields rarely are.

**When to use a name as anchor:** If your dataset has no system ID and the names are confirmed unique and stable, `full_name` is a reasonable anchor — and has the benefit that `[PERSON_1]` restores directly to the human-readable name.

### Good vs bad anchors

| Column | Verdict | Reason |
|---|---|---|
| `employee_id` | Good | System-assigned, unique, stable, always present |
| `user_guid` | Good | Same as above |
| `email` | Acceptable | Usually unique; breaks if email is reassigned |
| `full_name` | Acceptable if unique | Breaks with duplicate names; useful for readable restore output |
| `department` | Bad | Not unique — many people share a department |
| `manager_name` | Bad | Not unique, not stable |
| `first_name` | Bad | Not unique |

### What goes wrong with a bad anchor

If `department` is the anchor, everyone in "Engineering" becomes `[PERSON_1]` and everyone in "Marketing" becomes `[PERSON_2]`. The AI receives a file where all engineers appear to be the same person. The redaction is consistent (no token leaks the original data) but the AI's analysis will be nonsense.

### Auto-detection

If no anchor is configured in YAML and no `--anchor` flag is passed, `pseudoswapper` auto-detects from common column header patterns in this order: `employee_id`, `user_id`, `username`, `full_name`, `name`, `user`, `employee`. If none match, fields are tokenised independently with no cross-row correlation.

### Token restoration and anchor choice

When using an opaque ID as the anchor (e.g. `employee_id = "E001"`), the token `[PERSON_1]` restores to `"E001"`. If you want `[PERSON_1]` to restore to `"John Doe"` in the AI's output, use `full_name` as the anchor instead. List `employee_id` in `correlated_fields` to still replace it in the output.

---

## 5. Running the tool

### Installation

`pseudoswapper` requires **Python 3.12**. Follow the path below that matches your setup.

---

#### Mac users — use a virtual environment (recommended)

Macs ship with an older system Python that is used internally by macOS. Replacing or upgrading it to Python 3.12 can break system tools, so it is not recommended. The safe approach is to install Python 3.12 alongside the system Python and run `pseudoswapper` in an isolated virtual environment.

**Step 1 — Install Python 3.12 via Homebrew**

If you do not have [Homebrew](https://brew.sh) installed, open Terminal and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install Python 3.12:

```bash
brew install python@3.12
```

Verify the install:

```bash
python3.12 --version
# Expected output: Python 3.12.x
```

**Step 2 — Download the project**

Download or clone the repository into a folder on your machine. In Terminal, navigate to that folder:

```bash
cd /path/to/pseudoswapper
```

**Step 3 — Create and activate a virtual environment**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Your terminal prompt will change to show `(.venv)` — this confirms the environment is active. You need to run `source .venv/bin/activate` again each time you open a new Terminal window.

**Step 4 — Install the tool**

```bash
pip install -e .
```

**Step 5 — Download the language model**

```bash
python -m spacy download en_core_web_lg
```

This downloads the NLP model used for name detection (~750 MB, one-time only).

---

#### Windows / Linux — system Python or virtual environment

If you already have Python 3.12 installed, you can either install `pseudoswapper` into your system Python or use a virtual environment. A virtual environment is still recommended to keep dependencies isolated, but either works.

**Check your Python version first:**

```bash
python --version       # or: python3 --version
```

If the output is not `Python 3.12.x`, download Python 3.12 from [python.org](https://www.python.org/downloads/) and run the installer before continuing.

**Option A — virtual environment (recommended)**

```bash
# From the project folder:
python -m venv .venv

# Activate (Linux / macOS):
source .venv/bin/activate

# Activate (Windows):
.venv\Scripts\activate

pip install -e .
python -m spacy download en_core_web_lg
```

**Option B — system Python (no virtual environment)**

```bash
pip install .
python -m spacy download en_core_web_lg
```

The `pseudoswapper` command will be available globally without needing to activate anything.

---

#### Set up your config file

Copy the example config to your home directory:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

Open it and fill in your company-specific details:

```bash
pseudoswapper config --edit
```

See [Section 3](#3-setting-up-the-config-file) for a full walkthrough of every config option.

### Work directory

If you keep all your input files in one folder, you can register it as the work directory. When you then run `document`, `structured`, or `restore` without a file argument, the tool lists the eligible files in that folder and prompts you to pick one by number — no need to type full paths.

```bash
# Set once
pseudoswapper workdir --set ~/Documents/sensitive-files

# Check what is set
pseudoswapper workdir --show

# Remove the setting
pseudoswapper workdir --clear
```

The work directory and mode preference are both saved to `~/.pseudoswapper_prefs.yaml` (separate from your config file, so editing one never affects the other).

**File filtering by mode:**
- `document` — shows all non-structured files (excludes `.csv`, `.json`, `.xlsx`); includes `.docx`, `.pdf`, and plain text files; excludes already-redacted output files
- `structured` — shows only `.csv`, `.json`, and `.xlsx` files, excluding already-redacted outputs
- `restore` — shows all non-hidden files (AI output can be saved with any extension)

If a file is specified directly on the command line, the work directory is ignored for that invocation.

### Tokenize and mask mode

The active redaction style is controlled separately from document vs structured mode.

```bash
# Set persistent preference (stored in ~/.pseudoswapper_prefs.yaml)
pseudoswapper mode mask      # permanent redaction using masking_rules from config
pseudoswapper mode tokenize  # reversible tokenization (default)
pseudoswapper mode           # show current setting
pseudoswapper mode --show    # same as above
```

To override for a single run without changing the saved preference, use `--mask` or `--no-mask` on the `document` or `structured` command:

```bash
pseudoswapper document report.txt --mask        # apply masking this run only
pseudoswapper document report.txt --no-mask     # force tokenize even if mode=mask
pseudoswapper structured data.csv --mask
```

The flag takes priority over the saved preference. Priority order: `--mask`/`--no-mask` > saved `mode` > default (tokenize).

**Note:** Masking requires `masking_rules` to be configured in `~/.pseudoswapper_config.yaml` (see [Section 3](#3-setting-up-the-config-file)). Running `--mask` with no `masking_rules` defined will still run without error — all entities will fall back to standard tokenization.

### Document mode

```bash
pseudoswapper document report.txt
# → writes report.redacted.txt alongside the input file

pseudoswapper document email_thread.txt
# → writes email_thread.redacted.txt

# Word documents — output is a valid .docx file, not plain text
pseudoswapper document report.docx
# → writes report.redacted.docx

# PDFs — output is always plain text regardless of input format
pseudoswapper document report.pdf
# → writes report.redacted.txt

# Supply an employee roster for this run only
pseudoswapper document report.txt --employees-csv ~/company_employees.csv

# Leave IP addresses unreplaced (useful for security incident analysis)
pseudoswapper document incident.log --passthrough IP

# Multiple types — repeatable flag
pseudoswapper document incident.log --passthrough IP --passthrough DOMAIN
```

Output is written alongside the input file with a `.redacted` suffix. For `.pdf` inputs the output extension is always `.txt`: `name.txt` → `name.redacted.txt`, `name.docx` → `name.redacted.docx`, `name.pdf` → `name.redacted.txt`.

**Note for `.docx` files:** Replacement happens at the paragraph level. If a paragraph contains a replaced value, any intra-paragraph run-level formatting (e.g. a bold word, an italic phrase) is lost within that paragraph. Paragraph-level formatting (font size, heading style, spacing) is preserved. This is intentional — the output is consumed by an AI, not a human reader.

### Structured mode

```bash
# Anchor field from config
pseudoswapper structured access_logs.csv

# Override anchor field on the CLI
pseudoswapper structured employees.csv --anchor employee_id
pseudoswapper structured data.json --anchor user_id
pseudoswapper structured report.xlsx --anchor full_name

# Supply an employee roster for this run only
pseudoswapper structured access_logs.csv --anchor user_id --employees-csv ~/company_employees.csv

# Leave IP addresses and URLs unreplaced while still tokenizing all names and emails
pseudoswapper structured access_logs.csv --anchor user_id --passthrough IP --passthrough URL
```

Output follows the same naming convention: `employees.csv` → `employees.redacted.csv`.

#### CSV files with metadata headers

Some tools export CSVs with a block of report metadata above the real column headers — for example:

```
Administrator,davidau@example.com
Report Created,"May 15, 2026 2:19:08 PM UTC"
Users,"Include - [davidau@example.com]"
No.,Event Time,User,URL,...   ← real header row
1,...
```

`pseudoswapper structured` detects these automatically. It scans the first 20 rows, identifies the row with the most fields as the real header, and skips everything above it. No configuration is needed. The interactive column-selection menu also uses the detected header, so you always see the actual column names.

#### Force-tokenizing specific columns

When you run `pseudoswapper structured`, the tool reads the file's column headers and prompts you to select any columns that should be force-tokenized:

```
Columns in employees.xlsx:
  1. employee_id
  2. Last name, First name
  3. Department
  4. Email
  5. Manager

Select columns to force-tokenize (e.g. 1,4 — or Enter to skip):
```

Enter the column numbers separated by commas (e.g. `2,4`), or press Enter to skip and rely on automatic detection.

Force-tokenized columns bypass NLP detection entirely — every non-empty cell is tokenized as a person name or email unconditionally. This is the recommended fix for columns where spaCy misses names due to non-Western names, "Last, First" formatting, or short strings with no prose context.

To skip the interactive prompt, pass `--force-fields` on the CLI (one flag per column, repeatable):

```bash
# Single force field
pseudoswapper structured employees.xlsx --force-fields "Last name, First name"

# Multiple force fields
pseudoswapper structured employees.xlsx \
  --force-fields "Last name, First name" \
  --force-fields "Email"
```

To apply force fields on every run without being prompted, add them to the config file under `structured.force_fields` (see [Section 3](#3-setting-up-the-config-file)).

### DSAR redaction

For DSAR compliance use cases, use `pseudoswapper dsar-redaction` instead of `document` or `structured`. See [Section 10](#10-dsar-redaction) for a full walkthrough including subject config setup.

### Verifying the output

Before sharing the redacted file, open it and confirm:

- No original names, emails, or identifiers are visible
- Tokens are present and look like `[PERSON_1]`, `[EMAIL_PERSON_1]` etc.
- The structure of the file is intact (columns, rows, JSON shape)

The redacted file is what you share with the AI assistant.

---

## 6. Restoring AI output

### The workflow

```
1. pseudoswapper document report.txt        → report.redacted.txt
2. Share report.redacted.txt with AI
3. AI returns analysis.txt (contains tokens like [PERSON_1])
4. Save AI output to a file
5. pseudoswapper restore analysis.txt       → analysis.restored.txt
```

### Session pointer file

When you run `pseudoswapper document` or `pseudoswapper structured`, a file named `.pseudoswapper_session` is written to your current working directory. This file contains the path to the private temp directory where the token mapping is stored.

**You must run `pseudoswapper restore` from the same directory** as the one where you ran the redact command, so the restore process can find the `.pseudoswapper_session` pointer.

The pointer file itself contains no sensitive data — it is just a path.

### Auto-cleanup

After a successful restore, the session (temp dir + pointer file) is deleted automatically. You do not need to clean up manually. A completed redact → restore cycle leaves no artifacts in your working directory.

### If restore fails

If `pseudoswapper restore` exits with an error, the session is preserved so you can retry. Common causes:

- The AI output file path is wrong (check the path argument)
- You are in the wrong directory (`.pseudoswapper_session` not found)

Fix the issue and run `pseudoswapper restore` again.

### Abandoning a session

If you decide not to restore, or if the session is stuck, run:

```bash
pseudoswapper clear-session
```

This deletes the temp dir and pointer file. The original values are gone — there is no recovery path after clearing a session.

### If the session was lost

If the system rebooted, or the temp dir was deleted, or you moved to a different directory, the session cannot be recovered. The redacted file's tokens cannot be reversed. You will need to re-run the redact command on the original file.

### Token tolerance

`pseudoswapper restore` handles common AI reformatting:

- Case changes: `[person_1]`, `[PERSON_1]`, `[Person_1]` all restore correctly
- Markdown wrapping: `` `[PERSON_1]` `` and `**[PERSON_1]**` restore correctly

If the AI has substantially rewritten a token (e.g. expanding `[PERSON_1]` to `Person 1`), that occurrence will not be restored automatically. Scan the restored output for any remaining tokens.

---

## 7. Known limitations

### L1 — NLP may miss names in non-prose contexts

spaCy's named entity recognition is trained on prose. It is less reliable in tables, headers, log lines, and structured formats. Non-Western names and "Last, First" formatted fields are particularly prone to misses or misclassification.

**Impact:** A name in a CSV cell or log timestamp prefix may not be detected.

**Mitigation (choose one or both):**

- Add known employees to the `employees` list in your YAML config. Pre-registered employees are detected by exact-match before NLP runs, so they are always found regardless of context.
- In Structured mode, use `force_fields` (via the interactive prompt, `--force-fields` CLI flag, or `structured.force_fields` in config) to guarantee that every cell in a named column is tokenized unconditionally, without relying on NLP at all.

### L2 — Emails and names are not linked in Document mode

In Document mode, `john.doe@acme.com` becomes `[EMAIL_1]` and `John Doe` becomes `[PERSON_1]`. These tokens carry no linkage information. The AI will not automatically know the email belongs to the person.

**Mitigation:** Use Structured mode with `email` in `correlated_fields`. In Structured mode, an email in the same row as the anchor entity becomes `[EMAIL_PERSON_1]` — the token itself signals the linkage.

### L3 — Composite identity is not supported

If an entity is uniquely identified only by a combination of two fields (e.g. `tenant_id` + `user_id`), the tool cannot handle this in v1. Using either field alone as the anchor may cause different entities to collapse to the same token if the field is not globally unique.

**Mitigation:** If possible, create a derived unique key (e.g. concatenate the two fields into a single column) before running structured mode.

### L4 — The tool cannot validate anchor field quality

`pseudoswapper` assumes the anchor field is unique, stable, and always populated. It cannot verify this. If the anchor field has duplicate values for different people, those people will share a token — their data becomes indistinguishable in the redacted output.

**Mitigation:** Choose the anchor carefully (see [Section 4](#4-anchor-field-selection-structured-mode)). System-assigned IDs are the safest choice.

### L5 — Opaque ID anchors restore to the ID, not the name

When an opaque ID (`employee_id = "E001"`) is the anchor, the token `[PERSON_1]` restores to `"E001"`. The full name is not preserved as the canonical restored value.

**Mitigation:** Use `full_name` as the anchor if you want `[PERSON_1]` to restore to the human-readable name. Or add `employee_id` to `correlated_fields` and accept that restored output will contain IDs alongside the anchor token's canonical value.

### L6 — NLP false positives (common words redacted as names)

spaCy may interpret common English words as person names — "Will", "May", "Mark", "Grace" — especially in short sentences without context.

**Impact:** Over-redaction: words that are not actually names are replaced with person tokens.

**Mitigation:** Add the affected terms to `exclude_terms` in your YAML config.

### L7 — DOCX intra-paragraph formatting loss

When a paragraph in a `.docx` file contains a replaced value, all run-level formatting within that paragraph is lost. For example, if "John Doe" appears in a paragraph where "Doe" is bolded, the replacement removes that bold. Paragraph-level formatting (heading style, font size, line spacing) is preserved.

**Impact:** The redacted `.docx` is structurally valid and fully readable, but may look visually different from the original in paragraphs that contained PII.

**Mitigation:** None — this is an inherent constraint of paragraph-level replacement. The output is intended for an AI assistant, not human reading, so formatting loss is acceptable. If an exact visual copy is required, convert to `.txt` first.

### L8 — PDF output is always plain text

PDF input produces a `.redacted.txt` file, not a PDF. Layout, columns, tables, and formatting are not preserved in the output.

**Impact:** The AI receives the document's text content but not its visual structure. Multi-column layouts may extract in the wrong reading order.

**Scanned/image PDFs:** PDFs with no embedded text (e.g. scanned documents saved as images) are not supported and will produce an error. Convert to searchable PDF or extract text via OCR first.

**Mitigation:** None for layout loss — this is a fundamental constraint of PDF's format. For scanned PDFs, use an OCR tool to produce a searchable PDF or `.txt` first:

```bash
# macOS: use Automator's "Create PDF" with OCR, or a third-party OCR tool
# Linux: ocrmypdf report-scanned.pdf report-searchable.pdf
```

### L9 (was L8) — passthrough_types leaves selected entity types in the clear

When `passthrough_types` is configured or `--passthrough` is used, the listed entity types are not tokenized and appear as-is in the redacted file. This is intentional — but it means the AI assistant receives those original values.

**Impact:** The AI sees real IP addresses, domain names, URLs, phone numbers, or locations — whichever types you bypassed.

**Mitigation:** Only bypass types whose values you are comfortable sharing. Protected types (`PERSON`, `EMAIL`, `COMPANY`, `ORG`) cannot be bypassed regardless of configuration. Use `pseudoswapper config --summary` to confirm exactly what will and won't be tokenized before running a redaction.

### L10 — Masked values cannot be restored

When mask mode is active, entities processed under masking_rules (person names, payment card numbers) are permanently redacted in the output. They are not stored in the session file. Running `pseudoswapper restore` will correctly restore all tokenised entities from the same run, but masked values remain as-is (e.g. `5_J.D.`, `411111XXXXXX1111`).

**Impact:** If you need to reinstate a masked value, you must refer to the original file.

**Mitigation:** Use tokenize mode (the default) when you need full restoration capability. Use mask mode only when permanent redaction is acceptable — for example, when sharing card data for brand identification without retaining the full PAN, or when sharing name-linked data where knowing the initials is sufficient context.

---

## 8. Security notes

### The redacted file is safe to share

The redacted file contains only tokens. Even if the AI assistant's logs or outputs are intercepted, no original sensitive values are exposed. The mapping that decodes the tokens never leaves your machine.

### The token mapping is not persistent

The token-to-value mapping exists only in a private temporary directory (`/tmp/...`, mode `0700`, readable only by your OS user). It does not survive a system reboot. If you need to restore AI output after a reboot, re-run the redact command.

### The config file is sensitive

`~/.pseudoswapper_config.yaml` contains employee names, internal project names, and domain names. It is not a mapping file (it contains no tokens), but it does contain the original sensitive definitions.

- Do not commit it to a git repository
- Do not include it in any cloud backup that might sync to a third party
- Treat it with the same care as an SSH config or credentials file

### No network calls

`pseudoswapper` makes zero network calls during redact or restore. The NLP model (`en_core_web_lg`) is a local file downloaded once at install time. All processing is offline.

### Terminal session hygiene

If you `echo` a token mapping or print session details in a terminal, that output may be visible in shell history or log files. The tool itself does not print any original values — but be careful with commands you run alongside it.

---

## 9. Troubleshooting

### "command not found: pseudoswapper"

The package has not been installed, or the virtual environment where it was installed is not active.

**If you installed into a virtual environment** (following the README setup steps), activate it first:

```bash
source .venv/bin/activate
```

Run this from the project root each time you open a new terminal session before using the tool.

**If you installed into system Python** (`pip install .` without a venv), confirm the install succeeded and that your system Python's bin directory is on your `PATH`:

```bash
pip show pseudoswapper     # should print package metadata if installed
python -m pseudoswapper    # alternative way to invoke if PATH is not set up
```

**If you just downloaded the folder without installing**, run `pip install .` (or `pip install -e .` for an editable install) from the project root first.

---

### "No module named spacy" or "Can't find model 'en_core_web_lg'"

The spaCy model was not downloaded, or the wrong Python environment is active.

```bash
source .venv/bin/activate
python -m spacy download en_core_web_lg
```

The model is downloaded once and reused on every subsequent run. It is a local file — no network call is made when the tool runs.

---

### "No session found" / restore fails immediately

You are running `pseudoswapper restore` from a different directory than the one where you ran the redact command. The `.pseudoswapper_session` pointer file is written to the directory you were in when you ran `document` or `structured`.

```bash
# Navigate to the directory where you ran the redact command, then retry
cd ~/Documents/sensitive-files
pseudoswapper restore ai_output.txt
```

If you cannot find the original directory, or the session was lost after a reboot, the mapping is gone. Re-run the redact command on the original file to start a new session.

---

### Session was lost after a reboot

The token mapping lives in a system temp directory that does not survive a reboot. This is by design — it limits how long sensitive mappings sit on disk.

Re-run the redact command on the original input file. A new session and a new redacted file will be produced. The tokens in the new output will be identical in structure (e.g. `[PERSON_1]`) but the mapping will be freshly generated, so use the new redacted file with the AI rather than a previously shared one.

---

### The output file looks the same as the input — nothing was redacted

The tool ran but detected no sensitive entities. Common causes:

**Config not loaded or empty** — run `pseudoswapper config --summary` to confirm the tool is reading your config and that `company_terms` and `employees` are populated as expected.

**Employees not listed** — if the file contains names of known people, add them to `employees` in your config. NLP alone may not detect names in non-prose contexts (log lines, table headers, short strings).

**No config file found** — if `~/.pseudoswapper_config.yaml` does not exist, the tool runs with no company-specific definitions. Copy the example template:

```bash
cp pseudoswapper_config.example.yaml ~/.pseudoswapper_config.yaml
```

**Structured mode with no anchor** — if no anchor field is configured and auto-detection finds no match, fields are tokenised independently and NLP may miss many values. Set an explicit anchor with `--anchor` or in the config.

---

### Too much was redacted — common words are being replaced

spaCy may interpret common English words as person names (e.g. "Will", "May", "Mark"). Add the affected words to `exclude_terms` in your config:

```yaml
exclude_terms:
  - Will
  - May
  - Mark
```

Run `pseudoswapper config --summary` to confirm the terms are registered, then re-run the redact command.

---

### Some tokens were not restored in the AI output

The AI reformatted a token in a way the restore logic did not catch. Common cases that restore handles automatically: case changes (`[person_1]`, `[Person_1]`), markdown wrapping (`` `[PERSON_1]` ``, `**[PERSON_1]**`).

Cases that will not restore automatically: the AI expanded the token into prose (e.g. wrote "Person 1" instead of `[PERSON_1]`), or split/merged a token across lines.

Scan the restored output for any remaining `[TOKEN]` patterns — those are occurrences the AI altered beyond what fuzzy matching can recover. Replace them manually by cross-referencing the original file.

---

### "Error: unsupported file" or PDF produces an error

**Scanned / image-only PDF** — if the PDF has no embedded text (e.g. it is a scanned document saved as an image), `pseudoswapper` cannot extract text and will exit with an error. Convert the PDF to searchable text first:

```bash
# macOS: use Automator's "Create PDF" with OCR, or a third-party OCR tool
# Linux: ocrmypdf report-scanned.pdf report-searchable.pdf
```

**Unsupported extension** — only `.txt`, `.log`, `.docx`, `.pdf`, `.csv`, `.json`, and `.xlsx` are supported. For other formats, export or convert to `.txt` first.

---

### YAML parse error when running any command

Your config file contains a syntax error. Open it:

```bash
pseudoswapper config --edit
```

Common YAML mistakes:
- Indentation with tabs instead of spaces
- A string containing a colon not wrapped in quotes (e.g. `- Project: Alpha` should be `- "Project: Alpha"`)
- Missing `-` before list items under `employees` or `company_terms`

If you are unsure, validate it against the example template in `pseudoswapper_config.example.yaml`.

---

## 10. DSAR redaction

### What it does

`pseudoswapper dsar-redaction` is purpose-built for responding to Data Subject Access Requests. When a person exercises their right to see their own data, you must provide documents that contain their information while protecting the privacy of any other individuals mentioned in the same files.

`dsar-redaction` handles this in a single command:

- The **data subject's own PII** (their name, email, employee ID, phone, credit card number, or any other values you specify) is **preserved exactly as-is** in the output.
- All **other detected PII** is **permanently masked** — person names become `2_J.S.` style, card numbers are truncated to first 6 + last 4 digits.
- The command always runs in mask mode regardless of the global `pseudoswapper mode` setting — there is no accidental tokenize path.
- It accepts the same file formats as `document` and `structured`, auto-detected by extension.

### The subject config file

Each DSAR request requires a small YAML file that lists the requestor's known PII values. All fields are optional, but at least one must be present.

```yaml
# dsar_subject.yaml — one file per requestor
full_name: Jane Doe
first_name: Jane
last_name: Doe
email: jane.doe@example.com
employee_id: EMP-1042
phone: +61 400 123 456
credit_card: "4111111111111111"
```

**Field behaviour:**

| Field | Notes |
|---|---|
| `full_name` | Preserved as a full string. First and last name components are also derived and preserved independently — so "Jane" and "Doe" appearing alone in the document are also kept, unless `first_name` / `last_name` are separately specified. |
| `first_name` | Preserved as-is. Overrides the derived component from `full_name`. |
| `last_name` | Preserved as-is. Overrides the derived component from `full_name`. |
| `email` | Preserved as-is (case-insensitive match). |
| `employee_id` | Preserved as-is. |
| `phone` | Preserved as-is. |
| `credit_card` | Preserved as-is. If omitted, the subject's card number is masked like any other — add it here only if the requestor is entitled to see their own full card number in the output. |

### Setting up the subject config

**Option A — interactive setup (no file needed)**

Run `dsar-redaction` without a `--subject-config` flag. If no `dsar_subject.yaml` exists in the current directory, the tool launches a setup wizard:

```
DSAR Subject Setup
──────────────────────────────────────────
Enter the data subject's known PII values.
All fields are optional — at least one is required.

  Full Name:
  First Name:
  Last Name:
  Email Address:
  Employee ID:
  Phone Number:
  Credit Card Number:

Subject config saved: /path/to/dsar_subject.yaml
```

The file is saved to `dsar_subject.yaml` in the current directory and reused on subsequent runs.

**Option B — supply an existing file**

```bash
pseudoswapper dsar-redaction report.pdf --subject-config ~/requests/jane_doe.yaml
```

Pointing to an explicit path with `--subject-config` overrides auto-discovery and the interactive wizard entirely.

### Running a DSAR redaction

```bash
# Prose document — output: report.redacted.txt (or .docx/.pdf as appropriate)
pseudoswapper dsar-redaction report.pdf --subject-config dsar_subject.yaml
pseudoswapper dsar-redaction email_thread.docx --subject-config dsar_subject.yaml

# Structured file — auto-detected by extension
pseudoswapper dsar-redaction access_logs.csv --subject-config dsar_subject.yaml
pseudoswapper dsar-redaction employees.xlsx --subject-config dsar_subject.yaml --anchor employee_id

# No subject config argument — auto-discovers dsar_subject.yaml in CWD,
# or launches the interactive setup wizard if it doesn't exist yet
pseudoswapper dsar-redaction report.pdf

# Supply an employee roster to improve name detection coverage
pseudoswapper dsar-redaction report.pdf --subject-config dsar_subject.yaml --employees-csv ~/company_employees.csv
```

Output is written alongside the input file with a `.redacted` suffix, exactly as with `document` and `structured`.

### Reviewing the output

Before delivering the redacted file to the requestor, verify:

1. The requestor's name, email, and other configured values appear exactly as they do in the original.
2. Other people's names appear in masked form (e.g. `2_J.S.`, `3_A.J.`).
3. Other email addresses appear as tokens (e.g. `[EMAIL_1]`).
4. No full payment card numbers belonging to other individuals are visible.

### Subject config and the work directory

`dsar-redaction` respects the configured work directory for file selection (same as `document` and `structured`). The subject config file is separate and looked up in the current working directory, not the work directory — pass `--subject-config` with an explicit path if your subject YAML lives elsewhere.

### Known limitations for DSAR

**Subject values must be explicitly configured.** The tool has no way to infer which person is the requestor from the document content. If a surface form of the subject's name is not listed (e.g. a nickname, a maiden name, or an abbreviation) it will be masked rather than preserved. Include all expected surface forms in the subject config, or add `first_name` / `last_name` separately if they may appear in isolation.

**Other PII types are tokenized, not masked.** Only entity types with masking rules applied (`PERSON` and `CREDIT_CARD` by default) are permanently masked. Other types — email addresses, phone numbers, organisation names — become reversible tokens (`[EMAIL_1]`, `[ORG_1]`). If your main config has no `masking_rules`, `dsar-redaction` automatically applies defaults for `PERSON` and `CREDIT_CARD`. For other types, configure `masking_rules` in `~/.pseudoswapper_config.yaml` if permanent masking is required.

**`dsar-redaction` output cannot be restored.** Because it always runs in mask mode, the session that is created cannot be used to reinstate masked values. Keep the original source document — it is the only copy with unredacted content.

---

## 11. One-time redaction (`redact` command)

### What it does

`pseudoswapper redact` permanently sanitises files for sharing with internal teams. It differs from `document`/`structured` in three key ways:

1. **No session is written** — there is no restore path. The output file is the final artifact.
2. **Relaxed protection model** — only `CREDIT_CARD` is unconditionally redacted. Names, email addresses, company names, and org names are redacted by default but can be made visible with `--passthrough`.
3. **Extended entity detection** — three additional types are detected in redact mode: `AMOUNT`, `IBAN_CODE`, and `MAC_ADDRESS`.

### Supported file types

| Extension | Output | Notes |
|---|---|---|
| `.txt`, `.log`, and other plain text | `.redacted.txt` | |
| `.docx` | `.redacted.docx` | Paragraph-level replacement |
| `.pdf` | `.redacted.txt` | Text extracted; layout not preserved |
| `.eml` | `.redacted.txt` | Headers + body extracted |
| `.msg` | `.redacted.txt` | Outlook compound document; headers + body extracted |
| `.csv` | `.redacted.csv` | |
| `.json` | `.redacted.json` | |
| `.xlsx` / `.xls` | `.redacted.xlsx` | All sheets redacted; shared registry across sheets |

### Additional entity types in redact mode

| Type | Detected by | Token format | Notes |
|---|---|---|---|
| `AMOUNT` | spaCy `MONEY` NER | `[AMOUNT_1]` | Financial figures — full token only (no partial masking or bucketing) |
| `IBAN_CODE` | Presidio `IbanRecognizer` | `[IBAN_CODE_1]` | EU bank account numbers |
| `MAC_ADDRESS` | Presidio `MacAddressRecognizer` | `[MAC_ADDRESS_1]` | Network interface identifiers |

All three are bypassable via `--passthrough AMOUNT`, `--passthrough IBAN_CODE`, or `--passthrough MAC_ADDRESS`.

### Running a single-file redaction

```bash
# Prose, Word document, or PDF
pseudoswapper redact incident_report.txt
pseudoswapper redact forensic_notes.docx
pseudoswapper redact exported_log.pdf

# Email files
pseudoswapper redact phishing_sample.eml
pseudoswapper redact forwarded_email.msg

# Structured data — all sheets redacted
pseudoswapper redact affected_accounts.xlsx
pseudoswapper redact access_log.csv

# Leave names and email addresses visible for follow-up
pseudoswapper redact incident_report.txt --passthrough PERSON --passthrough EMAIL

# Use a named profile from config
pseudoswapper redact incident_report.txt --profile incident_report

# Supply an employee roster
pseudoswapper redact report.txt --employees-csv ~/company_employees.csv
```

### Relaxed protection model and `--passthrough`

In `document`/`structured`, `--passthrough` silently ignores attempts to bypass protected types (`PERSON`, `EMAIL`, `COMPANY`, `ORG`). In `redact`, those types can be passed through — they are not protected.

This is intentional: an incident report saying "[PERSON_1] needs MFA reset and [EMAIL_1] is the affected account" is useless. The security team needs the actual names and email addresses to act.

`CREDIT_CARD` remains unconditionally protected in all modes (PCI-DSS).

### Named profiles

Save passthrough configurations for repeated workflows in `~/.pseudoswapper_config.yaml`:

```yaml
redact_profiles:
  incident_report:
    passthrough: [PERSON, EMAIL, COMPANY, ORG]
  financial_review:
    passthrough: [PERSON, EMAIL]
```

```bash
pseudoswapper redact report.xlsx --profile incident_report
```

CLI `--passthrough` flags are merged with the profile. `CREDIT_CARD` is always excluded from the effective passthrough set regardless of what a profile lists.

### Batch folder mode

Supply a directory path instead of a file path to process all supported files in one pass:

```bash
# Process all supported files in a folder
pseudoswapper redact ~/incident-artifacts/

# Include files in subdirectories
pseudoswapper redact ~/incident-artifacts/ --recursive

# Combine with passthrough
pseudoswapper redact ~/incident-artifacts/ --passthrough EMAIL --passthrough PERSON
```

**What gets processed:** Files with extensions `.txt`, `.docx`, `.pdf`, `.eml`, `.msg`, `.csv`, `.json`, `.xlsx`, `.xls`. Hidden files (`.`-prefixed) and already-redacted files (`.redacted.` in name) are skipped.

**Shared entity registry:** The entire batch uses one `EntityRegistry`. If `Alice Wong` appears in `email_001.eml` and `attachment_003.docx`, both files produce the same mask. This ensures consistent anonymisation across the full artifact set.

**Progress output:**

```
Redacting files in: /Users/you/incident-artifacts
Extensions: .csv, .docx, .eml, .json, .msg, .pdf, .txt, .xlsx, .xls

  ✓ phishing_email.eml  →  phishing_email.redacted.txt
  ✓ affected_users.xlsx →  affected_users.redacted.xlsx
  ✗ corrupt_file.msg    →  error: ...

Done: 2 succeeded, 1 failed, 3 total
```

### EML and MSG email files

Both formats produce a `.redacted.txt` output containing:

1. A structured header block (From, To, Cc, Subject)
2. The email body (plain text preferred; HTML tags stripped if only HTML is available)

PII in both headers and body is detected and redacted together. Attachments are not extracted inline — save attachments separately and include them in a batch folder redaction.

### Known limitations

- **Email attachments not extracted inline** — run batch mode on a folder containing both the email file and separately-saved attachments.
- **`AMOUNT` detection is English-only** — spaCy's `MONEY` NER is trained on English-language text. Non-English monetary expressions may be missed.
- **No session = no restore** — `redact` is one-way. Keep the original file if you may need the unredacted values later.
