# Содержимое окружения (субагенты, скилы, правила, хуки) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Наполнить окружение реальным содержимым (5 субагентов, скилы-руководства, правила, хук) и развернуть его установщиком №1, параметризуя модель/effort из конфига.

**Architecture:** Каталог-шаблон `app/src/agentmon/env/content/` (agents/skills/rules/hooks), модуль `content.py` раскладывает его в `<project>/.claude/` и рендерит `settings.json`/`CLAUDE.md`; установщик №1 заменяет шаг `claude` на шаг `content`.

**Tech Stack:** Python 3.10+ (stdlib: json, pathlib, shutil-free copy), pytest. Контент — markdown (агенты/скилы/правила), Python-хук. Без новых зависимостей.

## Global Constraints

- Кросс-платформа Linux+Windows; пути только `pathlib`.
- Своя реализация, deps — референс. Тексты на русском.
- Без новых зависимостей.
- Копирование контента (не симлинки). Без RUS-ENG зеркала.
- Ровно 5 субагентов: `analyst`, `architect`, `developer`, `tester`, `reviewer`.
- 3 скила: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 3 правила:
  `search-before-write`, `verify-with-syntax-checker`, `task-artifacts`.
- 5 MCP: `1c-md`, `1c-syntax-checker-mcp`, `bsl-platform-context`, `1c-naparnic`, `code-index`.
- Агент-файлы содержат плейсхолдеры `{{MODEL}}` и `{{EFFORT}}`, подставляемые при установке из `config.agents`.
- Источник истины — файл; при `update` пользовательские `CLAUDE.md`/`settings.json` бэкапятся (`write_preserving`), а `agents/skills/rules/hooks` перезаписываются из шаблона.

## File Structure

- Create: `app/src/agentmon/env/content/agents/{analyst,architect,developer,tester,reviewer}.md`
- Create: `app/src/agentmon/env/content/skills/{mcp-usage,bsl-coding-standards,sdd-tdd-workflow}/SKILL.md`
- Create: `app/src/agentmon/env/content/rules/{search-before-write,verify-with-syntax-checker,task-artifacts}.md`
- Create: `app/src/agentmon/env/content/hooks/bsl_nudge.py`
- Create: `app/src/agentmon/env/content.py`
- Modify: `app/src/agentmon/env/installer.py` (шаг `claude` → `content`; убрать `_claude_md`)
- Test: `app/tests/env/test_content_files.py`, `test_bsl_nudge.py`, `test_content_deploy.py`, и правка `test_installer.py`

---

## Task 1: Файлы субагентов (5)

**Files:**
- Create: `app/src/agentmon/env/content/agents/analyst.md`, `architect.md`, `developer.md`, `tester.md`, `reviewer.md`
- Test: `app/tests/env/test_content_files.py`

**Interfaces:**
- Produces: 5 agent-шаблонов. Каждый — YAML frontmatter (`name`, `description`, `tools`, `model: {{MODEL}}`, `effort: {{EFFORT}}`) + русский системный промпт. Имена: analyst, architect, developer, tester, reviewer.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_content_files.py
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[2] / "src" / "agentmon" / "env" / "content"
AGENTS = {"analyst", "architect", "developer", "tester", "reviewer"}


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "нет frontmatter"
    end = text.index("\n---", 4)
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def test_exactly_five_agents():
    files = {p.stem for p in (CONTENT / "agents").glob("*.md")}
    assert files == AGENTS


