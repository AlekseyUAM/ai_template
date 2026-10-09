# Подстановка актуальных имён MCP в разворачиваемый шаблон

Дата: 2026-10-08

## Проблема

В `template/.claude` имена MCP-серверов захардкожены в нескольких файлах:

- `agents/*.md` — frontmatter `tools:` (`mcp__1c_naparnic__*, mcp__bsl_ls__*, mcp__1c_platform__*, mcp__code_index__*`);
- `settings.json` — список разрешённых серверов (`mcp__1c_naparnic`, `mcp__bsl_ls`, `mcp__1c_platform`, `mcp__code_index`);
- `hooks/bsl_nudge.py`, `rules/verify-with-syntax-checker.md`, `rules/search-before-write.md`,
  `skills/mcp-usage/SKILL.md`, `agents/reviewer.md` (тело) — упоминания в тексте
  (`mcp__bsl_ls__check`, `` `bsl_ls` ``, «MCP bsl_ls» и т.п.).

Четыре плейсхолдера: `1c_naparnic`, `bsl_ls`, `1c_platform`, `code_index`.

Если при создании проекта пользователь переименовал MCP в справочнике (поле
«Имя в .mcp.json»), то имя сервера в сгенерированном `.mcp.json` расходится с
этими плейсхолдерами. Тогда агенты ссылаются на несуществующий сервер
(`mcp__bsl_ls__*`), а текстовые подсказки в скилах/правилах указывают неверное имя.

## Цель

При создании проекта подставлять в скопированные файлы шаблона актуальные имена
выбранных MCP-серверов. Если MCP данного типа не выбран — плейсхолдер оставляем
как есть.

Решения, принятые при обсуждении:

- **Область замены:** везде, где встречается имя (frontmatter `tools:`,
  `settings.json` и текстовые упоминания в hooks/skills/rules).
- **Когда:** только при создании (`deploy_content(update=False)`), не при обновлении
  версии окружения.
- **Конвенция имён:** оставляем подчёркивания (`bsl_ls` и т.д.) — правим только
  по факту переименования пользователем; дефолты и шаблон не трогаем.

## Соответствие плейсхолдер → актуальное имя

Каждый плейсхолдер — это дефолтное значение `mcp_name` соответствующего вида MCP
(`env/mcp_types.py`). Вид выбранного MCP хранится в колонке `standard_key` строки
`mcp_servers` (его туда кладёт справочник: `mcp.js` → `standard_key: t.key`).

| тип (`standard_key`) | дефолтный `mcp_name` (плейсхолдер) |
|----------------------|-------------------------------------|
| `bsl-ls`             | `bsl_ls`                            |
| `1c-platform`        | `1c_platform`                       |
| `1c-naparnic`        | `1c_naparnic`                       |
| `code-index`         | `code_index`                        |

Актуальное имя выбранного MCP — это ключ сервера, который `build_mcp_json` пишет в
`.mcp.json`: имя из `connection_json` (если задан), иначе `standard_key`/`name`.

Правило: для каждого **выбранного** MCP формируем пару `{плейсхолдер: актуальное}`
только если у вида есть дефолтный `mcp_name` **и** актуальное имя отличается от
плейсхолдера. Виды без выбранного MCP пары не дают → плейсхолдер остаётся.

## Архитектура

### 1. `env/mcp_catalog.py` — вычисление имён

Выделяем из `build_mcp_json` приватный помощник имени сервера, чтобы и генерация
`.mcp.json`, и карта подстановок считали имя одинаково (единый источник истины):

```python
def _server_name(sel) -> str:
    connection = getattr(sel, "connection", None)
    if connection:
        name, _ = _parse_connection(connection, sel.id)
        return name
    return sel.id   # external/http/stdio — ключ по sel.id (standard_key или name)
```

`build_mcp_json` использует `_server_name` для ключа сервера (поведение не меняется).

Новая функция:

```python
def mcp_name_overrides(selections) -> dict[str, str]:
    """{плейсхолдер: актуальное_имя} для включённых выбранных MCP.

    Плейсхолдер — дефолтный mcp_name вида (mcp_types). Пары, где актуальное имя
    совпадает с плейсхолдером или вид неизвестен/без дефолта, пропускаются.
    """
    from .mcp_types import get_type          # локальный импорт: без цикла
    overrides = {}
    for sel in selections:
        if not getattr(sel, "enabled", False):
            continue
        try:
            placeholder = get_type(sel.id).defaults.get("mcp_name")
        except KeyError:
            placeholder = None
        if not placeholder:
            continue
        actual = _server_name(sel)
        if actual and actual != placeholder:
            overrides[placeholder] = actual
    return overrides
```

### 2. `env/content.py` — применение подстановки

В `deploy_content(config, *, update)` после копирования дерева, рендера агентов и
записи `settings.json` — один проход по развёрнутому `project/.claude`, только при
`update is False` и непустой карте:

```python
def _apply_mcp_names(claude_dir, overrides) -> None:
    for path in sorted(claude_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            path.write_text(new, encoding="utf-8")
```

Вызов в конце `deploy_content`:

```python
if not update:
    overrides = mcp_name_overrides(config.mcp)
    if overrides:
        _apply_mcp_names(claude, overrides)
```

`.mcp.json` (корень проекта) не трогаем — он уже генерируется с актуальными именами.

### Почему замена подстрокой безопасна

Проверка показала: все вхождения `bsl_ls` / `1c_platform` / `1c_naparnic` /
`code_index` в `template/` — это именно имена MCP (в `mcp__X__…`, `mcp__X`,
`` `X` `` или прозе «MCP X»). Пересечений с другими идентификаторами нет
(`bsl_sql`, `ask_1c_ai`, `check_1c_code`, `search_terms` и т.п. не содержат этих
строк). Поэтому `str.replace(placeholder, actual)` корректно правит и токены
разрешений `mcp__bsl_ls__check`, и прозу.

## Краевые случаи

- **MCP без `standard_key` / неизвестный вид** (`custom`): `sel.id` не является
  ключом вида → `get_type` бросает `KeyError` → пропуск. Сервер просто попадает в
  `.mcp.json`, шаблон его не упоминает.
- **Имя оставлено по умолчанию:** `actual == placeholder` → пары нет → no-op.
- **Два выбранных MCP одного вида:** в карту попадает последний (словарь). Редкий
  случай; плейсхолдер один, так что это допустимо.
- **Обновление окружения (`update=True`):** подстановка не выполняется.

## Тестирование

Юнит (`tests/env/test_mcp_catalog.py` или рядом):

- `mcp_name_overrides`: выбор `bsl-ls` с `connection_json`, где ключ `bsl_checker`
  → `{"bsl_ls": "bsl_checker"}`;
- имя по умолчанию (`bsl_ls`) → пустая карта;
- неизвестный вид / без `standard_key` → пропуск;
- без `connection` → актуальное имя берётся из `sel.id`.

Интеграция (`tests/env/` для `deploy_content`):

- конфиг с `bsl-ls`, переименованным в `bsl_checker`, и **без** `code-index`:
  после `deploy_content(update=False)` во всех файлах `.claude`
  (агенты, `settings.json`, `skills/mcp-usage/SKILL.md`,
  `rules/verify-with-syntax-checker.md`, `hooks/bsl_nudge.py`) встречается
  `bsl_checker` и не встречается `bsl_ls`; `code_index` остаётся нетронутым;
- `deploy_content(update=True)` с той же картой → подстановки нет.

## Вне области

- Обратная замена при обновлении окружения.
- Изменение конвенции имён (дефис/подчёркивание) — оставляем подчёркивания.
- Подстановка в файлах вне `.claude`.
