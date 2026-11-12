# Условное окружение под MCP `1c-md`: `validate_query` — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При разворачивании проекта с включённым MCP вида `1c-md`/`1c-md-queries` дополнять `mcp-usage` описанием `validate_query` и делать его первым слоем проверки в `query-analyze`.

**Architecture:** В текстах `template/.claude` появляются условные блоки `<!-- @if 1c-md -->…<!-- @endif -->`. Существующий проход `content.py` по текстовым файлам шаблона рендерит их по составу `config.mcp` и пишет изменённые файлы на цель — при создании и при `update-env`.

**Tech Stack:** Python 3.10+, pytest, markdown-шаблоны. Новых зависимостей нет.

## Global Constraints

- Источник истины для условия — `config.mcp` (`McpSelection.id` ∈ {`1c-md`, `1c-md-queries`}, `enabled=True`), не `.mcp.json`.
- Условие одно — `1c-md`; без вложенности, выражений и общего шаблонизатора.
- Контент шаблона — на русском, в тоне существующих навыков.
- Маркеры не должны попадать в развёрнутый проект; незакрытый/вложенный блок — `ValueError` с путём к файлу.
- `validate_query` в тексте описан как «если доступен»; локальный анализатор `query-analyze` остаётся.
- Существующие тесты `tests/env/test_content_deploy.py`, в т.ч. `test_skill_docs_use_venv_python`, должны остаться зелёными.
- Коммиты — conventional style, в конце сообщения строка `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

### Соглашение о маркерах

В шаблоне `@if` стоит **сразу после** строки-разделителя (без пустой строки
перед маркером), первая строка внутри блока — пустая (отбивка абзаца), `@endif` —
сразу после последней строки контента; пустая строка после `@endif` остаётся.

```
предыдущая строка
<!-- @if 1c-md -->

## Заголовок
контент
<!-- @endif -->

следующая строка
```

Для строк таблицы/списка пустых строк внутри блока нет:

```
| a |
<!-- @if 1c-md -->
| b |
<!-- @endif -->
| c |
```

### Файловая структура

- `app/src/agentmon/env/content.py` — рендер условных блоков и интеграция в деплой.
- `app/tests/env/test_content_conditions.py` — новый файл тестов.
- `template/.claude/skills/mcp-usage/SKILL.md` — условное описание `1c-md`.
- `template/.claude/skills/query-analyze/SKILL.md` — условная преамбула про `validate_query`.

---

### Task 1: Рендер условных блоков

**Files:**
- Modify: `app/src/agentmon/env/content.py:22` (после `_PY_INVOKE`)
- Test: `app/tests/env/test_content_conditions.py` (create)

**Interfaces:**
- Produces: `_render_conditional_blocks(text: str, has_1c_md: bool, *, filename: str = "") -> str` — оставляет или вырезает блоки `<!-- @if 1c-md -->…<!-- @endif -->`; бросает `ValueError` на неизвестном условии, незакрытом или лишнем маркере.

- [ ] **Step 1: Write the failing tests**

Создать `app/tests/env/test_content_conditions.py`:

```python
# app/tests/env/test_content_conditions.py
from pathlib import Path

import pytest

from agentmon.backends.local import LocalProvisioner
from agentmon.env import content
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION, McpSelection


def cfg(tmp_path, mcp):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="iv", developer_email="iv@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="",
        mcp=mcp, agents=[],
    )


def sel(mcp_id, *, enabled=True, connection=None):
    return McpSelection(id=mcp_id, enabled=enabled, mode="managed",
                        connection=connection)


def skill_text(tmp_path, name):
    return (Path(tmp_path) / ".claude" / "skills" / name / "SKILL.md"
            ).read_text(encoding="utf-8")


# --- рендер маркеров ---

def test_render_conditionals_keeps_block_when_true():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, True, filename="x.md") == "до\n\nвнутри\n\nпосле\n"


def test_render_conditionals_drops_block_when_false():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, False, filename="x.md") == "до\n\nпосле\n"


def test_render_conditionals_inline_rows():
    text = "| a |\n<!-- @if 1c-md -->\n| b |\n<!-- @endif -->\n| c |\n"
    assert content._render_conditional_blocks(
        text, True, filename="x.md") == "| a |\n| b |\n| c |\n"
    assert content._render_conditional_blocks(
        text, False, filename="x.md") == "| a |\n| c |\n"


def test_render_conditionals_without_markers_unchanged():
    text = "обычный текст\n"
    assert content._render_conditional_blocks(
        text, True, filename="x.md") == text