def test_agent_frontmatter_valid():
    for name in AGENTS:
        text = (CONTENT / "agents" / f"{name}.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
        assert "tools" in fm
        assert fm["model"] == "{{MODEL}}"
        assert fm["effort"] == "{{EFFORT}}"
        assert len(text) > 400, "промпт слишком короткий"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: FAIL (каталог agents пуст / файлов нет).

- [ ] **Step 3: Создать файлы агентов**

`app/src/agentmon/env/content/agents/analyst.md`:
```markdown
---
name: analyst
description: Аналитик 1С. Превращает требования в спецификацию (цель, требования, ограничения, критерии приёмки). Вызывай на этапе анализа, до проектирования и кода.
tools: Read, Grep, Glob
model: {{MODEL}}
effort: {{EFFORT}}
---

# Аналитик

Ты — аналитик 1С. Твоя задача — понять требования и зафиксировать их спецификацией.

## Когда вызываюсь
Этап «анализ»: в начале задачи, до архитектора и разработчика.

## Вход
Описание задачи (цель, план, ограничения) из каталога задачи.

## Что делаю
1. Уточняю цель и границы задачи.
2. Формулирую требования (что система должна делать) в терминах RFC 2119 (ДОЛЖНА/СЛЕДУЕТ/МОЖЕТ).
3. Фиксирую ограничения и критерии приёмки.
4. Отмечаю открытые вопросы и риски.

## Выход
Файл `ANALYZE.md` в каталоге задачи: цель, требования, ограничения, критерии приёмки, риски.

## Используемые MCP
- `bsl-platform-context` — справка по платформе.
- `1c-naparnic` — сложные вопросы по 1С.
- `code-index` — поиск по существующей кодовой базе.
- `1c-md` — изучение метаданных.

## Границы
Только анализ. Не проектирую архитектуру и не пишу код.
```

`app/src/agentmon/env/content/agents/architect.md`:
```markdown
---
name: architect
description: Архитектор 1С. По спецификации готовит технический дизайн и декомпозицию на этапы. Вызывай на этапе планирования, после аналитика.
tools: Read, Grep, Glob
model: {{MODEL}}
effort: {{EFFORT}}
---

# Архитектор

Ты — архитектор 1С. Проектируешь решение по готовой спецификации.

## Когда вызываюсь
Этап «план»: после аналитика, до разработки.

## Вход
`ANALYZE.md` (спецификация) из каталога задачи.

## Что делаю
1. Определяю затрагиваемые объекты метаданных и модули.
2. Проектирую решение (структура, ответственность, интерфейсы).
3. Декомпозирую на этапы/шаги разработки и тестирования.
4. Фиксирую решения и альтернативы.

## Выход
Файл `ARCHITECT.md` в каталоге задачи: технический дизайн, затронутые объекты, план этапов.

## Используемые MCP
- `1c-md` — метаданные конфигурации.
- `code-index` — поиск существующих решений.
- `bsl-platform-context` — справка по платформе.

## Границы
Только проектирование. Не пишу прикладной код.
```

`app/src/agentmon/env/content/agents/developer.md`:
```markdown
---
name: developer
description: Разработчик 1С. Пишет BSL-код по спецификации, техдизайну и заранее написанным тестам. Вызывай на этапе разработки.
tools: Read, Grep, Glob, Edit, Write, Bash
model: {{MODEL}}
effort: {{EFFORT}}
---

# Разработчик

Ты — разработчик 1С. Реализуешь BSL-код, чтобы тесты проходили, следуя стандартам.

## Когда вызываюсь
Этап «разработка»: после аналитика, архитектора и написания тестов.

## Вход
`ANALYZE.md`, `ARCHITECT.md`, написанные тесты.

## Что делаю
1. Ищу существующий код перед написанием нового (правило search-before-write).
2. Пишу минимальный BSL-код по стандартам (навык bsl-coding-standards).
3. После правок прогоняю статический анализ (правило verify-with-syntax-checker).
4. Довожу тесты до «зелёного».

## Выход
Изменённый BSL-код и файл `DEVELOP.md` в каталоге задачи: что сделано, список изменённых файлов.

## Используемые MCP
- `1c-syntax-checker-mcp` — статический анализ BSL.
- `code-index` — поиск по коду.
- `bsl-platform-context` — справка по платформе.
- `1c-md` — метаданные.

## Границы
Реализую по утверждённому дизайну. Расширение объёма — к архитектору.
```

`app/src/agentmon/env/content/agents/tester.md`:
```markdown
---
name: tester
description: Тестировщик 1С. Пишет и запускает тесты (YaxUnit), расширяет покрытие, ловит регрессии. Вызывай на этапе тестирования.
tools: Read, Grep, Glob, Edit, Write, Bash
model: {{MODEL}}
effort: {{EFFORT}}
---

# Тестировщик

Ты — тестировщик 1С. Отвечаешь за тесты и покрытие.

## Когда вызываюсь
Этап «создание тестов» (до разработки, Red) и этап «тестирование» (после разработки).

## Вход
`ANALYZE.md`, `ARCHITECT.md`, код разработчика.

## Что делаю
1. Пишу юнит-тесты (YaxUnit) по критериям приёмки — до реализации (Red).
2. После разработки расширяю покрытие: граничные случаи, регрессии.
3. Прогоняю тесты и статический анализ, фиксирую результаты.

## Выход
Тестовые модули и файл `TEST.md` в каталоге задачи: покрытие, результаты прогона.

## Используемые MCP
- `1c-syntax-checker-mcp` — статический анализ.
- `1c-md` — метаданные.

## Границы
Пишу тесты и проверяю. Прикладной код правит разработчик.
```

`app/src/agentmon/env/content/agents/reviewer.md`:
```markdown
---
name: reviewer
description: Код-ревьюер 1С. Проверяет соответствие спецификации, стандарты и качество кода, выносит вердикт приёмки. Вызывай на этапе ревью.
tools: Read, Grep, Glob
model: {{MODEL}}
effort: {{EFFORT}}
---

# Код-ревьюер

Ты — код-ревьюер 1С. Независимый контроль качества перед приёмкой.

## Когда вызываюсь
Этап «ревью»: после тестирования.

## Вход
`ANALYZE.md`, `ARCHITECT.md`, код и тесты, список изменённых файлов.

## Что делаю
1. Сверяю реализацию со спецификацией: ничего не пропущено, ничего лишнего.
2. Проверяю стандарты кода (bsl-coding-standards) и результаты статанализа.
3. Оцениваю качество, граничные случаи, тестовое покрытие.
4. Выношу вердикт: принято / на доработку, с конкретными замечаниями.

## Выход
Файл `REVIEW.md` в каталоге задачи: вердикт, замечания по важности (критичные/важные/минорные).

## Используемые MCP
- `1c-syntax-checker-mcp` — статический анализ.
- `code-index` — поиск по коду.
- `1c-naparnic` — спорные вопросы по 1С.

## Границы
Только ревью (readonly). Код не правлю — возвращаю разработчику.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/content/agents app/tests/env/test_content_files.py
git commit -m "feat(env): шаблоны 5 субагентов"
```

---

## Task 2: Скилы и правила

**Files:**
- Create: `app/src/agentmon/env/content/skills/mcp-usage/SKILL.md`, `skills/bsl-coding-standards/SKILL.md`, `skills/sdd-tdd-workflow/SKILL.md`
- Create: `app/src/agentmon/env/content/rules/search-before-write.md`, `rules/verify-with-syntax-checker.md`, `rules/task-artifacts.md`
- Modify: `app/tests/env/test_content_files.py` (добавить проверки скилов и правил)

**Interfaces:**
- Consumes: `CONTENT` путь из Task 1 теста.
- Produces: 3 `skills/<name>/SKILL.md` (frontmatter `name`, `description`, `allowed-tools`) и 3 `rules/<name>.md` (frontmatter `name`, `description` + тело).

- [ ] **Step 1: Write the failing test (добавить в test_content_files.py)**

```python
SKILLS = {"mcp-usage", "bsl-coding-standards", "sdd-tdd-workflow"}
RULES = {"search-before-write", "verify-with-syntax-checker", "task-artifacts"}


def test_skills_present_and_valid():
    found = {p.name for p in (CONTENT / "skills").iterdir() if p.is_dir()}
    assert found == SKILLS
    for name in SKILLS:
        text = (CONTENT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
        assert "allowed-tools" in fm


def test_rules_present_and_valid():
    found = {p.stem for p in (CONTENT / "rules").glob("*.md")}
    assert found == RULES
    for name in RULES:
        text = (CONTENT / "rules" / f"{name}.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: FAIL (skills/rules отсутствуют).

- [ ] **Step 3: Создать скилы**

`app/src/agentmon/env/content/skills/mcp-usage/SKILL.md`:
```markdown
---
name: mcp-usage
description: Когда применять каждый из подключённых MCP-серверов 1С. Читай перед обращением к метаданным, статанализу, справке платформы, сложным вопросам или поиску по коду.
allowed-tools: []
---

# Использование MCP-серверов

Подбирай сервер под задачу:

| Нужно | Сервер |
|-------|--------|
| Структура/состав объектов метаданных | `1c-md` |
| Статический анализ BSL (ошибки, стиль) | `1c-syntax-checker-mcp` |
| Справка по платформе 1С (синтаксис, методы) | `bsl-platform-context` |
| Сложный/неоднозначный вопрос по 1С | `1c-naparnic` |
| Поиск по существующей кодовой базе | `code-index` |

Правила:
- Перед написанием нового кода ищи существующее через `code-index` и `1c-md`.
- После правок BSL прогоняй `1c-syntax-checker-mcp`.
- Не угадывай синтаксис платформы — спрашивай `bsl-platform-context`.
```

`app/src/agentmon/env/content/skills/bsl-coding-standards/SKILL.md`:
```markdown
---
name: bsl-coding-standards
description: Стандарты кода BSL (1С). Читай перед написанием или ревью кода на встроенном языке.
allowed-tools: []
---

# Стандарты кода BSL

## Именование
- Переменные и параметры — осмысленные имена на русском, в стиле КонецГода.
- Экспортные процедуры/функции — глагол + объект (СформироватьОтчёт).

## Структура модуля
- Раздел программного интерфейса (экспортные методы) — сверху.
- Служебные процедуры — ниже, в отдельном разделе.
- Обработчики событий — в своём разделе.

## Запросы
- Явно перечисляй поля, избегай `ВЫБРАТЬ *`.
- Накладывай отборы в запросе, а не в коде постобработки.
- Для больших выборок используй временные таблицы и индексы.

## Обработка ошибок
- Исключения — через `ВызватьИсключение` с понятным текстом.
- Не глотай ошибки пустым `Исключение ... КонецПопытки`.

## Комментарии
- Комментируй «почему», а не «что». Описание методов — в формате справки 1С.
```

`app/src/agentmon/env/content/skills/sdd-tdd-workflow/SKILL.md`:
```markdown
---
name: sdd-tdd-workflow
description: Методология разработки через спецификацию и тесты (SDD+TDD). Читай при планировании этапов задачи.
allowed-tools: []
---

# SDD + TDD

## Спецификация до кода (SDD)
Для новой функциональности и значимых изменений сначала спека (цель, требования,
критерии приёмки), затем техдизайн, только потом код.

## Тесты до реализации (TDD)
1. **Red** — тестировщик пишет юнит-тесты (YaxUnit) по критериям приёмки; они падают.
2. **Green** — разработчик пишет минимальный код, доводит тесты до прохождения.
3. **Расширение** — тестировщик добавляет граничные случаи и регрессии.

## Слои тестов
- Серверная логика → YaxUnit (юнит-тесты).
- Прогоняй статический анализ (`1c-syntax-checker-mcp`) на каждом шаге.

## Цикл задачи
анализ → план → создание тестов → разработка → тестирование → ревью → документация.
```

- [ ] **Step 4: Создать правила**

`app/src/agentmon/env/content/rules/search-before-write.md`:
```markdown
---
name: search-before-write
description: Перед написанием нового кода искать существующее.
---

# Поиск перед написанием

Перед созданием новой процедуры, функции или объекта метаданных:
1. Найди существующие аналоги через `code-index`.
2. Проверь метаданные через `1c-md`.
3. Переиспользуй или расширяй существующее, если это уместно.

Дублирование логики — повод остановиться и поискать ещё раз.
```

`app/src/agentmon/env/content/rules/verify-with-syntax-checker.md`:
```markdown
---
name: verify-with-syntax-checker
description: После правок BSL прогонять статический анализ.
---

# Проверка статическим анализом

После каждого изменения BSL-кода прогоняй `1c-syntax-checker-mcp` и устраняй
найденные ошибки до перехода к следующему шагу. Не считай задачу готовой, пока
статанализ не чист.
```

`app/src/agentmon/env/content/rules/task-artifacts.md`:
```markdown
---
name: task-artifacts
description: Каждый субагент оставляет результат этапа в каталоге задачи.
---

# Артефакты задачи

Каждый субагент по завершении этапа:
1. Записывает результат в файл этапа в каталоге задачи
   (`ANALYZE.md`, `ARCHITECT.md`, `DEVELOP.md`, `TEST.md`, `REVIEW.md`).
2. Указывает статус и список изменённых файлов.

Это обеспечивает передачу контекста между этапами и прозрачность хода задачи.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/content/skills app/src/agentmon/env/content/rules app/tests/env/test_content_files.py
git commit -m "feat(env): скилы-руководства и правила"
```

---

## Task 3: Хук bsl_nudge.py

**Files:**
- Create: `app/src/agentmon/env/content/hooks/bsl_nudge.py`
- Test: `app/tests/env/test_bsl_nudge.py`

**Interfaces:**
- Produces: `build_output(event: dict) -> dict` — для `Edit/Write/MultiEdit` над `*.bsl` возвращает `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}`; иначе `{}`. `main()` читает stdin-JSON, печатает результат.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_bsl_nudge.py
import importlib.util
from pathlib import Path

HOOK = (Path(__file__).resolve().parents[2] / "src" / "agentmon" / "env"
        / "content" / "hooks" / "bsl_nudge.py")


def _load():
    spec = importlib.util.spec_from_file_location("bsl_nudge", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bsl_edit_nudges():
    mod = _load()
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": "/p/Module.bsl"}})
    assert "1c-syntax-checker-mcp" in out["hookSpecificOutput"]["additionalContext"]


def test_non_bsl_is_silent():
    mod = _load()
    assert mod.build_output({"tool_input": {"file_path": "/p/readme.md"}}) == {}


def test_missing_input_is_silent():
    mod = _load()
    assert mod.build_output({}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_bsl_nudge.py -q`
