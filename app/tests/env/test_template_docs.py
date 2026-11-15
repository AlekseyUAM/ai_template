"""Регресс-проверки документации шаблона: синтаксис `Граница` и ASCII-дефисы в BSL."""

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[3] / "template"
BSL_DOCS = TEMPLATE / ".claude" / "skills" / "bsl-coding-standards"

# `Граница(` без `Новый ` непосредственно перед ним
BOUNDARY_NO_NEW = re.compile(r"(?<!Новый )Граница\(")
# bsl_ls даёт InvalidCharacterInFile на эти тире в BSL-комментариях и строках
DASHES = ("—", "–")


def _code_spans(line: str):
    """Содержимое code-span'ов (между обратными кавычками) в строке markdown."""
    return re.findall(r"`([^`]*)`", line)


def test_boundary_examples_use_new():
    errors = []
    for path in sorted(BSL_DOCS.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for span in _code_spans(line):
                match = BOUNDARY_NO_NEW.search(span)
                if match:
                    errors.append(f"{path.relative_to(TEMPLATE)}:{lineno}: {span!r}")
    assert not errors, "`Граница(` без `Новый` в code-span:\n" + "\n".join(errors)


def test_bsl_sources_use_ascii_dashes():
    errors = []
    for path in sorted(TEMPLATE.rglob("*.bsl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = [ch for ch in DASHES if ch in line]
            if found:
                errors.append(f"{path.relative_to(TEMPLATE)}:{lineno}: {line.strip()!r}")
    assert not errors, "Не-ASCII тире в BSL-исходниках шаблона:\n" + "\n".join(errors)
