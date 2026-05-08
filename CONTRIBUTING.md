# Contributing to pseudoswapper

Thank you for your interest in contributing. This document covers how to contribute, and the safeguards that both contributors and the maintainer must follow to ensure no sensitive data is ever accidentally committed.

---

## Getting started

```bash
git clone https://github.com/imauchi-sd/pseudoswapper
cd pseudoswapper
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_lg
```

Run the test suite to confirm everything is working:

```bash
python -m pytest
```

---

## Submitting changes

1. Fork the repository and create a branch from `main`
2. Make your changes and ensure all tests pass
3. If you are adding a feature, add tests for it
4. Open a pull request with a clear description of what changed and why

For significant changes, open an issue first to discuss the approach before investing time in an implementation.

---

## Data safety — what must never be committed

This project handles sensitive data by design. The following rules apply to **everyone** — contributors and the maintainer alike.

### Test fixtures must use fictional data only

The files in `tests/fixtures/` are committed to the public repository. They must contain only clearly fictional, non-identifiable data. The existing fixtures use:

- **Company:** Acme Corporation / acme.com
- **People:** John Doe, Jane Smith, Alice Chen
- **Emails:** john.doe@acme.com, j.smith@acme.com
- **IPs/domains:** 192.168.10.42, ftp.acme.com

Follow this pattern. Never use:
- Real employee names, even anonymised-looking ones
- Real company names, domains, or project names
- Real email addresses, phone numbers, or IP addresses belonging to actual systems
- Data copied or derived from an actual work file

If a new fixture is needed, invent the data from scratch.

### Never commit output files

Files produced by running the tool — `*.redacted.*` and `*.restored.*` — are excluded by `.gitignore`. This is a safeguard, not a guarantee: double-check before staging if you have run the tool inside the project directory.

### Never commit a real config file

`~/.pseudoswapper_config.yaml` lives in your home directory and will not be picked up by git. However, if you ever create a local config inside the project directory (e.g. for testing), name it `pseudoswapper_config.yaml` or `pseudoswapper_config.local.yaml` — both are excluded by `.gitignore`.

### Never commit the session pointer

`.pseudoswapper_session` is excluded by `.gitignore`. It contains only a path, not sensitive values, but committing it would be confusing and is unnecessary.

---

## Pre-commit checklist

Before every `git commit`, run through this list:

- [ ] `git diff --staged` — scan the diff for any real names, email addresses, domains, or internal identifiers that do not belong in the public repo
- [ ] No `*.redacted.*` or `*.restored.*` files are staged
- [ ] No `pseudoswapper_config.yaml` or similar config file is staged
- [ ] Test fixtures contain only fictional data
- [ ] `python -m pytest` passes

---

## Reporting security issues

Please do not open a public issue for security vulnerabilities. See [`SECURITY.md`](SECURITY.md) for the responsible disclosure process.
