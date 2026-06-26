# DESIGN.md — Design Reference: Local Data Redaction Tool

This document captures the design decisions and rationale from the initial scoping discussion.
It serves as a reference for implementation decisions and for the USER_GUIDE.md content.

---

## Problem Statement

Employees need to share files containing sensitive company data (names, emails, domains, internal
identifiers) with AI assistants, online services, or other untrusted or public tools for analysis,
summarisation, or refactoring. Manually redacting and then re-applying values is error-prone and
time-consuming.

The tool is designed for temporary, one-off use — each redact → restore cycle is self-contained.
Unlike persistent anonymisation approaches that require managing encryption keys, pseudoswapper
holds the mapping only for the duration of a session and deletes it automatically after restore.

The tool must:
- Make redaction and restoration fast and low-friction
- Keep all sensitive data and mappings strictly local (never leave the user's machine)
- Maintain the relational integrity of the data so the recipient tool receives coherent, usable content
- Be simple enough that non-technical users can operate it with a short guide

---

## Key Design Decisions

### Decision 1: Session-scoped maps, no persistence

**Decision:** Token-to-original mappings exist in memory only and are never written to any
user-visible, persistent file.

**Rationale:** The mapping file would itself be sensitive data — it is the key that decodes
everything fed into the AI. A persistent file creates a new attack surface (theft, accidental
commit to version control, inclusion in a backup). Session scope means there is nothing to steal.

**Session persistence mechanism:** Because `pseudoswapper redact` and `pseudoswapper restore` run
as two separate processes, the session map must bridge them. This is done via:
1. A private temp directory created with `tempfile.mkdtemp()` at mode 0700 (inaccessible to
   other users), containing `session.json`.
2. A `.pseudoswapper_session` pointer file written to the CWD, holding the path to the temp dir.
   The restore process reads this pointer to locate the session.

This is not persistent storage in the threat-model sense — the temp dir is user-only, invisible
to other users, and does not survive a reboot.

**Session lifecycle:**

| Event | What happens |
|---|---|
| `pseudoswapper document` / `pseudoswapper structured` succeeds | Temp dir + `session.json` created; `.pseudoswapper_session` written to CWD |
| `pseudoswapper restore` succeeds | Temp dir and `.pseudoswapper_session` deleted automatically — no user action required |
| `pseudoswapper restore` fails | Session preserved; user told to fix the issue and retry, or run `clear-session` |
| `pseudoswapper clear-session` | Explicit escape hatch: deletes session and pointer file; use when abandoning a session |
| System reboot / OS temp cleanup | Temp dir is gone; pointer file in CWD becomes stale (safe to delete manually) |

**Normal-path experience:** Users never need to think about cleanup. A completed redact → restore
cycle leaves no artifacts. The `clear-session` command exists only as an escape hatch for
abandoned or stuck sessions.

**Future option:** If persistence is added, it must be opt-in and encrypted with a user-supplied
passphrase. Out of scope for v1.

---

### Decision 2: Two modes rather than one universal mode

**Decision:** Document mode for prose, Structured mode for tabular/structured data.

**Rationale:** A single mode trying to handle both cases would make poor trade-offs for both.
Prose benefits from NLP-driven detection. Structured data has explicit field relationships that
make NLP unnecessary and allow more reliable correlation. Separating them lets each mode make
appropriate assumptions.

**Document mode assumption:** Context is implicit, correlation between fields (e.g. name and
email) is not guaranteed to be in the same "unit". Independent tokenisation of emails is
acceptable because the AI understands prose context.

**Structured mode assumption:** Each row or JSON object is a self-contained entity bundle.
Fields within the same row can be reliably correlated to a single real-world entity.

---

### Decision 3: Person entity model as the unit of tokenisation

**Decision:** A person is registered as an entity with all their surface forms at once, not as
individual strings.

**Rationale:** If `John`, `Doe`, and `John Doe` each received independent tokens, the AI would
see three apparently unrelated entities. The entity model preserves the semantic relationship.

**Implementation:** Longest-match-first replacement ensures `John Doe` is caught and replaced
before the tool has a chance to match `John` or `Doe` independently.

---

### Decision 4: Anchor field model for structured data

**Decision:** User designates one field as the entity anchor. All other fields in the same row
are correlated to the entity registered under that anchor value.

**Rationale:** Rather than trying to infer which fields belong together (unreliable), the user
provides a single hint — the anchor — and the row structure does the rest. This is both simpler
to implement reliably and more transparent to the user.

**Critical constraint:** The anchor field must be unique per entity, stable across all rows, and
always populated. Violating any of these produces silent corruption of relational structure. This
is a user education requirement, not something the tool can fully validate.

**Why this matters for log files:** A security log with 1000 rows for the same user ID must
produce the same token for that user across all 1000 rows. The global entity registry (populated
on first encounter, reused on all subsequent encounters) is what makes this work.

---

### Decision 5: Human-readable token format

**Decision:** Tokens are formatted as `[PERSON_1]`, `[EMAIL_1]`, `[DOMAIN_1]` etc., not as
opaque UUIDs or hashes.

**Rationale:** The AI assistant needs to produce useful output referring to the tokenised
entities. `[PERSON_1] sent an email to [PERSON_2]` is interpretable. `a3f9c1d2... sent an
email to b7e4a0f1...` is not. Human-readable tokens also make it easier for the user to
verify the redacted file before sharing it.

---

### Decision 6: YAML config for definitions, never mappings

**Decision:** The YAML config file persists and contains detection definitions (company terms,
employee names, structured mode settings). It never contains token mappings.

**Rationale:** Config needs to persist so users don't redefine company-specific terms every
session. But mappings must not persist (see Decision 1). These are separate concerns.

**Security note:** The config file itself contains some sensitive data (employee names, internal
project names). Users should treat it accordingly — don't commit it to version control, don't
share it.

---

### Decision 7: Two-tier passthrough — protected types vs. bypassable types

**Decision:** Users can opt out of tokenising certain entity types (`IP`, `DOMAIN`, `URL`, `PHONE`,
`LOC`) via `passthrough_types` in config or `--passthrough` on the CLI. A hardcoded set of
protected types (`PERSON`, `EMAIL`, `COMPANY`, `ORG`, `CREDIT_CARD`) is always tokenised or masked and cannot be bypassed
by any config or flag.

**Rationale:** Not all detectable values are equally sensitive. IP addresses in a security incident
log carry analytical value — the AI needs to reason about specific hosts. Suppressing them removes
useful information without adding privacy protection, since IPs of internal systems are not
personally identifying in most contexts. At the same time, allowing users to bypass names or emails
would undermine the tool's core privacy guarantee, so those types are hardcoded as non-bypassable.

**Implementation:** `PROTECTED_TYPES` is a `frozenset` in `tokenizer.py` containing `PERSON`, `EMAIL`, `COMPANY`, `ORG`, and `CREDIT_CARD`. When a `Tokenizer` is
constructed with a `passthrough_types` set, any protected type listed there is silently dropped.
`Tokenizer.assign()` skips entities whose type is in the effective passthrough set. Force-tokenized
fields (structured mode's `force_fields`) always tokenize unconditionally — they are unaffected by
passthrough, since the user explicitly opted in to tokenising that column.

**Merge semantics:** CLI `--passthrough` flags are unioned with the YAML `passthrough_types` list.
Neither overrides the other. The final set is computed in `cli._resolve_passthrough()` and passed
down to the mode orchestrators.

---

### Decision 8: Masking as a permanent alternative to reversible tokenisation

**Decision:** Introduce a `masking_rules` config block and a `mode` preference that allow specific entity types to be permanently redacted rather than replaced with reversible tokens.

**Rationale:** Some use cases don't require full restoration. A user sharing payment card data to ask the AI to identify the card brand needs the first 6 digits (the IIN/BIN) — but not the full PAN stored anywhere. A user producing a report for a compliance audit may prefer to share initials rather than full names, knowing they will never ask the AI's output to be reinstated to the original. For these cases, permanent redaction is simpler and safer than the tokenise → share → restore cycle.

**Why not just "don't restore"?** A user could already achieve non-restoration by simply not running `pseudoswapper restore`. But tokenised output still contains structured, decodable tokens (`[PERSON_1]`) that invite accidental or deliberate reversal. Masked output (`5_J.D.`, `411111XXXXXX1111`) has no decoding path because the mapping was never stored.

**Person name masking format (`{n}_{initials}`):**
The format is designed to satisfy three constraints simultaneously:
1. **Uniqueness:** Two people with the same initials (e.g. Jane Doe and John Doe) are distinguished by their sequence number (`1_J.D.` vs `2_J.D.`).
2. **NER safety:** The format `5_J.D.` is not recognised as a human name by spaCy, so multi-pass documents do not produce cascading re-detections.
3. **Traceability:** A reader can tell that all occurrences of `5_J.D.` refer to the same person without knowing who that person is.

The sequence number `n` is drawn from the same `EntityRegistry` counter used for tokens, so masks and tokens within the same session never share a counter value.

**PAN masking format (first N + last N digits):**
Follows PCI-DSS guidance for truncated PANs. The default is keep_first=6, keep_last=4 — retaining the IIN/BIN (brand/issuer identification) and the last 4 (common for user-facing display). Non-digit characters (spaces, dashes) are stripped before masking; the output is a clean digit string.

**Separation of definition from activation:**
The `masking_rules` config block defines *how* to mask (format, digit counts, fill character). Whether masking is active is controlled separately by the `mode` preference or the `--mask`/`--no-mask` per-run flag. This allows users to define masking rules once in config and toggle them on/off without editing the config file.

**Non-restorability is enforced at the registry level:**
Masked values are stored in `EntityRegistry._forward` (so repeated occurrences of the same value produce the same mask) but NOT in `EntityRegistry._reverse` (so `pseudoswapper restore` cannot reverse them). The restore logic searches for `[TOKEN]` patterns — masked values (`5_J.D.`, `411111XXXXXX1111`) do not match that pattern and are left untouched even if restore is run.

---

### Decision 9: `redact` command — one-time permanent redaction without a session

**Decision:** Introduce a dedicated `pseudoswapper redact <file>` command that always runs in mask
mode and never writes a session. The output file is the artifact — there is no restore path.

**Rationale:** The `document` and `structured` commands were designed around the tokenise → share →
restore cycle. Post-incident analysis produces a different workflow: an exposure report needs to be
permanently sanitised before being shared with internal teams who have no need (or clearance) to see
the original values. Creating a session for this use case is actively misleading — it implies
restoration is possible when it is not the intent.

The DSAR command is also session-free and mask-only, but requires a data subject config and is
scoped to a specific compliance use case. `redact` is the general-purpose equivalent: no subject, no
config overhead, one command.

**Relationship to existing commands:**

| Command | Mode | Session | Subject config | Protection model |
|---|---|---|---|---|
| `document` / `structured` | tokenize (default) or mask | yes | no | PERSON, EMAIL, COMPANY, ORG, CREDIT_CARD always protected |
| `dsar-redaction` | mask always | no | yes (required) | PERSON, EMAIL, COMPANY, ORG, CREDIT_CARD always protected |
| `redact` | mask always | no | no | CREDIT_CARD only unconditionally protected (see Decision 10) |

---

### Decision 10: Relaxed protection model in `redact`

**Decision:** In the `redact` command, only `CREDIT_CARD` is unconditionally redacted. All other
types — including `PERSON`, `EMAIL`, `COMPANY`, and `ORG` — are redacted by default but can be
passthroughed via `--passthrough` or a named profile.

**Rationale:** The strict protection model in `document`/`structured` exists to prevent accidental
exposure when handing data to an external AI. For internal reports the threat model is different:
the reader is a trusted colleague who needs actionable information. An incident report that says
"[PERSON_1] requires MFA reset and [EMAIL_1] is the affected account" is useless — the security
team needs to know the actual email and name to take action.

`CREDIT_CARD` remains unconditionally protected in all modes because PCI-DSS compliance applies
regardless of audience.

**`--passthrough` scope extension:** In `document`/`structured`, `--passthrough` silently drops any
attempt to bypass a protected type. In `redact`, the same flag accepts any type including those that
are protected in other commands. This is an intentional divergence — the commands serve different
purposes and the protection guarantees are mode-specific, not global.

**Named redaction profiles:** The `pseudoswapper_config.yaml` gains a `redact_profiles` block
allowing users to save named passthrough configurations for repeated workflows:

```yaml
redact_profiles:
  incident_report:
    passthrough: [PERSON, EMAIL, COMPANY, ORG]
```

Used as: `pseudoswapper redact report.xlsx --profile incident_report`

Profiles are resolved before CLI `--passthrough` flags; both are merged (union semantics, same as
the existing `--passthrough` + `passthrough_types` merge). `CREDIT_CARD` is always removed from the
effective passthrough set regardless of what is listed in a profile.

---

### Decision 11: Multi-sheet XLSX support

**Decision:** When `redact` (and the `structured` command) processes an XLSX file, all sheets are
read, redacted, and written back to the output workbook. A single `EntityRegistry` is shared across
all sheets for the entire workbook.

**Rationale:** The current implementation reads only the first sheet (`pd.read_excel` default). An
exposure report with a Summary sheet, a Raw Events sheet, and an Affected Accounts sheet would
silently lose all but the first. This is a data loss bug.

**Why a shared registry matters:** The same person's name may appear in multiple sheets. If each
sheet received an independent registry, `Alice Wong` in Sheet 1 might become `1_A.W.` while `Alice
Wong` in Sheet 3 becomes `2_A.W.` — implying two different people. A shared registry guarantees
consistent masking across the entire workbook.

**Implementation approach:** `pd.ExcelFile` to read all sheet names, then `pd.read_excel` per
sheet. `pd.ExcelWriter` to write all sheets back. Anchor field resolution runs independently per
sheet (each sheet may have a different column layout). Progress reporting counts total rows across
all sheets.

**Scope:** Multi-sheet support applies to `redact` and is also retrofitted to the `structured`
command as a fix. The existing single-sheet behaviour was a silent limitation, not a design
decision.

---

### Decision 12: New entity types scoped to `redact`

**Decision:** Three new entity types are introduced and available initially in `redact` only. All
three are bypassable (not protected).

| Type | Detection source | Token format | Rationale |
|---|---|---|---|
| `AMOUNT` | spaCy `MONEY` entity (already loaded model) | `[AMOUNT_1]` | Financial figures (salary, payroll) — magnitude alone is sensitive, so partial masking and range bucketing were rejected in favour of full token replacement |
| `IBAN_CODE` | Presidio `IbanRecognizer` (built-in) | `[IBAN_CODE_1]` | EU-based org; IBAN is the standard bank account format; US_BANK_NUMBER not required |
| `MAC_ADDRESS` | Presidio `MacAddressRecognizer` (built-in) | `[MAC_ADDRESS_1]` | Network forensics artifact common in incident response analysis |

**Why bypassable and not protected:** Unlike names or emails, these types have contexts where their
presence in output is analytically necessary (e.g. a network analyst needs MAC addresses visible in
a forensic report). Making them bypassable follows the same rationale as `IP`, `DOMAIN`, and `URL`.

**Why `AMOUNT` uses full token:** Partial masking (`$XX,XXX`) preserves magnitude. Range bucketing
(`[$40k–$60k]`) preserves order of magnitude. In payroll or executive compensation contexts, even
approximate figures are sensitive. Full token replacement (`[AMOUNT_1]`) reveals nothing about the
value.

**Scope note:** These types are not added to the existing `document` and `structured` commands in
this phase to avoid introducing detection noise in the tokenise → restore workflow. They can be
promoted to the main detector once validated.

---

### Decision 13: Email file support (EML and MSG)

**Decision:** `redact` accepts `.eml` and `.msg` files. Both are routed through the document
pipeline and produce a `.redacted.txt` output.

**EML (RFC 2822):** Parsed with Python's stdlib `email` module (no new dependency). Text extraction
prefers the `text/plain` MIME part; falls back to stripping HTML tags from `text/html` if no plain
part exists. Metadata fields (From, To, Subject, Date) are extracted as a structured header block
and prepended to the body before detection — this ensures email addresses and names in headers are
also redacted.

**MSG (Outlook compound document):** Parsed with `extract-msg` (pure Python, MIT licensed). Same
extraction logic as EML after parsing: sender, recipients, subject, body. MSG is the native Outlook
format; it is more common than EML in enterprise environments where incident artifacts come from
Exchange exports.

**Output format:** Both formats produce `.redacted.txt`. Reconstructing a valid EML or MSG with
redacted content would require rebuilding MIME structure, re-encoding, and preserving all headers —
complexity with no practical benefit since the output is consumed by humans reviewing the redaction,
not re-sent as email.

**Attachments:** Attachment extraction is deferred. Attachments are treated as separate files
handled by batch mode (Decision 14) rather than extracted inline. This keeps the single-file
extractor simple and avoids decisions about how to name and route extracted attachment files.

---

### Decision 14: Batch mode — folder processing

**Decision:** `pseudoswapper redact` accepts a directory path in addition to a file path. When a
directory is supplied, all supported files in that directory are processed in sequence using the
same `redact` pipeline. A single `EntityRegistry` is shared across the entire batch.

**Rationale:** Post-incident analysis involves a folder of artifacts — emails, attachments,
exported logs. Running `pseudoswapper redact` once per file is feasible but friction-heavy. A
folder target removes that friction without requiring a new command.

**Shared registry across the batch:** Same rationale as multi-sheet XLSX (Decision 11). If `Alice
Wong` appears in `email_001.eml` and `attachment_003.docx`, both should produce the same mask. The
shared registry is initialised once at batch start and passed to every file's pipeline.

**Supported file discovery:** Files in the target directory are filtered to supported extensions
only (`.txt`, `.docx`, `.pdf`, `.csv`, `.json`, `.xlsx`, `.eml`, `.msg`). Subdirectories are not
recursed by default; a `--recursive` flag enables recursion.

**Progress reporting:** Per-file progress line (filename, status) rather than a single aggregate
bar, so the user can see which file is being processed. A summary line at the end shows total files
processed and any errors.

**No session written:** Consistent with single-file `redact` behaviour. The batch produces output
files only; there is no restore path.

---

## Email Handling: The Hard Problem

Email addresses are a special case because they often encode personal information (first name,
last name, or both) in a non-standardised way. Three approaches were considered:

**Option A — Independent tokens (chosen for Document mode)**
`john.doe@acme.com` → `[EMAIL_1]`. No attempt to correlate with person tokens. Simple and
reliable. Loses name-email relationship. Acceptable for prose where context provides meaning.

**Option B — Pattern inference**
Attempt to match `firstname.lastname`, `f.lastname` etc. in the email local part against known
persons. Best-effort, not guaranteed. Used as a secondary corroboration signal in Structured mode.

**Option C — Explicit YAML mapping**
User maps specific emails to persons in config. Reliable but requires manual maintenance.
Supported via the `employees` list in YAML config.

**Structured mode** uses same-row correlation as the primary mechanism (more reliable than
pattern inference) with Option B as a secondary signal.

---

## Limitations Register

This is the authoritative list of known limitations to carry into USER_GUIDE.md.

| # | Limitation | Impact | Mitigation |
|---|---|---|---|
| L1 | spaCy NER misses names in non-prose (tables, headers, logs) | Unredacted names in output | Add known employees to YAML config |
| L2 | Email-to-name inference imperfect in Document mode | Email and person tokens not linked | Use Structured mode for correlated data |
| L3 | Composite identity (two fields needed to ID one person) not supported | Two employees with same ID in different tenants collapse to one token | Out of scope v1; use YAML to pre-register |
| L4 | Tool cannot validate anchor field correctness | Silently wrong relational structure if anchor is non-unique or unstable | User education; documented in guide |
| L5 | AI may reformat tokens in output | Restoration regex fails to match | Fuzzy/case-insensitive restore matching |
| L6 | NER false positives (common words as names) | Over-redaction | Add `exclude_terms` to YAML config |
| L7 | DOCX intra-paragraph formatting loss | Bold/italic on individual words within a replaced paragraph is lost; paragraph-level style is preserved | Intentional trade-off — output is for AI consumption, not human reading |
| L8 | PDF output is always plain text; scanned/image PDFs unsupported | Layout and formatting lost; image-only PDFs raise UnsupportedFileError | Documented limitation; scanned PDFs require OCR pre-processing |
| L9 | Opaque ID anchors restore to the ID, not the person name | `[PERSON_1]` → `"E001"` rather than `"John Doe"` in restored AI output | Use `full_name` as anchor when human-readable restoration is required |
| L10 | `passthrough_types` intentionally leaves selected entity types unreplaced | The AI assistant receives original values for bypassed types | Protected types (PERSON, EMAIL, COMPANY, ORG) cannot be bypassed; user is responsible for assessing sensitivity of bypassed types |
| L11 | Masked values cannot be restored | `pseudoswapper restore` leaves masked values (`5_J.D.`, `411111XXXXXX1111`) as-is — they are not in the session's reverse map | Design intent; use tokenize mode when full restoration is required |
| L12 | Email attachments are not extracted inline | `.eml` and `.msg` extractors process only the email body and headers; attachments are not unpacked | Run `redact` in batch mode on the folder containing both the email file and separately-saved attachments |
| L13 | `AMOUNT` detection is English-only | The `AMOUNT` type relies on spaCy's `MONEY` NER from `en_core_web_lg`, which is trained on English-language text; non-English monetary expressions may be missed | For non-English figures, add known amounts to `company_terms` or use the `AMOUNT` passthrough and redact manually |

---

## User Guide Outline

> `USER_GUIDE.md` has been produced and covers all sections below. This outline is kept as a reference for what the guide must contain.

The USER_GUIDE.md covers:

1. **What this tool does and doesn't do**
   - Local processing guarantee
   - Session scope explanation and why it matters
   - What "relational integrity" means and why it's preserved

2. **Choosing a mode**
   - Document mode: when to use, what it handles, what it doesn't
   - Structured mode: when to use, what it handles, what it doesn't
   - DSAR redaction: compliance use case
   - Redact mode: one-time permanent redaction for incident reports and internal distribution
   - Decision guide

3. **Setting up the YAML config**
   - Where the file lives
   - How to add company terms
   - How to add known employees
   - How to set anchor field for structured mode
   - `redact_profiles` block for named passthrough configurations
   - Security note: treat this file as sensitive

4. **Anchor field selection (Structured mode)**
   - What makes a good anchor (unique, stable, always populated)
   - Why system-assigned IDs are preferred over names
   - What goes wrong if the anchor is a bad choice
   - Examples: good anchors vs bad anchors

5. **Running the tool**
   - Install steps
   - Example commands for each mode
   - What the output file looks like

6. **Restoring AI output**
   - How to use `pseudoswapper restore`
   - Session pointer file (`.pseudoswapper_session`) — what it is, why it's in the CWD
   - Auto-cleanup after successful restore: session and pointer are deleted automatically
   - If restore fails: session is preserved; retry or run `pseudoswapper clear-session`
   - `pseudoswapper clear-session`: when to use it (abandoned session, stuck state)
   - What to do if the session was lost before restore (manual replacement; no automated recovery)

7. **Known limitations**
   - Plain-language version of the limitations register above

8. **Security notes**
   - The redacted file is safe to share; the terminal session is not
   - The YAML config is sensitive; don't commit it to version control
   - The tool makes no network calls

11. **One-time redaction (`redact` command)**
    - When to use `redact` instead of `document`/`structured`
    - Relaxed protection model: only CREDIT_CARD always protected; PERSON/EMAIL etc. passthroughable
    - Supported file types: `.txt`, `.docx`, `.pdf`, `.eml`, `.msg`, `.csv`, `.json`, `.xlsx`
    - New entity types: AMOUNT, IBAN_CODE, MAC_ADDRESS — detection, token format, passthrough
    - Named redaction profiles (`redact_profiles` in config)
    - Batch folder mode: supply a directory instead of a file; shared entity registry; `--recursive` flag
    - No session written; no restore path