def test_render_conditionals_unclosed_marker_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "<!-- @if 1c-md -->\nтекст\n", True, filename="x.md")


def test_render_conditionals_orphan_endif_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "текст\n<!-- @endif -->\n", True, filename="x.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: FAIL — `AttributeError: module 'agentmon.env.content' has no attribute '_render_conditional_blocks'`.

- [ ] **Step 3: Implement the renderer**

В `app/src/agentmon/env/content.py` сразу после определения `_PY_INVOKE` (строка 22) добавить:

```python
# Условные блоки шаблона: <!-- @if 1c-md --> … <!-- @endif -->. Маркер @if
# стоит сразу после строки-разделителя (без пустой строки перед ним), первая
# строка внутри блока — пустая для отбивки абзаца, @endif — сразу после
# последней строки контента; пустая строка после @endif остаётся в шаблоне.
_CONDITIONAL_BLOCK = re.compile(
    r"^<!-- @if (?P<cond>[a-z0-9_-]+) -->\n(?P<body>.*?)^<!-- @endif -->\n",
    re.MULTILINE | re.DOTALL,
)


def _render_conditional_blocks(text: str, has_1c_md: bool, *,
                               filename: str = "") -> str:
    """Оставляет/вырезает условные блоки шаблона по составу MCP проекта.

    Сейчас условие одно: `1c-md` — включён MCP вида `1c-md` или
    `1c-md-queries`. Незакрытый, вложенный или лишний маркер — ValueError:
    маркеры не должны попасть в развёрнутый проект.
    """
    conditions = {"1c-md": has_1c_md}

    def repl(match: re.Match) -> str:
        cond = match.group("cond")
        if cond not in conditions:
            raise ValueError(
                f"неизвестное условие {cond!r} в {filename or '<текст>'}")
        return match.group("body") if conditions[cond] else ""

    rendered = _CONDITIONAL_BLOCK.sub(repl, text)
    if "<!-- @if " in rendered or "<!-- @endif -->" in rendered:
        raise ValueError(
            f"несбалансированный условный блок в {filename or '<текст>'}: "
            "@if/@endif должны быть парными и не вложенными")
    return rendered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: PASS — 6 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/content.py app/tests/env/test_content_conditions.py
git commit -m "$(cat <<'EOF'
feat(env): рендер условных блоков шаблона по составу MCP

Маркеры <!-- @if 1c-md -->…<!-- @endif --> в текстах template/.claude
будут оставлять или вырезать фрагмент в зависимости от того, включён ли
в карточке проекта MCP вида 1c-md или 1c-md-queries.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Интеграция в деплой + условное описание в `mcp-usage`

**Files:**
- Modify: `app/src/agentmon/env/content.py:65-90` (`_apply_mcp_names` → `_render_template_texts`), `:119-134` (`_rewrite_python_invocations`), `:167-198` (`deploy_content`)
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`
- Test: `app/tests/env/test_content_conditions.py` (append)

**Interfaces:**
- Consumes: `_render_conditional_blocks(...)` из Task 1.
- Produces: `_render_template_texts(prov, claude_dir, overrides, *, has_1c_md: bool, py_cmd: str) -> None`; `_rewrite_python_text(text: str, py_cmd: str) -> str`.

- [ ] **Step 1: Write the failing deploy tests**

Дописать в `app/tests/env/test_content_conditions.py`:

```python
# --- деплой: mcp-usage ---

def test_deploy_1c_md_adds_validate_query_to_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" in text
    assert "загружены в БД" in text
    assert "<!-- @if" not in text and "<!-- @endif" not in text


def test_deploy_1c_md_queries_also_adds_section(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md-queries")]),
        update=False)
    assert "validate_query" in skill_text(tmp_path, "mcp-usage")


def test_deploy_without_1c_md_has_no_validate_query_in_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("bsl-ls")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" not in text
    assert "<!-- @if" not in text


def test_deploy_disabled_1c_md_has_no_validate_query(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md", enabled=False)]),
        update=False)
    assert "validate_query" not in skill_text(tmp_path, "mcp-usage")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: FAIL — `assert 'validate_query' in ...` (секции в шаблоне ещё нет); тесты рендера из Task 1 проходят.

- [ ] **Step 3: Wire the renderer into deploy**

В `app/src/agentmon/env/content.py`:

3a. Добавить helper перед `_rewrite_python_invocations`:

```python
def _rewrite_python_text(text: str, py_cmd: str) -> str:
    """Заменяет вызовы `python …` на интерпретатор .venv проекта."""
    return _PY_INVOKE.sub(lambda _m: py_cmd + " ", text)
