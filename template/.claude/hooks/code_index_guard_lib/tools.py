"""Имена инструментов code-index так, как их видит модель."""
DEFAULT_PREFIX = "mcp__code_index__"
_prefix = DEFAULT_PREFIX


def set_prefix(prefix: str | None) -> None:
    global _prefix
    _prefix = prefix or DEFAULT_PREFIX


def tool(name: str) -> str:
    return f"{_prefix}{name}"
