# Инструментарий ревью запросов 1С — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать ревьюеру два навыка в `template/.claude`: `query-analyze` (Python-скрипты поиска проблем в запросах 1С) и `query-review` (чеклист ручного ревью), наполняемые по 25 PDF-стандартам, с отчётом по каждому PDF.

**Architecture:** `extract_queries.py` (порт проверенного алгоритма из `query_console_vscode`) извлекает тексты запросов из `.bsl`/СКД-XML. `analyze_query.py` прогоняет реестр правил `rules.py` (одна функция = одна проверка со std-кодом) по тексту запроса и печатает находки. Непроверяемое скриптом фиксируется в `query-review/SKILL.md`. По каждому PDF — отчёт в `Done/`.

**Tech Stack:** Python 3.8+ (stdlib), pytest, pdftotext (poppler).

## Global Constraints

- Навыки лежат в `template/.claude/skills/<name>/`, у каждого `SKILL.md` с frontmatter: `name`, `description`, `allowed-tools` (значения — точные).
- Python-скрипты: `sys.stdout.reconfigure(encoding="utf-8")` в начале, argparse с PS-стилем флагов (`-Path`, `-Detailed`), `allow_abbrev=False`.
- Оба навыка регистрируются в `app/tests/env/test_content_files.py` в множестве `SKILLS`.
- Извлечение — дословный порт `src/cli/extractQueries.ts` из `~/projects/query_console_vscode`; поведение сверяется с `test/unit/extractQueries.test.ts`.
- SDBL-парсер НЕ портируется. Анализ — эвристики по тексту запроса.
- Тексты отчётов, SKILL.md, сообщения правил — на русском.
- Коммит после каждой задачи.

---

### Task 1: Скелет навыка `query-analyze` + порт извлечения запросов

**Files:**
- Create: `template/.claude/skills/query-analyze/SKILL.md`
- Create: `template/.claude/skills/query-analyze/scripts/extract_queries.py`
- Test: `template/.claude/skills/query-analyze/scripts/tests/test_extract.py`

**Interfaces:**
- Produces: `extract_queries.py` экспортирует
  - `extract_query_strings(bsl_source: str) -> list[ExtractedQuery]`
  - `extract_queries_from_xml(xml_source: str) -> list[ExtractedQuery]`
  - `unescape_xml_entities(s: str) -> str`
  - `ExtractedQuery` — dataclass с полями `text: str`, `line_start: int`.
  - CLI: `python extract_queries.py -Path <file|dir> [-Xml] [-Numbered]` печатает блоки `# <путь>:<line_start>` + текст запроса, разделённые строкой `--- 8< ---`.

- [ ] **Step 1: Написать падающие тесты (порт кейсов из extractQueries.test.ts)**