```

3b. В `_rewrite_python_invocations` заменить тело подстановки:

```python
        new = _rewrite_python_text(text, py_cmd)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}", new)
```

3c. Переименовать `_apply_mcp_names` → `_render_template_texts`, добавить параметры `has_1c_md` и `py_cmd`, рендерить блоки и применять подстановку интерпретатора при записи:

```python
def _render_template_texts(prov, claude_dir, overrides, *,
                           has_1c_md: bool, py_cmd: str) -> None:
    """Подставляет имена MCP и рендерит условные блоки — пишем на цель.

    Обходим текстовые файлы шаблона .claude на мониторе; меняем и пишем на цель
    только изменившиеся. Агенты и settings.json пропускаем: агенты обрабатываются
    в _render_agents (с учётом model/effort), settings.json — через write_preserving.
    При записи применяется и подстановка интерпретатора .venv: файл с условными
    блоками (query-analyze) содержит вызовы `python …`.
    """
    for src in sorted(CONTENT_DIR.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(CONTENT_DIR)
        if "__pycache__" in rel.parts:
            continue
        # agents/ обрабатываются в _render_agents; settings.json — через write_preserving
        if rel.parts[:1] == ("agents",) or rel.parts == ("settings.json",):
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        new = _render_conditional_blocks(
            new, has_1c_md, filename=rel.as_posix())
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}",
                            _rewrite_python_text(new, py_cmd))
```

3d. В `deploy_content` вычислить условие и заменить вызов:

```python
    mcp_subs = mcp_name_overrides(config.mcp)
    subs = {**mcp_subs, "{{CODE_INDEX_REPO}}": config.project_name}
    has_1c_md = any(
        getattr(sel, "enabled", False)
        and sel.id in ("1c-md", "1c-md-queries")
        for sel in config.mcp
    )
```

```python
    _render_template_texts(prov, claude, subs, has_1c_md=has_1c_md,
                           py_cmd=_py_cmd(prov, project_dir))
```

- [ ] **Step 4: Add the conditional content to `mcp-usage/SKILL.md`**

4a. Вводная фраза. Заменить:

```markdown
Четыре сервера, каждый закрывает свой класс задач. Общий принцип: **не читай сырой XML/код руками и не угадывай** — спроси тот сервер, который держит нужный факт в индексе или в справочнике.
```

на:

```markdown
Серверы ниже, каждый закрывает свой класс задач. Общий принцип: **не читай сырой XML/код руками и не угадывай** — спроси тот сервер, который держит нужный факт в индексе или в справочнике.
```

4b. Строка таблицы. Заменить:

```markdown
| Справка по API платформы (типы, методы, свойства, конструкторы) | `1c_platform` | `search` → `info` |
| Статический анализ BSL (ошибки, стандарты) | `bsl_ls` | `check` |
```

на:

```markdown
| Справка по API платформы (типы, методы, свойства, конструкторы) | `1c_platform` | `search` → `info` |
<!-- @if 1c-md -->
| Проверить синтаксис запроса по метаданным ИБ | `1c-md` | `validate_query` |
<!-- @endif -->
| Статический анализ BSL (ошибки, стандарты) | `bsl_ls` | `check` |
```

4c. Секция после `1c_platform`. Заменить:

```markdown
Маршрут: не знаешь имя → `search`; знаешь тип, нужен весь API → `getMembers`; знаешь элемент → `info`/`getMember`; создаёшь объект → `getConstructors`.

---

## `bsl_ls` — статический анализ BSL
```

на:

```markdown
Маршрут: не знаешь имя → `search`; знаешь тип, нужен весь API → `getMembers`; знаешь элемент → `info`/`getMember`; создаёшь объект → `getConstructors`.
<!-- @if 1c-md -->

## `1c-md` — метаданные и проверка запросов платформой

Расширение 1С с HTTP-сервисом `mcp_APIBackend` на веб-публикации базы. В отличие
от `code_index`, работает не с XML-исходниками, а с **актуальными метаданными
информационной базы**.

- **`validate_query`** (`queryText` — текст запроса) — проверка синтаксиса
  платформой (`СхемаЗапроса.УстановитьТекстЗапроса`), без выполнения и без
  обращения к данным. Возвращает `valid` и `message`. Это самый точный слой
  проверки синтаксиса и имён: проверяет сама платформа по составу текущей ИБ.

