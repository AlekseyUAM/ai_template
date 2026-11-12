"""Нормализация и сравнение путей (порт code-index-guard)."""
import os
import sys


def default_case_insensitive() -> bool:
    """Windows и macOS сравнивают пути без учёта регистра, Linux — с учётом."""
    return os.name == "nt" or sys.platform == "darwin"


def fold_path(s: str, case_insensitive: bool | None = None) -> str:
    ci = default_case_insensitive() if case_insensitive is None else case_insensitive
    return s.lower() if ci else s


def norm_prefix(p: str, case_insensitive: bool | None = None) -> str:
    """Префикс репозитория: прямые слэши, без хвостового, регистр по правилу."""
    return fold_path(p.replace("\\", "/").rstrip("/"), case_insensitive)