`template/.claude/skills/query-analyze/scripts/tests/test_extract.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from extract_queries import (
    extract_query_strings,
    extract_queries_from_xml,
    unescape_xml_entities,
)


def test_multiline_query_with_pipes():
    src = "\n".join([
        "Процедура Тест()",
        '\tЗапрос.Текст = "ВЫБРАТЬ',
        "\t|\tТаблица.Поле",
        "\t|ИЗ",
        '\t|\tСправочник.Тест КАК Таблица";',
        "КонецПроцедуры",
    ])
    res = extract_query_strings(src)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ\n\tТаблица.Поле\nИЗ\n\tСправочник.Тест КАК Таблица"
    assert res[0].line_start == 2


def test_two_queries_numbered_in_order():
    src = 'А = "ВЫБРАТЬ Поле1";\nБ = "ВЫБРАТЬ Поле2";'
    res = extract_query_strings(src)
    assert [q.text for q in res] == ["ВЫБРАТЬ Поле1", "ВЫБРАТЬ Поле2"]
    assert [q.line_start for q in res] == [1, 2]


def test_ignores_non_query_literal():
    assert extract_query_strings('Сообщить("Привет");') == []


def test_unescapes_doubled_quotes():
    res = extract_query_strings('Т = "ВЫБРАТЬ ""abc"" КАК Поле";')
    assert len(res) == 1
    assert res[0].text == 'ВЫБРАТЬ "abc" КАК Поле'


def test_ignores_keyword_in_comment():
    src = '// ВЫБРАТЬ это не запрос "ВЫБРАТЬ Поле"\nХ = 1;'
    assert extract_query_strings(src) == []


def test_recognizes_destroy_case_insensitive():
    res = extract_query_strings('Т = "уничтОжить Справочник.Тест";')
    assert len(res) == 1
    assert res[0].text == "уничтОжить Справочник.Тест"


def test_ignores_date_single_quotes():
    res = extract_query_strings("Д = '20240101'; Т = \"ВЫБРАТЬ 1\";")
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ 1"


def test_unescape_basic_entities():
    assert unescape_xml_entities("a &lt; b &gt; c &amp; d") == "a < b > c & d"


def test_unescape_quot_apos():
    assert unescape_xml_entities("&quot;x&quot; &apos;y&apos;") == "\"x\" 'y'"


def test_unescape_left_to_right_priority():
    assert unescape_xml_entities("&amp;lt;") == "&lt;"


def test_unescape_numeric_dec_and_hex():
    assert unescape_xml_entities("&#1041;&#x42E;") == "БЮ"


def test_unescape_bad_codepoint_kept():
    assert unescape_xml_entities("&#x110000;") == "&#x110000;"


def test_xml_single_query_decoded():
    xml = "<dataSet><query>ВЫБРАТЬ Т.Поле\nГДЕ Т.А &lt;&gt; &amp;П</query></dataSet>"
    res = extract_queries_from_xml(xml)
    assert len(res) == 1
    assert res[0].text == "ВЫБРАТЬ Т.Поле\nГДЕ Т.А <> &П"


def test_xml_multiple_queries_line_start():
    xml = "\n".join([
        "<schema>",
        "  <query>ВЫБРАТЬ Поле1</query>",
        "  <other>x</other>",
        "  <query>ВЫБРАТЬ Поле2</query>",
        "</schema>",
    ])
    res = extract_queries_from_xml(xml)
    assert [q.text for q in res] == ["ВЫБРАТЬ Поле1", "ВЫБРАТЬ Поле2"]
    assert [q.line_start for q in res] == [2, 4]


def test_xml_ignores_non_query():
    assert extract_queries_from_xml("<query>не запрос</query>") == []
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_extract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'extract_queries'`.

- [ ] **Step 3: Реализовать `extract_queries.py` (порт алгоритма)**

```python
# extract_queries.py — порт src/cli/extractQueries.ts (query_console_vscode).
import argparse
import os
import re
import sys
from dataclasses import dataclass

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

QUERY_KEYWORDS = ("ВЫБРАТЬ", "УНИЧТОЖИТЬ")

NAMED_XML_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}

_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|#[xX][0-9a-fA-F]+|#[0-9]+);")
_WORD_RE = re.compile(r"[^\W]", re.UNICODE)  # буква/цифра/подчёркивание проверяется отдельно


@dataclass
class ExtractedQuery:
    text: str
    line_start: int


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _starts_with_query_keyword(text: str) -> bool:
    trimmed = text.lstrip(" \t\r\n﻿")
    upper = trimmed.upper()
    for kw in QUERY_KEYWORDS:
        if not upper.startswith(kw):
            continue
        nxt = trimmed[len(kw):len(kw) + 1]
        if nxt == "" or not _is_word_char(nxt):
            return True
    return False


def _unpipe(raw_body: str) -> str:
    lines = raw_body.split("\n")
    out = []
    for i, line in enumerate(lines):
        if i == 0:
            out.append(line)
            continue
        m = re.match(r"[ \t]*\|", line)
        out.append(line[m.end():] if m else line)
    return "\n".join(out)


def unescape_xml_entities(s: str) -> str:
    def repl(m):
        ent = m.group(1)
        if ent[0] == "#":
            code = int(ent[2:], 16) if ent[1] in "xX" else int(ent[1:], 10)
            if code < 0 or code > 0x10FFFF:
                return m.group(0)
            try:
                return chr(code)
            except ValueError:
                return m.group(0)
        return NAMED_XML_ENTITIES[ent]
    return _ENTITY_RE.sub(repl, s)


def extract_query_strings(bsl_source: str):
    result = []
    n = len(bsl_source)
    i = 0
    line = 1
    while i < n:
        ch = bsl_source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and bsl_source[i + 1] == "/":
            while i < n and bsl_source[i] != "\n":
                i += 1
            continue
        if ch == "'":
            i += 1
            while i < n and bsl_source[i] != "'" and bsl_source[i] != "\n":
                i += 1
            if i < n and bsl_source[i] == "'":
                i += 1
            continue
        if ch == '"':
            line_start = line
            i += 1
            raw = []
            while i < n:
                c = bsl_source[i]
                if c == '"':
                    if i + 1 < n and bsl_source[i + 1] == '"':
                        raw.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                if c == "\n":
                    line += 1
                raw.append(c)
                i += 1
            text = _unpipe("".join(raw))
            if _starts_with_query_keyword(text):
                result.append(ExtractedQuery(text, line_start))
            continue
        i += 1
    return result


def extract_queries_from_xml(xml_source: str):
    result = []
    for m in re.finditer(r"<query>([\s\S]*?)</query>", xml_source):
        line_start = xml_source[:m.start()].count("\n") + 1
        text = unescape_xml_entities(m.group(1))
        if _starts_with_query_keyword(text):
            result.append(ExtractedQuery(text, line_start))
    return result


def _walk(root: str, ext: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(ext):
                yield os.path.join(dirpath, name)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("-Path", required=True)
    parser.add_argument("-Xml", action="store_true", help="извлекать из СКД-XML (<query>)")
    args = parser.parse_args(argv)
    path = args.Path
    blocks = []
    targets = []
    if os.path.isdir(path):
        ext = ".xml" if args.Xml else ".bsl"
        targets = sorted(_walk(path, ext))
    else:
        targets = [path]
    for file in targets:
        try:
            with open(file, encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            continue
        found = extract_queries_from_xml(source) if args.Xml else extract_query_strings(source)
        for q in found:
            blocks.append(f"# {file}:{q.line_start}\n{q.text}")
    print("\n--- 8< ---\n".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_extract.py -q`