**Важно: `validate_query` знает только метаданные, загруженные в БД.** Если в
ходе разработки метаданные менялись в XML-исходниках и ещё не загружены в
информационную базу, инструмент про них не знает: запрос с новыми реквизитами,
табличными частями или объектами получит ошибку «не найдено», хотя в исходниках
корректен. Тогда:

1. сверь новые имена с XML-исходниками (`meta-info`, `code_index`);
2. не переписывай корректный запрос под устаревшую БД;
3. после загрузки изменений в ИБ повтори `validate_query` — ошибка уйдёт.

`validate_query` не заменяет `query-analyze`: он не проверяет стилевые и
оптимизационные стандарты запросов.
<!-- @endif -->

---

## `bsl_ls` — статический анализ BSL
```

4d. Рецепт. Заменить:

```markdown
- **«Как правильно вызвать метод платформы?»** → `1c_platform search` → `info`/`getMembers`.
- **«Проверить написанный код»** → `bsl_ls check` (с `config` из проекта); концептуальные сомнения — `1c_naparnic ask_1c_ai`.
```

на:

```markdown
- **«Как правильно вызвать метод платформы?»** → `1c_platform search` → `info`/`getMembers`.
<!-- @if 1c-md -->
- **«Проверить синтаксис запроса»** → `1c-md validate_query` (по метаданным ИБ; если метаданные ещё не загружены — ошибки про новые имена ожидаемы), затем `query-analyze` для стилевых правил.
<!-- @endif -->
- **«Проверить написанный код»** → `bsl_ls check` (с `config` из проекта); концептуальные сомнения — `1c_naparnic ask_1c_ai`.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: PASS — все тесты, включая 4 новых.

- [ ] **Step 6: Commit**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/content.py \
        app/tests/env/test_content_conditions.py \
        template/.claude/skills/mcp-usage/SKILL.md
git commit -m "$(cat <<'EOF'
feat(env): описание 1c-md и validate_query в mcp-usage при наличии MCP

При включённом в карточке проекта MCP вида 1c-md или 1c-md-queries
секция про validate_query попадает в mcp-usage; без него — не попадает.
Рендер условных блоков встроен в проход по текстовым файлам шаблона,
запись применяет и подстановку интерпретатора .venv.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `validate_query` первым слоем в `query-analyze`

**Files:**
- Modify: `template/.claude/skills/query-analyze/SKILL.md:12-17`
- Test: `app/tests/env/test_content_conditions.py` (append)

**Interfaces:**
- Consumes: готовый рендер и интеграция из Task 2.
- Produces: в развёрнутом `query-analyze/SKILL.md` — преамбула с `mcp__1c-md__validate_query` (имя сервера подставляется существующим `mcp_name_overrides`).

- [ ] **Step 1: Write the failing tests**

Дописать в `app/tests/env/test_content_conditions.py`:

```python
# --- деплой: query-analyze и переходы при обновлении ---

def test_deploy_1c_md_makes_validate_query_first_layer(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__1c-md__validate_query" in text
    assert "analyze_query.py" in text          # локальные проверки остались
    assert "<!-- @if" not in text


def test_deploy_1c_md_queries_makes_validate_query_first_layer(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md-queries")]),
        update=False)
    assert "mcp__1c-md__validate_query" in skill_text(tmp_path, "query-analyze")


def test_deploy_without_1c_md_keeps_query_analyze_as_is(tmp_path):
    content.deploy_content(LocalProvisioner(), cfg(tmp_path, []), update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "validate_query" not in text
    assert "analyze_query.py" in text


def test_update_adds_then_removes_1c_md_blocks(tmp_path):
    prov = LocalProvisioner()
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    assert "validate_query" not in skill_text(tmp_path, "query-analyze")

    content.deploy_content(prov, cfg(tmp_path, [sel("1c-md")]), update=True)
    assert "validate_query" in skill_text(tmp_path, "query-analyze")
    assert "validate_query" in skill_text(tmp_path, "mcp-usage")

    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    assert "validate_query" not in skill_text(tmp_path, "query-analyze")
    assert "validate_query" not in skill_text(tmp_path, "mcp-usage")


def test_renamed_1c_md_server_name_substituted(tmp_path):
    conn = ('"my_md": {"type": "http", '
            '"url": "http://localhost/base/hs/mcp"}')
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md", connection=conn)]),
        update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__my_md__validate_query" in text
    assert "mcp__1c-md__validate_query" not in text


def test_conditional_render_keeps_venv_python(tmp_path):
    prov = LocalProvisioner()
    content.deploy_content(prov, cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "query-analyze")
    expected = content._shell_path(content.venv_python(prov, str(tmp_path)))
    assert expected in text


def test_no_conditional_markers_leak_into_project(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md-queries")]),
        update=False)
    for path in (Path(tmp_path) / ".claude").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "<!-- @if" not in text, path
        assert "<!-- @endif" not in text, path


def test_template_markers_are_balanced():
    for path in content.CONTENT_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        content._render_conditional_blocks(text, True, filename=str(path))
        content._render_conditional_blocks(text, False, filename=str(path))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: FAIL — `assert 'mcp__1c-md__validate_query' in ...` для query-analyze; остальные тесты из Task 1-2 проходят.

- [ ] **Step 3: Add the conditional preamble to `query-analyze/SKILL.md`**

Заменить:

```markdown
Находит нарушения стандартов разработки оптимальных запросов (ИТС).
Работает в два шага: извлечение текста запроса из `.bsl`/СКД-XML и прогон
реестра автоматических проверок.

