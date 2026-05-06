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


def _output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}.redacted{input_path.suffix}"


def redact_document(file: Path, config: dict, cwd: Path) -> Path:
    """Run document mode: detect, tokenize, replace, write output, save session."""
    registry = EntityRegistry()
    tokenizer = Tokenizer(registry)
    detector = Detector(config)

    _pre_register_employees(config, tokenizer)

    text = file.read_text(encoding="utf-8", errors="replace")
    entities = detector.analyze(text)
    token_map = tokenizer.assign(entities)
    redacted_text = replace(text, token_map)

    out = _output_path(file)
    out.write_text(redacted_text, encoding="utf-8")

    if session_exists(cwd):
        save_session(registry, cwd)
    else:
        create_session(registry, cwd)

    return out
