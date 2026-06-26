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


def _build_pipeline(
    config: dict,
    passthrough_types: set[str] | None,
    masking_rules: dict | None = None,
    subject_values: frozenset[str] | None = None,
    strict_protection: bool = True,
    redact_mode: bool = False,
    _registry=None,   # NEW: pass existing registry to reuse
    _tokenizer=None,  # NEW: pass existing tokenizer to reuse
):
    registry = _registry if _registry is not None else EntityRegistry()
    if _tokenizer is not None:
        tokenizer = _tokenizer
    else:
        tokenizer = Tokenizer(
            registry,
            passthrough_types=passthrough_types,
            masking_rules=masking_rules or {},
            subject_values=subject_values,
            strict_protection=strict_protection,
        )
    detector = Detector(config, redact_mode=redact_mode)
    if _registry is None:  # only pre-register when building fresh
        _pre_register_employees(config, tokenizer)
    return registry, tokenizer, detector


def _save(registry: EntityRegistry, cwd: Path, write: bool = True) -> None:
    if not write:
        return
    if session_exists(cwd):
        save_session(registry, cwd)
    else:
        create_session(registry, cwd)


def _redact_plain(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None, subject_values: frozenset[str] | None = None, write_session: bool = True, strict_protection: bool = True, redact_mode: bool = False, _registry=None, _tokenizer=None) -> Path:
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules, subject_values, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    text = file.read_text(encoding="utf-8", errors="replace")
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file)
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd, write=write_session)
    return out


def _redact_docx(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None, subject_values: frozenset[str] | None = None, write_session: bool = True, strict_protection: bool = True, redact_mode: bool = False, _registry=None, _tokenizer=None) -> Path:
    from pseudoswapper.extractors.docx import apply_token_map, extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules, subject_values, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    out = _output_path(file)
    apply_token_map(file, token_map, out)
    _save(registry, cwd, write=write_session)
    return out


def _redact_pdf(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None, subject_values: frozenset[str] | None = None, write_session: bool = True, strict_protection: bool = True, redact_mode: bool = False, _registry=None, _tokenizer=None) -> Path:
    from pseudoswapper.extractors.pdf import extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules, subject_values, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file, force_suffix=".txt")
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd, write=write_session)
    return out


def _redact_eml(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None, subject_values: frozenset[str] | None = None, write_session: bool = True, strict_protection: bool = True, redact_mode: bool = False, _registry=None, _tokenizer=None) -> Path:
    from pseudoswapper.extractors.eml import extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules, subject_values, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file, force_suffix=".txt")
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd, write=write_session)
    return out


def _redact_msg(file: Path, config: dict, cwd: Path, passthrough_types: set[str] | None, masking_rules: dict | None, subject_values: frozenset[str] | None = None, write_session: bool = True, strict_protection: bool = True, redact_mode: bool = False, _registry=None, _tokenizer=None) -> Path:
    from pseudoswapper.extractors.msg import extract_text
    registry, tokenizer, detector = _build_pipeline(config, passthrough_types, masking_rules, subject_values, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    text = extract_text(file)
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)
    out = _output_path(file, force_suffix=".txt")
    out.write_text(redacted_text, encoding="utf-8")
    _save(registry, cwd, write=write_session)
    return out


def redact_document(
    file: Path,
    config: dict,
    cwd: Path,
    passthrough_types: set[str] | None = None,
    masking_rules: dict | None = None,
    subject_values: frozenset[str] | None = None,
    write_session: bool = True,
    strict_protection: bool = True,
    redact_mode: bool = False,
    _registry=None,
    _tokenizer=None,
) -> Path:
    """Run document mode: detect, tokenize/mask, replace, write output, save session."""
    suffix = file.suffix.lower()
    if suffix == ".docx":
        return _redact_docx(file, config, cwd, passthrough_types, masking_rules, subject_values, write_session, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    if suffix == ".pdf":
        return _redact_pdf(file, config, cwd, passthrough_types, masking_rules, subject_values, write_session, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    if suffix == ".eml":
        return _redact_eml(file, config, cwd, passthrough_types, masking_rules, subject_values, write_session, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    if suffix == ".msg":
        return _redact_msg(file, config, cwd, passthrough_types, masking_rules, subject_values, write_session, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
    return _redact_plain(file, config, cwd, passthrough_types, masking_rules, subject_values, write_session, strict_protection, redact_mode=redact_mode, _registry=_registry, _tokenizer=_tokenizer)