## Извлечение запросов
```

на:

```markdown
Находит нарушения стандартов разработки оптимальных запросов (ИТС).
Работает в два шага: извлечение текста запроса из `.bsl`/СКД-XML и прогон
реестра автоматических проверок.
<!-- @if 1c-md -->

## Приоритетная проверка: `validate_query`

Если доступен MCP `1c-md` с инструментом `validate_query` (полное имя
инструмента — `mcp__1c-md__validate_query`; при переименованном сервере —
`mcp__<имя>__validate_query`), каждый извлечённый текст запроса сначала
проверяется платформой:

1. Извлеки запросы — как описано ниже.
2. Вызови `validate_query` с `{"queryText": "<текст запроса>"}`.
   - `valid: true` — синтаксис принят платформой.
   - `valid: false` — разбери `message` и исправь ошибку.
3. Затем прогони локальный `analyze_query.py` — он проверяет стилевые и
   оптимизационные правила, которых `validate_query` не делает.

**Ограничение `validate_query`:** он проверяет по метаданным, загруженным в
информационную базу. Если метаданные правились в XML-исходниках и ещё не
загружены в БД, новые реквизиты, табличные части или объекты вызовут ложные
ошибки «не найдено». Такие имена сверяй с XML (`meta-info`, `code_index`), а не
переписывай корректный запрос под устаревшую БД. После загрузки изменений в ИБ
повтори проверку.

Если `validate_query` недоступен (MCP не подключён или в сборке расширения нет
инструмента) — работай по локальному анализатору, как описано ниже.
<!-- @endif -->

## Извлечение запросов
```

- [ ] **Step 4: Run the focused tests**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py -v`

Expected: PASS — все тесты файла.

- [ ] **Step 5: Run the content regression suites**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest tests/env/test_content_conditions.py tests/env/test_content_deploy.py tests/env/test_content.py -q`

Expected: PASS. Особое внимание — `test_skill_docs_use_venv_python` (путь к `.venv` не затёрт рендером маркеров).

- [ ] **Step 6: Run the full suite**

Run: `cd /home/uam/projects/ai_template/app && python -m pytest -q`

Expected: PASS, без новых падений относительно baseline.

- [ ] **Step 7: Commit**

```bash
cd /home/uam/projects/ai_template
git add template/.claude/skills/query-analyze/SKILL.md \
        app/tests/env/test_content_conditions.py
git commit -m "$(cat <<'EOF'
feat(env): validate_query первым слоем проверки в query-analyze

При включённом MCP 1c-md/1c-md-queries навык query-analyze сначала
проверяет каждый текст запроса платформенным validate_query, затем
гоняет локальные стилевые правила; без инструмента — прежний путь.
Предупреждение о метаданных, ещё не загруженных в БД, — в обоих навыках.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

## Самопроверка плана

- **Покрытие спеки:** триггер по `config.mcp` — Task 2 Step 3d; оба вида — тесты Task 2/3; маркеры и ошибки — Task 1; `mcp-usage` — Task 2; `query-analyze` — Task 3; fallback и предупреждение о БД — Task 3 Step 3; `update-env` в обе стороны — Task 3 Step 1; переименование сервера — Task 3 Step 1; отсутствие утечки маркеров — Task 3 Step 1.
- **Плейсхолдеры:** нет TODO/TBD; весь код и тексты приведены целиком.
- **Согласованность сигнатур:** `_render_conditional_blocks(text, has_1c_md, *, filename)` используется в Task 1, 2 и 3 одинаково; `_render_template_texts(..., has_1c_md, py_cmd)` — в Task 2 и вызывается из `deploy_content`.
