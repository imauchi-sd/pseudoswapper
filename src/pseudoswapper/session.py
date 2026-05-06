from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from pseudoswapper.entity_registry import EntityRegistry

_POINTER_FILENAME = ".pseudoswapper_session"
_SESSION_FILENAME = "session.json"


def _pointer_path(cwd: Path) -> Path:
    return cwd / _POINTER_FILENAME


def session_exists(cwd: Path) -> bool:
    pointer = _pointer_path(cwd)
    if not pointer.exists():
        return False
    temp_dir = Path(pointer.read_text().strip())
    return temp_dir.exists() and (temp_dir / _SESSION_FILENAME).exists()


def create_session(registry: EntityRegistry, cwd: Path) -> Path:
    """Write registry to a new temp dir and drop the pointer file in *cwd*."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_dir.chmod(stat.S_IRWXU)  # 0700

    session_file = temp_dir / _SESSION_FILENAME
    session_file.write_text(json.dumps(registry.to_dict(), indent=2))

    pointer = _pointer_path(cwd)
    pointer.write_text(str(temp_dir))
    return temp_dir


def load_session(cwd: Path) -> EntityRegistry:
    """Load registry from the session pointed to by the pointer file in *cwd*."""
    pointer = _pointer_path(cwd)
    if not pointer.exists():
        raise FileNotFoundError(
            f"No active session found in {cwd}. "
            "Run 'pseudoswapper document' or 'pseudoswapper structured' first."
        )
    temp_dir = Path(pointer.read_text().strip())
    session_file = temp_dir / _SESSION_FILENAME
    if not session_file.exists():
        raise FileNotFoundError(
            f"Session data missing at {temp_dir}. "
            "The session may have been deleted. Run 'pseudoswapper clear-session' to clean up."
        )
    data = json.loads(session_file.read_text())
    return EntityRegistry.from_dict(data)


def save_session(registry: EntityRegistry, cwd: Path) -> None:
    """Overwrite the existing session's registry (used after redact updates the registry)."""
    pointer = _pointer_path(cwd)
    if not pointer.exists():
        raise FileNotFoundError(f"No active session pointer found in {cwd}.")
    temp_dir = Path(pointer.read_text().strip())
    session_file = temp_dir / _SESSION_FILENAME
    session_file.write_text(json.dumps(registry.to_dict(), indent=2))


def clear_session(cwd: Path) -> None:
    """Delete the temp dir and pointer file unconditionally."""
    pointer = _pointer_path(cwd)
    if pointer.exists():
        temp_dir_str = pointer.read_text().strip()
        temp_dir = Path(temp_dir_str)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        pointer.unlink(missing_ok=True)
