from pseudoswapper.config import default_config


def make_config(**overrides) -> dict:
    """Return a minimal valid config dict, with optional field overrides."""
    config = default_config()
    config.update(overrides)
    return config
