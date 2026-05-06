import pytest
from pathlib import Path

from pseudoswapper.entity_registry import EntityRegistry
from pseudoswapper.session import (
    clear_session,
    create_session,
    load_session,
    save_session,
    session_exists,
)


@pytest.fixture
def cwd(tmp_path):
    return tmp_path


def make_registry(*entries) -> EntityRegistry:
    reg = EntityRegistry()
    for value, entity_type in entries:
        reg.register(value, entity_type)
    return reg


def test_session_exists_false_when_no_pointer(cwd):
    assert session_exists(cwd) is False


def test_create_session_writes_pointer(cwd):
    reg = make_registry(("John Doe", "PERSON"))
    create_session(reg, cwd)
    assert (cwd / ".pseudoswapper_session").exists()


def test_session_exists_true_after_create(cwd):
    reg = make_registry(("John Doe", "PERSON"))
    create_session(reg, cwd)
    assert session_exists(cwd) is True


def test_create_then_load_round_trip(cwd):
    reg = make_registry(("John Doe", "PERSON"), ("jane@corp.com", "EMAIL"))
    create_session(reg, cwd)

    loaded = load_session(cwd)
    assert loaded.lookup("John Doe") == "[PERSON_1]"
    assert loaded.lookup("jane@corp.com") == "[EMAIL_1]"
    assert loaded.reverse_lookup("[PERSON_1]") == "John Doe"


def test_temp_dir_has_restricted_permissions(cwd):
    reg = make_registry(("secret", "PERSON"))
    temp_dir = create_session(reg, cwd)

    import stat as stat_module
    mode = temp_dir.stat().st_mode
    # Owner has rwx; group and other have nothing
    assert mode & stat_module.S_IRWXG == 0
    assert mode & stat_module.S_IRWXO == 0


def test_save_session_updates_existing(cwd):
    reg = make_registry(("Alice", "PERSON"))
    create_session(reg, cwd)

    reg.register("bob@example.com", "EMAIL")
    save_session(reg, cwd)

    loaded = load_session(cwd)
    assert loaded.lookup("bob@example.com") == "[EMAIL_1]"


def test_clear_session_removes_pointer_and_temp_dir(cwd):
    reg = make_registry(("Alice", "PERSON"))
    temp_dir = create_session(reg, cwd)

    clear_session(cwd)

    assert not (cwd / ".pseudoswapper_session").exists()
    assert not temp_dir.exists()


def test_session_exists_false_after_clear(cwd):
    reg = make_registry(("Alice", "PERSON"))
    create_session(reg, cwd)
    clear_session(cwd)
    assert session_exists(cwd) is False


def test_clear_session_noop_when_no_session(cwd):
    # Should not raise
    clear_session(cwd)


def test_load_session_raises_when_no_pointer(cwd):
    with pytest.raises(FileNotFoundError, match="No active session"):
        load_session(cwd)


def test_load_session_raises_when_temp_dir_missing(cwd):
    reg = make_registry(("Alice", "PERSON"))
    temp_dir = create_session(reg, cwd)

    import shutil
    shutil.rmtree(temp_dir)

    with pytest.raises(FileNotFoundError):
        load_session(cwd)
