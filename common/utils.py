"""Shared utility functions used across common modules."""


def _is_enabled_flag(value):
    """Interpret common enabled/disabled flag representations.

    Supports bool, string (enabled/true/yes/1/on), and int values.
    Returns False for any unrecognised type or value.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"enabled", "true", "yes", "1", "on"}:
            return True
        if normalized in {"disabled", "false", "no", "0", "off"}:
            return False
        return False
    if isinstance(value, int):
        return value != 0
    return False
