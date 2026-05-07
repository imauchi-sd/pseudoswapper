# DESIGN.md — Design Reference: Local Data Redaction Tool

This document captures the design decisions and rationale from the initial scoping discussion.
It serves as a reference for implementation decisions and for the USER_GUIDE.md content.

---

## Problem Statement

Employees using personal AI subscriptions for work tasks need to share files containing sensitive
company data (names, emails, domains, internal identifiers) with those AI assistants. Manually
redacting and then re-applying values is error-prone and time-consuming.

The tool must:
- Make redaction and restoration fast and low-friction
- Keep all sensitive data and mappings strictly local (never leave the user's machine)
- Maintain the relational integrity of the data so the AI receives coherent, usable content
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
protected types (`PERSON`, `EMAIL`, `COMPANY`, `ORG`) is always tokenised and cannot be bypassed
by any config or flag.

**Rationale:** Not all detectable values are equally sensitive. IP addresses in a security incident
log carry analytical value — the AI needs to reason about specific hosts. Suppressing them removes
useful information without adding privacy protection, since IPs of internal systems are not
personally identifying in most contexts. At the same time, allowing users to bypass names or emails
would undermine the tool's core privacy guarantee, so those types are hardcoded as non-bypassable.

**Implementation:** `PROTECTED_TYPES` is a `frozenset` in `tokenizer.py`. When a `Tokenizer` is
constructed with a `passthrough_types` set, any protected type listed there is silently dropped.
`Tokenizer.assign()` skips entities whose type is in the effective passthrough set. Force-tokenized
fields (structured mode's `force_fields`) always tokenize unconditionally — they are unaffected by
passthrough, since the user explicitly opted in to tokenising that column.

**Merge semantics:** CLI `--passthrough` flags are unioned with the YAML `passthrough_types` list.
Neither overrides the other. The final set is computed in `cli._resolve_passthrough()` and passed
down to the mode orchestrators.

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
| L7 | No binary file redaction in v1 (no .docx, .pdf) | Users must convert to .txt first | Document conversion step in guide |
| L8 | Opaque ID anchors restore to the ID, not the person name | `[PERSON_1]` → `"E001"` rather than `"John Doe"` in restored AI output | Use `full_name` as anchor when human-readable restoration is required |
| L9 | `passthrough_types` intentionally leaves selected entity types unreplaced | The AI assistant receives original values for bypassed types | Protected types (PERSON, EMAIL, COMPANY, ORG) cannot be bypassed; user is responsible for assessing sensitivity of bypassed types |

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
   - Decision guide: "if your file is a CSV, spreadsheet, or log file → Structured; otherwise → Document"

3. **Setting up the YAML config**
   - Where the file lives
   - How to add company terms
   - How to add known employees
   - How to set anchor field for structured mode
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