Expected: FAIL (файла хука нет).

- [ ] **Step 3: Создать хук**

```python
# app/src/agentmon/env/content/hooks/bsl_nudge.py
#!/usr/bin/env python3
"""PostToolUse-хук: напоминает прогнать статанализ после правки *.bsl."""
import json
import sys


def _paths(tool_input: dict) -> list:
    out = []
    for key in ("file_path", "path", "notebook_path"):
        val = tool_input.get(key)
        if isinstance(val, str):
            out.append(val)
    return out


def build_output(event: dict) -> dict:
    tool_input = event.get("tool_input") or {}
    if any(p.lower().endswith(".bsl") for p in _paths(tool_input)):
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "[ai1c] Изменён BSL-модуль — прогони статический анализ "
                "(навык mcp-usage, MCP 1c-syntax-checker-mcp)."),
        }}
    return {}


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    out = build_output(event)
    if out:
        json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_bsl_nudge.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/content/hooks/bsl_nudge.py app/tests/env/test_bsl_nudge.py
git commit -m "feat(env): хук-подсказка статанализа для BSL"
```

---

## Task 4: Модуль развёртывания content.py

**Files:**
- Create: `app/src/agentmon/env/content.py`
- Test: `app/tests/env/test_content_deploy.py`

**Interfaces:**
- Consumes: `EnvConfig`, `AgentModel` (config_schema); `write_preserving` (scaffold).
- Produces: `deploy_content(config, *, update: bool) -> None` — копирует `content/{skills,rules,hooks}` в `<project>/.claude/`, рендерит `agents/*.md` (подстановка `{{MODEL}}`/`{{EFFORT}}` из `config.agents`, дефолт для отсутствующих), пишет `<project>/.claude/settings.json` и `<project>/CLAUDE.md` через `write_preserving`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_content_deploy.py
from pathlib import Path
from agentmon.env.config_schema import EnvConfig, AgentModel, SCHEMA_VERSION
from agentmon.env import content