Expected: PASS (14 passed).

- [ ] **Step 5: Написать `SKILL.md`**

```markdown
---
name: query-analyze
description: Автоматический анализ запросов 1С на нарушения стандартов оптимальных запросов. Используй для поиска проблем/ошибок в тексте запроса перед код-ревью.
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /query-analyze — автоматический анализ запросов 1С

Находит нарушения стандартов разработки оптимальных запросов (ИТС, std*).
Работает в два шага: извлечение текста запроса из `.bsl`/СКД-XML и прогон
реестра автоматических проверок.

## Извлечение запросов

```bash
# Из .bsl-файла или каталога (рекурсивно)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Catalogs/Товары/Ext/ManagerModule.bsl
# Из макетов СКД (XML)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Reports -Xml
```

Выводит блоки `# <путь>:<строка>` с текстом запроса, разделённые `--- 8< ---`.

## Анализ запроса

```bash
# Текст запроса из файла
python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" query.txt
# Или из stdin
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path Module.bsl | python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" -
```

Находки печатаются как `severity | std-код | строка | сообщение`. Флаг
`-Detailed` показывает и пройденные проверки. Код возврата ≠ 0 при находках
уровня `error`.

## Чего анализатор НЕ проверяет

Автопроверки работают только по тексту запроса. Соответствие индексам БД,
семантике задачи и составу метаданных проверяется вручную — см. навык
`query-review`.
```

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/skills/query-analyze/SKILL.md template/.claude/skills/query-analyze/scripts/extract_queries.py template/.claude/skills/query-analyze/scripts/tests/test_extract.py
git commit -m "feat(query-analyze): скелет навыка + порт извлечения запросов из .bsl/СКД

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Движок анализа + реестр правил + первое правило (ВЫБРАТЬ *)

**Files:**
- Create: `template/.claude/skills/query-analyze/scripts/rules.py`
- Create: `template/.claude/skills/query-analyze/scripts/analyze_query.py`
- Test: `template/.claude/skills/query-analyze/scripts/tests/test_rules.py`

**Interfaces:**
- Consumes: ничего из Task 1 (независимый модуль).
- Produces:
  - `rules.py`:
    - `@dataclass Finding(code: str, severity: str, line: int, message: str)`
    - `@dataclass QueryContext(text: str)` с ленивыми свойствами: `lines: list[str]`, `upper: str` (текст в верхнем регистре, той же длины), `statements: list[tuple[int, str]]` (пакеты по `;` с номером стартовой строки). Метод `line_of(pos: int) -> int`.
    - `RULES: list[Rule]` — глобальный реестр; декоратор `@rule(code, severity, title)` регистрирует функцию `fn(ctx: QueryContext) -> list[Finding]`.
    - `run_all(ctx) -> list[Finding]`.
    - `check_select_star` — первое правило (std729): `ВЫБРАТЬ *`.
  - `analyze_query.py` CLI: `python analyze_query.py <file|->  [-Detailed] [-NoFail]`.
- Produced helpers используются всеми последующими PDF-задачами.

- [ ] **Step 1: Написать падающий тест**

`tests/test_rules.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rules


