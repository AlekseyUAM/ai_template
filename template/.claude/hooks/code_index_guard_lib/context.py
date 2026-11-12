"""Контекст одного запуска хука."""
from dataclasses import dataclass

from .config import GuardConfig


@dataclass(frozen=True)
class GuardContext:
    config: GuardConfig
    paths: list[tuple[str, str]]
    case_insensitive: bool
