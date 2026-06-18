from __future__ import annotations

from pathlib import Path

from pseudoswapper.config import ConfigError, load_config
from pseudoswapper.detector import Detector
from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.replacer import replace
from pseudoswapper.session import create_session, session_exists, save_session
from pseudoswapper.tokenizer import Tokenizer


def _pre_register_employees(config: dict, tokenizer: Tokenizer) -> None:
    for emp in config.get("employees", []):
        full_name = (emp.get("full_name") or "").strip()
        if not full_name:
            continue
        token = tokenizer._assign_person(full_name)
        username = (emp.get("username") or "").strip()
        if username:
            tokenizer._registry.register_alias(username, token)


def _output_path(input_path: Path, force_suffix: str | None = None) -> Path:
    suffix = force_suffix if force_suffix else input_path.suffix
    return input_path.parent / f"{input_path.stem}.redacted{suffix}"


def _build_pipeline(config: dict, passthrough_types: set[str] | None, masking_rules: dict | None = None):
    registry = EntityRegistry()
    tokenizer = Tokenizer(registry, passthrough_types=passthrough_types, masking_rules=masking_rules or {})
    detector = Detector(config)
    _pre_register_employees(config, tokenizer)
    return registry, tokenizer, detector


def _save(registry: EntityRegistry, cwd: Path) -> None:
    if session_exists(cwd):
        save_session(registry, cwd)
    else:
        create_session(registry, cwd)


def _redact_plain(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None) -> Path:
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules)
    text = file.read_text(encoding="utf-8", errors="replace")
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file)
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd)
    return out


def _redact_docx(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None) -> Path:
    from pseudoswapper.extractors.docx import apply_token_map, extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    out = _output_path(file)
    apply_token_map(file, token_map, out)
    _save(registry, cwd)
    return out


def _redact_pdf(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None) -> Path:
    from pseudoswapper.extractors.pdf import extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file, force_suffix=".txt")
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd)
    return out


def redact_document(
    file: Path,
    config: dict,
    cwd: Path,
    passthrough_types: set[str] | None = None,
    masking_rules: dict | None = None,
) -> Path:
    """Run document mode: detect, tokenize/mask, replace, write output, save session."""
    suffix = file.suffix.lower()
    if suffix == ".docx":
        return _redact_docx(file, config, cwd, passthrough_types, masking_rules)
    if suffix == ".pdf":
        return _redact_pdf(file, config, cwd, passthrough_types, masking_rules)
    return _redact_plain(file, config, cwd, passthrough_types, masking_rules)