def _codes(text):
    ctx = rules.QueryContext(text)
    return [f.code for f in rules.run_all(ctx)]


def test_select_star_flagged():
    assert "std729:select-star" in _codes("ВЫБРАТЬ * ИЗ Справочник.Товары")


def test_select_star_case_insensitive():
    assert "std729:select-star" in _codes("выбрать   *  из Справочник.Товары")


def test_explicit_fields_not_flagged():
    assert "std729:select-star" not in _codes("ВЫБРАТЬ Код, Наименование ИЗ Справочник.Товары")


def test_multiplication_not_flagged_as_star():
    # звёздочка как умножение в выражении — не ВЫБРАТЬ *
    assert "std729:select-star" not in _codes("ВЫБРАТЬ Цена * Количество КАК Сумма ИЗ Документ.Продажа")


def test_context_line_of():
    ctx = rules.QueryContext("ВЫБРАТЬ\n*\nИЗ Т")
    assert ctx.line_of(ctx.text.index("*")) == 2
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_rules.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules'`.

- [ ] **Step 3: Реализовать `rules.py`**

```python
# rules.py — реестр автоматических проверок запросов 1С.
import re
from dataclasses import dataclass, field


@dataclass
class Finding:
    code: str
    severity: str  # error | warning | info
    line: int
    message: str


@dataclass
class Rule:
    code: str
    severity: str
    title: str
    fn: object


RULES = []


def rule(code, severity, title):
    def deco(fn):
        RULES.append(Rule(code=code, severity=severity, title=title, fn=fn))
        return fn
    return deco


class QueryContext:
    def __init__(self, text):
        self.text = text
        self._lines = None
        self._upper = None

    @property
    def lines(self):
        if self._lines is None:
            self._lines = self.text.split("\n")
        return self._lines

    @property
    def upper(self):
        if self._upper is None:
            self._upper = self.text.upper()  # для кириллицы длина сохраняется
        return self._upper

    def line_of(self, pos):
        return self.text.count("\n", 0, pos) + 1


def run_all(ctx):
    findings = []
    for r in RULES:
        findings.extend(r.fn(ctx))
    return findings


# ── Проверки ────────────────────────────────────────────────

_SELECT_STAR_RE = re.compile(r"\bВЫБРАТЬ\b(?:\s+(?:РАЗРЕШЕННЫЕ|РАЗЛИЧНЫЕ|ПЕРВЫЕ\s+\d+))*\s*\*", re.UNICODE)


@rule(code="std729:select-star", severity="warning",
      title="ВЫБРАТЬ * — выбирать только нужные поля")
def check_select_star(ctx):
    out = []
    for m in _SELECT_STAR_RE.finditer(ctx.upper):
        out.append(Finding(
            code="std729:select-star",
            severity="warning",
            line=ctx.line_of(m.start()),
            message="ВЫБРАТЬ *: выбирайте только нужные поля, а не все (std729).",
        ))
    return out
```

- [ ] **Step 4: Реализовать `analyze_query.py`**

```python
# analyze_query.py — прогон реестра правил по тексту запроса.
import argparse
import sys

import rules

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("source", help="путь к файлу с текстом запроса или '-' для stdin")
    parser.add_argument("-Detailed", action="store_true")
    parser.add_argument("-NoFail", action="store_true", help="не возвращать код ≠0 при error")
    args = parser.parse_args(argv)

    text = sys.stdin.read() if args.source == "-" else open(args.source, encoding="utf-8").read()
    ctx = rules.QueryContext(text)
    findings = rules.run_all(ctx)
    findings.sort(key=lambda f: (f.line, f.code))

    for f in findings:
        print(f"{f.severity} | {f.code} | строка {f.line} | {f.message}")

    if args.Detailed:
        hit = {f.code for f in findings}
        for r in rules.RULES:
            if r.code not in hit:
                print(f"ok | {r.code} | — | {r.title}")

    if not findings:
        print("Нарушений не найдено.")

    has_error = any(f.severity == "error" for f in findings)
    return 0 if args.NoFail else (1 if has_error else 0)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `cd template/.claude/skills/query-analyze/scripts && python -m pytest tests/test_rules.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Smoke CLI**

