# Security Policy

## Reporting a Vulnerability

If you find a security issue in `pseudoswapper`, please **do not open a public GitHub issue**. Public disclosure before a fix is available could put users at risk.

Instead, email: **imauchi.sd@gmail.com**

Include:
- A description of the issue and its potential impact
- Steps to reproduce it
- Any suggested fix if you have one

You can expect an acknowledgement within **5 business days** and a resolution or status update within **30 days**. This is a solo-maintained project — timelines may vary for complex issues, but I will keep you informed.

---

## Scope

Given that `pseudoswapper` is a locally-run CLI tool with no server-side components and no network calls, the attack surface is narrow. Issues most relevant to this project:

- **Session file exposure** — the token mapping temp directory or `.pseudoswapper_session` pointer leaking sensitive data beyond the current OS user
- **Config file handling** — unintended reads, writes, or exposure of `~/.pseudoswapper_config.yaml`
- **Output file permissions** — redacted output files written with overly permissive modes
- **Path traversal** — maliciously crafted input filenames escaping expected directories
- **Dependency vulnerabilities** — known CVEs in pinned dependencies (presidio, spaCy, pdfplumber, etc.)

## Out of Scope

- Issues that require physical access to the user's machine
- Attacks that require the user to have already run arbitrary code
- NLP detection misses or false positives — these are documented limitations, not security vulnerabilities