def cfg(tmp_path, agents):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="iv", developer_email="iv@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="", mcp=[], agents=agents,
    )


def test_deploy_copies_content(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    c = tmp_path / ".claude"
    assert (c / "agents" / "developer.md").exists()
    assert (c / "skills" / "mcp-usage" / "SKILL.md").exists()
    assert (c / "rules" / "task-artifacts.md").exists()
    assert (c / "hooks" / "bsl_nudge.py").exists()
    assert (c / "settings.json").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_agent_model_effort_rendered(tmp_path):
    agents = [AgentModel("developer", "claude-opus-4-8", "high")]
    content.deploy_content(cfg(tmp_path, agents), update=False)
    text = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "{{MODEL}}" not in text and "{{EFFORT}}" not in text
    assert "claude-opus-4-8" in text and "high" in text


def test_agent_without_config_gets_default(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    text = (tmp_path / ".claude" / "agents" / "analyst.md").read_text(encoding="utf-8")
    assert "{{MODEL}}" not in text


def test_update_backs_up_claude_md(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    (tmp_path / "CLAUDE.md").write_text("мой текст\n", encoding="utf-8")
    content.deploy_content(cfg(tmp_path, []), update=True)
    assert (tmp_path / "CLAUDE.md.bak").read_text(encoding="utf-8") == "мой текст\n"


def test_settings_registers_hook(tmp_path):
    import json
    content.deploy_content(cfg(tmp_path, []), update=False)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "bsl_nudge.py" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_deploy.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.content).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/content.py
import json
from pathlib import Path

from .scaffold import write_preserving

CONTENT_DIR = Path(__file__).parent / "content"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_EFFORT = "medium"
_RULES = ("search-before-write", "verify-with-syntax-checker", "task-artifacts")
_AGENTS = ("analyst", "architect", "developer", "tester", "reviewer")


def _copy_tree(src: Path, dst: Path) -> None:
    for item in sorted(src.rglob("*")):
        target = dst / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")


def _model_effort(config, name):
    for a in config.agents:
        if a.agent == name:
            return a.model, a.effort
    return _DEFAULT_MODEL, _DEFAULT_EFFORT


def _render_agents(config, agents_dst: Path) -> None:
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src in sorted((CONTENT_DIR / "agents").glob("*.md")):
        model, effort = _model_effort(config, src.stem)
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{MODEL}}", model).replace("{{EFFORT}}", effort)
        (agents_dst / src.name).write_text(text, encoding="utf-8")


def _render_settings() -> str:
    settings = {"hooks": {"PostToolUse": [{
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command",
                   "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/bsl_nudge.py"'}],
    }]}}
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"


def _render_claude_md(config) -> str:
    rules = "\n".join(f"- @.claude/rules/{n}.md" for n in _RULES)
    agents = "\n".join(f"- {n}" for n in _AGENTS)
    return (
        f"# {config.project_name}\n\n"
        f"Разработчик: {config.developer_id} <{config.developer_email}>\n"
        f"Платформа 1С: {config.platform_version} ({config.platform_dir})\n\n"
        f"## Правила\n{rules}\n\n"
        f"## Субагенты\n{agents}\n\n"
        "## Цикл задачи\n"
        "анализ → план → создание тестов → разработка → тестирование → ревью → документация\n"
    )


def deploy_content(config, *, update: bool) -> None:
    claude = Path(config.project_dir) / ".claude"
    for sub in ("skills", "rules", "hooks"):
        _copy_tree(CONTENT_DIR / sub, claude / sub)
    _render_agents(config, claude / "agents")
    write_preserving(claude / "settings.json", _render_settings(), update=update)
    write_preserving(Path(config.project_dir) / "CLAUDE.md",
                     _render_claude_md(config), update=update)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_deploy.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/content.py app/tests/env/test_content_deploy.py
git commit -m "feat(env): развёртывание содержимого окружения (content.py)"
```

---

## Task 5: Интеграция в установщик №1

**Files:**
- Modify: `app/src/agentmon/env/installer.py` (шаг `claude` → `content`; удалить `_claude_md`; импорт `deploy_content`)
- Modify: `app/tests/env/test_installer.py` (добавить проверку развёрнутого контента)

**Interfaces:**
- Consumes: `deploy_content` (content).
- Produces: установщик на шаге `content` разворачивает содержимое; шаги layout/config/mcp/dump/register без изменений.

- [ ] **Step 1: Обновить тест установщика**

В `app/tests/env/test_installer.py`, в `test_install_writes_config_and_registers`, после строки `assert (tmp_path / "CLAUDE.md").exists()` добавить:

```python
    assert (tmp_path / ".claude" / "agents" / "developer.md").exists()
    assert (tmp_path / ".claude" / "hooks" / "bsl_nudge.py").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert any(e.step == "content" and e.status == "ok" for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_installer.py -q`
Expected: FAIL (нет шага `content` / нет `.claude/agents/developer.md`).

- [ ] **Step 3: Изменить installer.py**

В `app/src/agentmon/env/installer.py`:

1. Заменить импорт: убрать зависимость от `_claude_md`-логики, добавить:
```python
from .content import deploy_content
```
2. Удалить функцию `_claude_md` (её рендеринг переехал в `content.py`).
3. В списке `steps` заменить строку шага `claude`:
```python
        ("claude", lambda: write_preserving(base / "CLAUDE.md",
                                            _claude_md(config), update=update)),
```
на:
```python
        ("content", lambda: deploy_content(config, update=update)),
```
(Строки `write_preserving` и `Path` в installer.py могут стать неиспользуемыми — если так, убери их импорты.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_installer.py -q`
Expected: PASS.

- [ ] **Step 5: Прогнать весь набор**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все; установщик теперь разворачивает контент).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/installer.py app/tests/env/test_installer.py
git commit -m "feat(env): установщик разворачивает содержимое окружения"
```

---

## Self-Review

**Spec coverage:**
- 5 субагентов → Task 1. Скилы (3) → Task 2. Правила (3) → Task 2. Хук → Task 3.
- settings.json / CLAUDE.md рендеринг → Task 4 (content.py). Подстановка model/effort → Task 4.
- Копирование (не симлинки), без RUS-ENG зеркала → Task 4 (`_copy_tree`, одно дерево).
- update: бэкап CLAUDE.md/settings.json, перезапись agents/skills/rules/hooks → Task 4 (`write_preserving` + копирование шаблона).
- Интеграция в установщик (шаг claude → content) → Task 5.
- Тесты (валидация контента, хук, deploy, интеграция) → Task 1-5.

**Placeholder scan:** контент файлов полный; `{{MODEL}}`/`{{EFFORT}}` — намеренные плейсхолдеры шаблона, подставляются в Task 4. В Task 4 Step 5 исправить опечатку в сообщении коммита.

**Type consistency:** `deploy_content(config, *, update)`, `_model_effort`, `_render_*` согласованы; `AgentModel.agent/model/effort` и `EnvConfig.agents` совпадают с №1; `write_preserving(path, content, *, update)` — сигнатура из №1.

**Отложено (вне №2):** жизненный цикл задачи и `tasks/task#id` (№3); операционные тул-скилы 1С; `permissions` в settings.json (добавим при интеграции MCP); выбор `python3` vs `python` в команде хука — кросс-платформенный нюанс, зафиксирован для триажа.