Run: `cd template/.claude/skills/query-analyze/scripts && printf 'ВЫБРАТЬ * ИЗ Справочник.Товары' | python analyze_query.py -`
Expected: строка `warning | std729:select-star | строка 1 | ВЫБРАТЬ *: ...`.

- [ ] **Step 7: Коммит**

```bash
git add template/.claude/skills/query-analyze/scripts/rules.py template/.claude/skills/query-analyze/scripts/analyze_query.py template/.claude/skills/query-analyze/scripts/tests/test_rules.py
git commit -m "feat(query-analyze): движок анализа, реестр правил, проверка ВЫБРАТЬ * (std729)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Скелет навыка `query-review` + регистрация навыков в тесте окружения

**Files:**
- Create: `template/.claude/skills/query-review/SKILL.md`
- Modify: `app/tests/env/test_content_files.py:5` (множество `SKILLS`)

**Interfaces:**
- Consumes: ничего.
- Produces: навык-чеклист `query-review`, пополняемый PDF-задачами; оба новых навыка в `SKILLS`.

- [ ] **Step 1: Написать `query-review/SKILL.md` (скелет чеклиста)**

```markdown
---
name: query-review
description: Чеклист код-ревью запросов 1С — требования стандартов, которые нельзя проверить автоматически (индексы БД, метаданные, семантика задачи). Используй при ревью запроса после /query-analyze.
allowed-tools:
  - Read
---

# /query-review — чеклист ручного ревью запросов 1С

Сюда вынесены требования стандартов оптимальных запросов, которые НЕ
проверяются скриптом `query-analyze` (нужны знание индексов БД, состава
метаданных или семантики задачи). Проверяй каждый пункт глазами.

Формат пункта: `[std-код] требование — что смотреть`.

## Чеклист

<!-- Пункты добавляются по мере разбора стандартов. -->
```

- [ ] **Step 2: Обновить `SKILLS` в тесте окружения**

В `app/tests/env/test_content_files.py` заменить строку 5:

```python
SKILLS = {"mcp-usage", "bsl-coding-standards", "sdd-tdd-workflow", "task-orchestration",
          "query-analyze", "query-review"}
```

- [ ] **Step 3: Запустить тест окружения**

Run: `cd ~/projects/ai_template && python -m pytest app/tests/env/test_content_files.py -q`
Expected: PASS (включая `test_skills_present_and_valid`).

- [ ] **Step 4: Коммит**

```bash
git add template/.claude/skills/query-review/SKILL.md app/tests/env/test_content_files.py
git commit -m "feat(query-review): скелет чеклиста ручного ревью + регистрация навыков

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4..28: Разбор PDF-стандартов (по одному PDF = одна задача)

Каждый PDF обрабатывается ОДНОЙ итерацией по одной и той же процедуре. Ниже —
полная процедура и порядок файлов. Порядок: от базовых к частным.

**Процедура для одного PDF `<name>.pdf`:**

- [ ] **Step 1: Извлечь текст стандарта**

Run: `cd "~/projects/ai_template/tmp/docs/Ревью запросов" && pdftotext -enc UTF-8 "<name>.pdf" -`
Прочитать вывод, выписать проверяемые требования и их std-код (из URL/`#std...`).

- [ ] **Step 2: Классифицировать каждое требование**
  - Автоматизируемо по тексту запроса → новое правило в `rules.py`.
  - Неавтоматизируемо (индексы/метаданные/семантика) → пункт в `query-review/SKILL.md`.

- [ ] **Step 3: Для авто-требований — TDD правило**
  1. Добавить позитивный и негативный тест в `tests/test_rules.py` (код правила вида `std<NNN>:<short>`).
  2. Запустить: `python -m pytest tests/test_rules.py -q` → FAIL.
  3. Добавить функцию с `@rule(...)` в `rules.py`.
  4. Запустить → PASS.

