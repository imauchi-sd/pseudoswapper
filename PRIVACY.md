# Privacy Policy & User Responsibilities

## Privacy Policy

### Summary

`pseudoswapper` processes all data locally on your machine. No sensitive data, no token mappings, and no file contents are ever transmitted to any external server, API, or service — not during installation, not during redaction, and not during restore.

### What the tool does with your data

| Data | Where it lives | When it is deleted |
|---|---|---|
| File contents read for scanning | In-process memory only | When the process exits |
| Token-to-value mapping | Private temp directory (`/tmp/...`, mode `0700`) | Automatically after a successful restore, or on `clear-session` |
| Redacted output file | Written to the same directory as the input file | Never — you manage this file |
| Config file (`~/.pseudoswapper_config.yaml`) | Your home directory | Never — you manage this file |
| Work directory preference (`~/.pseudoswapper_prefs.yaml`) | Your home directory | On `workdir --clear` or manual deletion |

### No network calls

`pseudoswapper` makes **zero network calls** at any point. This includes:

- **Redaction** — fully offline. No data leaves your machine.
- **Restoration** — fully offline. No data leaves your machine.
- **NLP detection** — uses a local spaCy model (`en_core_web_lg`) downloaded once at install time. No inference API is called.
- **No telemetry** — no usage analytics, crash reports, or diagnostic data are collected or transmitted.

The only network activity associated with this tool is the one-time `pip install` and `spacy download` during setup, which downloads the tool's code and model files from PyPI and the spaCy CDN respectively. Once installed, the tool is entirely air-gapped.

### The token mapping never leaves your machine

The mapping that links tokens (e.g. `[PERSON_1]`) back to original values is the most sensitive artefact produced by this tool. It is:

- Stored in a private temporary directory created with `tempfile.mkdtemp()` (mode `0700` — inaccessible to other OS users on the same machine)
- Never written to a user-visible persistent file
- Deleted automatically after a successful restore
- Not recoverable after a system reboot (temp directories do not survive reboots)

### The config file

`~/.pseudoswapper_config.yaml` contains definitions you have explicitly written — employee names, internal project names, domain names — not mappings produced by a redaction session. It is:

- Never read by any external service
- Never included in any output file
- Entirely under your control

Treat it as sensitive: do not commit it to version control, do not include it in cloud backups that sync to third parties, and do not share it alongside redacted files.

---

## User Responsibilities & Disclaimers

### Detection is not guaranteed to be complete

`pseudoswapper` uses a best-effort combination of exact-match config, regex patterns, and NLP (spaCy named entity recognition). **It does not guarantee 100% detection coverage.** Sensitive values may be missed, particularly in:

- Non-prose contexts (log lines, table headers, short strings without surrounding context)
- Non-Western names or names formatted as "Last, First"
- Email addresses with non-standard local-part formats
- Entities not listed in your config and not detected by NLP

**You are responsible for verifying the redacted output before sharing it.** Open the `.redacted.*` file and confirm that no original sensitive values remain visible. Do not assume the tool has caught everything.

### Config quality directly affects output quality

The tool's detection is only as good as your configuration. Misconfigured or incomplete settings are a common source of missed redactions:

- If `employees` or `employees_csv` is incomplete, known individuals may be missed by NLP
- If `anchor_field` is not unique and stable, entities in structured mode will be incorrectly correlated or collapsed
- If `company_terms` does not include all variants of a name (e.g. "Acme Corp" vs "Acme Corporation" vs "ACME"), some occurrences will be missed
- If `correlated_fields` omits a sensitive column, that column's values will not be associated with the anchor entity

Run `pseudoswapper config --summary` before each session to confirm that your config covers the entities you intend to protect.

### passthrough_types is a deliberate privacy trade-off you own

If you configure `passthrough_types` (e.g. to leave IP addresses visible in a security log), those values will appear unredacted in the output file and will be visible to any AI assistant or person you share the file with. The tool will not warn you at share time.

Only bypass entity types whose exposure you have consciously assessed as acceptable for your specific context. You are responsible for that judgement.

### The tool does not provide legal compliance

`pseudoswapper` is a practical aid for reducing unnecessary exposure of sensitive information when using AI tools. It is **not** a certified anonymisation or pseudonymisation solution under any regulatory framework (GDPR, HIPAA, CCPA, or similar). It does not:

- Guarantee re-identification risk reduction to any defined standard
- Provide audit trails
- Cover all data types that may be considered personally identifiable under applicable law

If you are processing data subject to legal compliance requirements, consult appropriate legal and technical counsel. Do not rely solely on this tool to meet those obligations.

### Restoration depends on session continuity

If the session is lost (system reboot, accidental `clear-session`, moving to a different working directory), tokens in the AI's output cannot be automatically reversed. Re-run the redact command on the original file to start a new session.

### The AI assistant receives the redacted file — not original values

Once you share a redacted file with an AI assistant, the assistant's handling of that file is governed by that assistant's own privacy policy, not by `pseudoswapper`. The redacted content should contain no original sensitive values — but you are responsible for verifying this before sharing.

---

*This policy applies to `pseudoswapper` as a locally-run CLI tool. It does not apply to any hosted service, cloud deployment, or modified fork.*
