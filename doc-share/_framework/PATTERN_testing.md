# Pattern: Fixture-Based Testing with Redacted Real Files

## Problem it solves
A tool that reads real-world file formats (Excel exports, CSV dumps) needs tests that exercise the actual parsing and logic — not mocked abstractions. But real files contain sensitive data and can't be committed. Redacted samples preserve the format while removing PII.

## Shape

```
tests/
├── __init__.py
├── fixtures/                    # redacted sample files used as test inputs
│   ├── sample_hr.xlsx
│   ├── sample_idp.csv
│   └── sample_export.csv
├── test_<module>.py             # one test file per source module
└── conftest.py                  # shared fixtures (tmp_path helpers, config builders)
```

## Key decisions from access-review

### Redacted fixtures, not generated data
Test fixtures are real exports with names/emails replaced by fake-but-realistic values. This validates that the tool handles the actual column layouts, encodings, and edge cases that come from real systems — not a clean invented schema.

### Pure logic is separated from I/O
Normalisation, classification, and matching functions live in modules with no file I/O (`normalize.py`). These are tested with plain Python objects — no file reads. File-reading code (`sot.py`, `audit.py`) is tested with fixture paths.

This separation means the most-tested functions are the cheapest to test.

### No mocking of file reads
If a function reads an Excel file, the test passes a real `.xlsx` fixture path. Mocking `openpyxl` or `pandas` would test the mock, not the integration.

### Tests are run as a module
```bash
python3 -m pytest
```
Not `pytest` directly, to ensure the installed package is on the path consistently.

### Test structure mirrors source structure
`test_sot.py` tests `sot.py`, `test_audit.py` tests `audit.py`, etc. One-to-one mapping makes it obvious where to add a test for a new function.

### Config is built inline, not loaded from files
Tests that need config dicts build minimal dicts directly rather than loading `workspace.yaml`. This avoids coupling tests to file presence and makes each test self-describing.

```python
def make_ws():
    return {
        "company": {"name": "Acme", "domains": ["acme.com"], ...},
        "bamboohr": {"email_header": "Work Email", ...},
        ...
    }
```

## What to adapt per project
- Fixture file formats and names
- Which modules are "pure logic" vs "I/O"
- Minimum config dict shape

## What to keep as-is
- Real redacted files as fixtures (not generated schemas)
- No mocking of file I/O
- Inline config dicts in tests
- `python3 -m pytest` as the test runner command
- Test file names mirror source file names