- [ ] **Step 4: Для ручных требований — дописать пункт в `query-review/SKILL.md`**
  Строка вида `- [std<NNN>] <требование> — <что смотреть глазами>`.

- [ ] **Step 5: Написать отчёт**
  `tmp/docs/Ревью запросов/Done/<name>.md` со структурой:
  ```markdown
  # <name>

  Код стандарта: std<NNN>. Область применения: <...>.

  ## Выводы из стандарта
  - <ключевые требования>

  ## Добавлено в query-analyze (авто)
  - `std<NNN>:<short>` (<severity>) — <что ловит> (+ тесты).
  - (или «нет автопроверок — причина»)

  ## Добавлено в query-review (чеклист)
  - [std<NNN>] <требование> — <что смотреть>.
  - (или «нет ручных пунктов»)

  ## Осознанно не автоматизировано
  - <требование> — <почему нельзя скриптом>.
  ```

- [ ] **Step 6: Прогнать все тесты навыка**
  Run: `cd template/.claude/skills/query-analyze/scripts && python -m pytest tests -q`
  Expected: PASS.

- [ ] **Step 7: Коммит**
  ```bash
  git add template/.claude/skills tmp/docs/"Ревью запросов"/Done
  git commit -m "feat(query-review): стандарт <name> — проверки + отчёт"
  ```

**Порядок обработки PDF (по задаче на каждый):**

1. `Общие требования по разработке оптимальных запросов .pdf`
2. `Оформление текстов запросов.pdf`
3. `Псевдонимы источников данных в запросах.pdf`
4. `Упорядочивание результатов запроса.pdf`
5. `Проверка на пустой результат выполнения запроса.pdf`
6. `Использование ключевых слов _ОБЪЕДИНИТЬ_ и _ОБЪЕДИНИТЬ ВСЕ_ в запросах .pdf`
7. `Особенности использования в запросах оператора ПОДОБНО.pdf`
8. `Округление результатов арифметических операций в запросах.pdf`
9. `Ограничение на использование конструкции _ПОЛНОЕ ВНЕШНЕЕ СОЕДИНЕНИЕ_ в запросах.pdf`
10. `Ограничения на использование вложенных запросов в условии соединения.pdf`
11. `Ограничения на соединения с вложенными запросами и виртуальными таблицами.pdf`
12. `Разыменование ссылочных полей составного типа в языке запросов.pdf`
13. `Эффективные условия запросов.pdf`
14. `Несоответствие индексов и условий запроса.pdf`
15. `Индексы таблиц базы данных.pdf`
16. `Дополнительные индексы.pdf`
17. `Обращения к виртуальным таблицам.pdf`
18. `Эффективное обращение к виртуальной таблице «Остатки».pdf`
19. `Использование временных таблиц.pdf`
20. `Многократное выполнение однотипных запросов.pdf`
21. `Вычисление количества записей в запросах.pdf`
22. `Разрешение итогов для периодических регистров сведений.pdf`
23. `Запросы в динамических списках.pdf`
24. `Глава 9. Работа с данными __ 1С_Предприятие 8.3.27. Документация.pdf`

(«Done» — каталог отчётов; создаётся при первом отчёте: `mkdir -p "tmp/docs/Ревью запросов/Done"`.)

---

## Self-Review

- **Покрытие спеки:** оба навыка (Task 1–3), извлечение (Task 1), движок+правила (Task 2), чеклист (Task 3), регистрация в тесте (Task 3), per-PDF отчёты и наполнение (Task 4..28) — покрыто.
- **Плейсхолдеры:** код приведён целиком для скелета и первого правила; PDF-задачи намеренно процедурные (содержимое правил зависит от текста стандарта, который читается в Step 1) — это не плейсхолдер, а детерминированная процедура с полным кодом движка в Task 2.
- **Согласованность типов:** `ExtractedQuery.text/line_start`, `Finding(code,severity,line,message)`, `QueryContext.text/lines/upper/line_of`, `rule(code,severity,title)` — используются единообразно во всех задачах.

## Примечания по исполнению

- 24 PDF (не 25: `tmp/docs/Ревью запросов` содержит 24 файла). Один PDF = одна
  обрабатываемая единица; «Глава 9» — обзорная, из неё берём только конкретные
  проверяемые требования.
- Делать небольшими частями: по одному PDF за подход, с коммитом и отчётом.
