from __future__ import annotations

from pathlib import Path
from typing import Callable

_STRUCTURED_EXTENSIONS = {".csv", ".json", ".xlsx", ".xls"}
_DEFAULT_MASKING_RULES: dict = {"PERSON": {}, "CREDIT_CARD": {}}

SUPPORTED_BATCH_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".docx", ".pdf", ".eml", ".msg",
    ".csv", ".json", ".xlsx", ".xls",
})


def redact_file(
    file: Path,
    config: dict,
    passthrough_types: set[str] | None = None,
    on_row: Callable[[int, int], None] | None = None,
    _registry=None,
    _tokenizer=None,
) -> Path:
    """One-time permanent redaction — always mask mode, no session written."""
    masking_rules = config.get("masking_rules") or _DEFAULT_MASKING_RULES
    suffix = file.suffix.lower()

    if suffix in _STRUCTURED_EXTENSIONS:
        from pseudoswapper.modes.structured import redact_structured
        return redact_structured(
            file, config, file.parent,
            passthrough_types=passthrough_types,
            masking_rules=masking_rules,
            write_session=False,
            strict_protection=False,
            redact_mode=True,
            on_row=on_row,
            _registry=_registry,
            _tokenizer=_tokenizer,
        )

    from pseudoswapper.modes.document import redact_document
    return redact_document(
        file, config, file.parent,
        passthrough_types=passthrough_types,
        masking_rules=masking_rules,
        write_session=False,
        strict_protection=False,
        redact_mode=True,
        _registry=_registry,
        _tokenizer=_tokenizer,
    )


def redact_batch(
    directory: Path,
    config: dict,
    passthrough_types: set[str] | None = None,
    recursive: bool = False,
    on_file: Callable[[Path, bool, str], None] | None = None,
) -> dict:
    """Redact all supported files in *directory* using a shared EntityRegistry.

    *on_file* is called after each file: on_file(file_path, success, message).
    Returns a summary dict: {processed, succeeded, failed, results}.
    """
    from pseudoswapper.entity_registry import EntityRegistry
    from pseudoswapper.modes.document import _pre_register_employees
    from pseudoswapper.tokenizer import Tokenizer

    masking_rules = config.get("masking_rules") or _DEFAULT_MASKING_RULES

    # Discover eligible files
    glob_pattern = "**/*" if recursive else "*"
    candidates = sorted(
        f for f in directory.glob(glob_pattern)
        if f.is_file()
        and not f.name.startswith(".")
        and ".redacted" not in f.name
        and f.suffix.lower() in SUPPORTED_BATCH_EXTENSIONS
    )

    if not candidates:
        return {"processed": 0, "succeeded": 0, "failed": 0, "results": []}

    # Build one shared pipeline for the entire batch
    registry = EntityRegistry()
    tokenizer = Tokenizer(
        registry,
        passthrough_types=passthrough_types,
        masking_rules=masking_rules,
        strict_protection=False,
    )
    _pre_register_employees(config, tokenizer)

    results: list[dict] = []
    for file in candidates:
        try:
            out = redact_file(
                file, config,
                passthrough_types=passthrough_types,
                _registry=registry,
                _tokenizer=tokenizer,
            )
            results.append({"file": file, "output": out, "error": None})
            if on_file:
                on_file(file, True, str(out.name))
        except Exception as exc:
            results.append({"file": file, "output": None, "error": str(exc)})
            if on_file:
                on_file(file, False, str(exc))

    succeeded = sum(1 for r in results if r["error"] is None)
    return {
        "processed": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }
