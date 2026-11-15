"""Регресс-проверки документации шаблона: синтаксис `Граница` и ASCII-дефисы в BSL."""

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[3] / "template"
BSL_DOCS = TEMPLATE / ".claude" / "skills" / "bsl-coding-standards"

# `Граница(` без `Новый ` непосредственно перед ним (lookbehind фиксированной
# ширины). Метод платформы (`Объект.Граница(`) — не конструктор: `[\w.]`
# слева его отсекает.
BOUNDARY_NO_NEW = re.compile(r"(?<!Новый )(?<![\w.])Граница\(")
# bsl_ls даёт InvalidCharacterInFile на эти тире в BSL-комментариях и строках
DASHES = ("—", "–")


def _code_spans(line: str):
    """Содержимое code-span'ов (между обратными кавычками) в строке markdown."""
    return re.findall(r"`([^`]*)`", line)


def _rel(path: Path) -> str:
    """Путь относительно шаблона; для временных каталогов — как есть."""
    try:
        return str(path.relative_to(TEMPLATE))
    except ValueError:
        return path.name


def _boundary_errors(root: Path):
    errors = []
    for path in sorted(root.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for span in _code_spans(line):
                match = BOUNDARY_NO_NEW.search(span)
                if match:
                    errors.append(f"{_rel(path)}:{lineno}: {span!r}")
    return errors


def _dash_errors(root: Path):
    errors = []
    for path in sorted(root.rglob("*.bsl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = [ch for ch in DASHES if ch in line]
            if found:
                errors.append(f"{_rel(path)}:{lineno}: {line.strip()!r}")
    return errors


def test_template_dir_exists():
    # Без каталога rglob молча вернул бы пустой список — проверки были бы вакуумными.
    assert TEMPLATE.is_dir(), f"нет каталога шаблона: {TEMPLATE}"
    assert BSL_DOCS.is_dir()


def test_boundary_regex_catches_constructor_without_new():
    assert BOUNDARY_NO_NEW.search("x = Граница(А, Б);")
    assert BOUNDARY_NO_NEW.search("Граница(А);")
    # отрицательные: с `Новый` и метод объекта
    assert not BOUNDARY_NO_NEW.search("x = Новый Граница(А, Б);")
    assert not BOUNDARY_NO_NEW.search("x = Объект.Граница(А);")
    assert not BOUNDARY_NO_NEW.search("ГраницаХранения(А);")


def test_boundary_examples_use_new():
    errors = _boundary_errors(BSL_DOCS)
    assert not errors, "`Граница(` без `Новый` в code-span:\n" + "\n".join(errors)


def test_boundary_check_not_vacuous(tmp_path):
    doc = tmp_path / "bad.md"
    doc.write_text("Пример: `Работа = Граница(А, Б);`\n", encoding="utf-8")
    assert _boundary_errors(doc.parent)
    # method call — не ошибка
    doc.write_text("Пример: `Работа = Объект.Граница(А);`\n", encoding="utf-8")
    assert not _boundary_errors(doc.parent)


def test_bsl_sources_use_ascii_dashes():
    errors = _dash_errors(TEMPLATE)
    assert not errors, "Не-ASCII тире в BSL-исходниках шаблона:\n" + "\n".join(errors)


def test_dash_rule_catches_bad_file(tmp_path):
    bad = tmp_path / "Модуль.bsl"
    bad.write_text("Процедура Тест() // шаг — один\n\tКонецПроцедуры\n",
                   encoding="utf-8")
    errors = _dash_errors(bad.parent)
    assert errors
    assert "—" in errors[0]
