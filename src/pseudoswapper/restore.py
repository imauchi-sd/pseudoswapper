from __future__ import annotations

import re
from pathlib import Path

from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.session import clear_session, load_session

# Matches any [TOKEN] pattern, case-insensitively, tolerating AI reformatting.
_TOKEN_PATTERN = re.compile(r"\[([^\[\]\s]+)\]", re.IGNORECASE)


def restore(text: str, registry: EntityRegistry) -> str:
    """Replace all token occurrences in *text* with their original values."""
    # Build an uppercase-keyed lookup so case variants from AI output all resolve.
    reverse: dict[str, str] = {k.upper(): v for k, v in registry._reverse.items()}

    def _lookup(m: re.Match) -> str:
        token = m.group(0).upper()
        return reverse.get(token, m.group(0))

    return _TOKEN_PATTERN.sub(_lookup, text)


def _output_path(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}.restored{input_path.suffix}"


def restore_file(file: Path, cwd: Path) -> Path:
    """Load session, restore tokens in *file*, write output, then clear the session."""
    registry = load_session(cwd)
    text = file.read_text(encoding="utf-8", errors="replace")
    restored_text = restore(text, registry)

    out = _output_path(file)
    out.write_text(restored_text, encoding="utf-8")

    clear_session(cwd)
    return out
