# План: MCP «Статический анализ BSL» — один инструмент `check`

## Проблема

Вид MCP «Статический анализ BSL» (кнопка «Развернуть в Docker локально») сейчас
поднимает **родной `mcp`-режим BSL LS**. У него нет инструмента для анализа
присланного текста: все инструменты (`analyze_file`, `document_symbols`, …)
работают только с файлами **внутри зарегистрированной и проиндексированной
workspace-папки**. Поэтому «прислал фрагмент кода → получил диагностику» не
работает (см. `tmp/out.txt`): агент не смог отдать текст модуля на проверку.

## Цель

Контейнер с BSL LS, в котором ровно **один** MCP-инструмент — `check`:

- на вход — текст кода BSL (+ опционально имя файла);
- на выход — список диагностик (ошибки/предупреждения) по настройкам проверок;
- полностью **stateless**, без доступа к кодовой базе и без индекса;
- настройки берутся из `.bsl-language-server.json` в корне проекта
  (пример — `~/projects/test_project1/.bsl-language-server.json`).

Bridge (`deps/mcp-bsl-lsp-bridge`) не используется (вывод из
`docs/MCP_BSL_INVESTIGATION.md`).

## Решение

Тонкая обёртка в контейнере: Python-сервер **FastMCP** (streamable-HTTP,
эндпоинт `/mcp`) с одним инструментом `check`, который гоняет BSL LS в режиме
**CLI `analyze`** с json-репортёром и парсит отчёт.

Поток `check(code, filename="Module.bsl")`:
1. временный каталог `src/`, записать `code` в `src/<filename>`;
2. `java -jar /opt/bsl-language-server.jar analyze --srcDir <src> --outputDir
   <out> --reporter json -c /config/.bsl-language-server.json`
   (`-c` подхватывает настройки; если конфиг не смонтирован — без `-c`);
3. прочитать `<out>/bsl-json.json`, достать `fileinfos[].diagnostics[]`;
4. вернуть `{ ok, count, diagnostics: [{line, column, endLine, endColumn,
   severity, code, source, message}] }` (строки/столбцы 1-based) + человекочитаемый текст;
5. подчистить временный каталог.

Формат отчёта `bsl-json.json` (из `reporters/JsonReporter` + `data/FileInfo`):
`{ date, fileinfos: [ { path, mdoRef, diagnostics: [lsp4j Diagnostic], metrics } ], sourceDir }`.
`severity` lsp4j может сериализоваться числом (1=Error,2=Warning,3=Information,4=Hint)
или именем — парсер обрабатывает оба.

### Конфиг `.bsl-language-server.json` — передаётся в вызове

Один общий контейнер bsl_ls обслуживает **все** проекты. Настройки проверок не
монтируются и не привязаны к карточке: вызывающий агент (Claude Code, работающий
в корне своего проекта) читает `.bsl-language-server.json` из корня проекта и
передаёт его содержимое **аргументом** `check(code, config=...)`. Сервер кладёт
этот текст в корень временной workspace-папки (рядом с кодом), и BSL LS
подхватывает его как per-workspace-настройки. Контейнеру не нужен ни доступ к ФС
проектов, ни монтирования, ни поле карточки — он полностью stateless.

Пример: проект `~/projects/test_project1` → агент шлёт содержимое
`~/projects/test_project1/.bsl-language-server.json`; проект
`test_project2` — своё. Один сервер, у каждого вызова свои настройки.

`config` необязателен: без него анализ идёт с дефолтными правилами BSL LS.

### Образ (очистка)

Dockerfile — **multi-stage**: сборочная стадия качает jar и ставит venv с `mcp`,
рантайм-стадия берёт только JRE + python3 + готовый venv + jar + сервер (без
`wget`/`ca-certificates`/`python3-venv`/apt-кэшей).

## Файлы

### Контейнер (контекст сборки `app/docker/mcp`)
- `app/docker/mcp/bsl-ls.Dockerfile` — переписать: JRE 21 + python3 + `mcp`
  (FastMCP) + exec-jar BSL LS; `COPY bsl_check_server.py`; `CMD python3
  bsl_check_server.py` (сервер слушает `0.0.0.0:${BSL_PORT}` на `/mcp`).
- `app/docker/mcp/bsl_check_server.py` — FastMCP-сервер, инструмент `check`;
  чистая функция `parse_report(report: dict, filename: str) -> list[dict]`
  (тестируется отдельно, без java/docker).

### Бэкенд-обвязка
- `app/src/agentmon/env/mcp_docker_recipes.py` — рецепт `bsl-ls`: флаг
  `config_mount=True`; в `launch_params` добавить параметр `config_path`,
  создать дефолтный конфиг при отсутствии, смонтировать ro в
  `/config/.bsl-language-server.json`, задать env `BSL_CONFIG`.
- `app/src/agentmon/env/mcp_api.py` — в `_resolve_docker` передавать
  `config_path = repo_root / ".bsl-language-server.json"` в `launch_params`.

### Тесты
- `app/tests/env/test_bsl_check_server.py` — `parse_report`: пусто, одна/несколько
  диагностик, severity числом и строкой, несколько fileinfos.
- `app/tests/env/test_mcp_docker_recipes.py` — обновить `test_bsl_ls_params_*`:
  монтирование конфига, создание дефолта, env `BSL_CONFIG`.
- `app/tests/env/test_mcp_api.py` — при необходимости: launch bsl-ls создаёт
  конфиг и прокидывает mount (с замоканным docker).

## Проверка (verification)
- `cd app && .venv/bin/python -m pytest -q` — зелёные, включая новые тесты.
- Сборка образа и запуск контейнера, реальный `check` с заведомо «грязным»
  кодом (длинная строка > 140) → в ответе диагностика `LineLength`.
- Коммит в `master` локально (Conventional Commits).

## Вне scope
Фронтенд (`mcp.js`, форма, кнопка «Развернуть в Docker локально») и вид MCP уже
готовы — не трогаем.
