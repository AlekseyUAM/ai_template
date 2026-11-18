# MCP 1c_naparnic в benchmark-окружении

Дата: 2026-11-18
Статус: согласовано с пользователем (дизайн)

## Цель

Подключать общий MCP-сервер 1С:Напарник (`1c_naparnic`) к проекту,
подготовленному `benchmark/setup_benchmark.py`, по адресу из
`benchmark/test.env` — по аналогии с опциональным `1c-md`. Навык
`mcp-usage` должен направлять агента в `ask_1c_ai` при ошибках компиляции и
сигнатур, но только когда сервер реально подключён — через условный блок
`<!-- @if 1c_naparnic -->`, как `<!-- @if 1c-md -->`.

## Не входит в Scope

- Запуск/сборка контейнера 1С:Напарника: сервер общий и уже работает,
  setup только прописывает адрес в `.mcp.json`.
- Хранение токена Напарника в `test.env`: токен настроен на стороне сервера.
- Изменения `query-analyze`, `query-review`, `task-orchestration`: `ask_1c_ai`
  рекомендуется только в `mcp-usage`.
- Изменение реального `benchmark/test.env` (он в `.gitignore` и содержит
  секреты) — пользователь добавляет ключ сам, если нужно.

## Контракт test.env

Новый необязательный ключ — полный URL streamable-HTTP MCP:

```dotenv
# URL общего MCP 1С:Напарник; если не задан — сервер не подключается.
# Токен Напарника настроен на стороне сервера, в test.env его нет.
#MCP_1C_NAPARNIC_URL=http://localhost:8003/mcp
```

- Ключ входит в `OPTIONAL_KEYS`; пустое значение = сервер не подключён.
- Валидация такая же, как у `MCP_1C_MD_URL`: схема `http(s)://`, корректный
  `host:port`; иначе `SetupError`.
- `BenchConfig.one_c_naparnic_url: str | None`.

## Изменения

### `benchmark/example.test.env`

Закомментированный пример в разделе «Опционально» (см. выше).

### `app/src/agentmon/env/bench_setup.py`

- `OPTIONAL_KEYS` += `MCP_1C_NAPARNIC_URL`; ключ в цикле проверки URL.
- `BenchConfig.one_c_naparnic_url`.
- `build_mcp_plans`: при заданном URL — план **после 1c-md, перед code_index**:
  - `standard_key="1c-naparnic"` (совпадает с ключом вида в `mcp_types`);
  - `mcp_name="1c_naparnic"`;
  - `kind="docker"` (вид карточки; контейнер не запускается);
  - `connection_json=_connection_http("1c_naparnic", url)`;
  - `purpose` — «Объяснение логики кода, любые вопросы по
    информационно-технологическому сопровождению 1С»;
  - `url`/`port` заполнены из `_url_host_port`.
- `preflight` получает параметр `http_ok=default_http_ok`; при заданном URL
  проверяет HTTP-доступность (любой HTTP-ответ, включая 401/4xx, означает, что
  сервис слушает). Ошибка:
  `MCP_1C_NAPARNIC_URL: сервер недоступен по адресу <url>`.
- `run_setup` передаёт `http_ok` в оба вызова `preflight` (включая ветку
  `recreate`).

### `benchmark/setup_benchmark.py`

В итоговой сводке — строка `1c_naparnic: <url>` при заданном ключе (рядом с
`1c-md`).

### `app/src/agentmon/env/content.py`

- Декларативная карта условий:

  ```python
  _CONDITION_MCP_IDS = {
      "1c-md": ("1c-md", "1c-md-queries"),
      "1c_naparnic": ("1c-naparnic",),
  }
  ```

- `conditional_flags(mcp) -> dict[str, bool]` — по включённым `McpSelection`
  (флаг учитывает `enabled`; выключенный сервер блок не включает).
- `_render_conditional_blocks(text, conditions, *, filename="")` принимает
  mapping; неизвестное условие — `ValueError` (маркеры не должны попадать в
  развёрнутый проект).
- `_render_template_texts(..., conditions, py_cmd)`.
- `deploy_content`: флаги считаются один раз; `has_1c_md` =
  `conditions["1c-md"]` — подстановка `{{MCP_1C_MD_TOOLS}}` не меняется.
- Порядок прежний: рендер условий **до** подстановки имён MCP, поэтому
  переименование сервера не ломает маркер `@if 1c_naparnic`.

### `template/.claude/skills/mcp-usage/SKILL.md`

Внутри `<!-- @if 1c_naparnic -->`:

- строка таблицы: «Ошибка компиляции BSL или непонятная сигнатура метода →
  `1c_naparnic` → `ask_1c_ai`»;
- золотое правило: при **любой** ошибке компиляции/сигнатуры — сразу
  `ask_1c_ai`, параллельно с `bsl_ls check` и `1c_platform`, не угадывать по
  памяти;
- точное имя инструментов: `mcp__1c_naparnic__*` — подчёркивание, не дефис;
- секция о сервере: инструменты `ask_1c_ai` и `explain_1c_syntax`; запросы и
  фрагменты кода уходят во внешний сервис 1С — не отправлять секреты; ошибка
  авторизации означает неверный/просроченный токен на сервере; `check_1c_code`
  не используется, для проверки кода — `bsl_ls`;
- рецепт «ошибка компиляции/сигнатуры».

Агенты уже содержат `mcp__1c_naparnic__*` в allow-list — не меняются.

## Поток данных

`test.env` → `load_config` (`BenchConfig.one_c_naparnic_url`) → `build_mcp_plans`
(план `1c-naparnic`) → `resolve_mcp_cards` / `build_env_config` →
`.mcp.json` и карточка проекта в AgentMon. Параллельно `deploy_content` по
списку MCP проекта рендерит `@if 1c_naparnic` в `mcp-usage`.

## Обработка ошибок

- URL без `http(s)://` или с некорректным портом → `SetupError` на разборе
  конфига, до создания каталога.
- Сервер недоступен → `SetupError` в preflight, до создания каталога и записей
  БД (fail fast; в режиме `recreate` старый проект не удаляется).
- Сервер не задан → блок в навыке вырезан, `1c_naparnic` отсутствует в
  `.mcp.json`; benchmark работает как раньше.

## Тестирование

`app/tests/env/test_bench_setup.py`:

- парсинг ключа; `None` по умолчанию; отказ URL без схемы;
- `build_mcp_plans` с naparnic: порядок, `mcp_name`, connection, url/port;
- `build_env_config` / `build_mcp_json` содержат `1c_naparnic`;
- preflight: недоступный URL → `SetupError`, доступный → проходит; без ключа HTTP
  не вызывается.

`app/tests/env/test_content_conditions.py`:

- прямые вызовы `_render_conditional_blocks` переводятся на mapping;
- deploy с `sel("1c-naparnic")` → в `mcp-usage` есть `ask_1c_ai`, нет
  `<!-- @if … -->`;
- без naparnic и при `enabled=False` → `ask_1c_ai` нет;
- переименованный сервер (`"my_ai"`) подставляется в `mcp__my_ai__…`;
- маркеры не утекают в развёрнутый проект ни при включённом, ни при выключенном
  сервере.
