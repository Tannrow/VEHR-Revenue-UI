import os

_TRUTHY_VALUES = {"1", "true", "yes", "y", "on"}


def truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY_VALUES


def env_default_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_VALUES
