# Нативный code-index вместо Docker

Дата: 2026-11-21

## Проблема

В Docker-развёртывании code-index на Windows индекс не обновляется
инкрементально: Linux-контейнер использует inotify, а изменения файлов на
Windows-хосте через bind mount событий не порождают. Индекс остаётся снимком
на момент старта контейнера. Текущий обход — перезапуск контейнера между
задачами benchmark (`bench_index.py`) — не нужен и удаляется.

Дополнительно в agentmon два вида code-index (Docker и локальный) и две
кнопки развёртывания. Нужен один нативный путь, поддерживающий несколько баз
в одном сервисе.

## Цели

1. Убрать Docker-развёртывание code-index из agentmon и benchmark.
2. Один нативный вид карточки code-index с кнопкой «Развернуть».
3. Один нативный сервис (`code_index_dir`) обслуживает несколько баз;
   добавление базы не затирает существующие `[[paths]]`, обращение — по
   alias (`project_name`, уже реализовано в code-index).
4. Benchmark поднимает нативный code-index сам: каталог из `.env`, процессы
   daemon/serve с PID-файлом, при перезапуске setup каталог и старый индекс
   очищаются.
5. Удалить обход `bench_index.py` и флаг `--no-index-refresh`.

## Принятые решения

- **Один вид карточки:** `code-index` становится нативным (`action="local"`),
  `code-index-local` остаётся скрытым legacy-видом для старых карточек.
  Docker-действие code-index убирается из UI и benchmark, Docker-рецепт и
  Docker-функции benchmark удаляются.
- **Идентичность сервиса:** абсолютный `code_index_dir`. В нём лежат
  `bsl-indexer`, `daemon.toml`, `service.json` (порт сервиса), логи.
  Несколько сервисов = несколько разных каталогов.
- **Мульти-база:** `daemon.toml` содержит несколько `[[paths]]`; добавление
  базы обновляет/добавляет ровно одну запись по alias и сохраняет остальные
  секции. После изменения — `daemon reload` и перезапуск `serve` (в режиме
  `--config` список alias'ов — снимок на старте).
- **Порт сервиса:** фиксируется в `service.json` при первом развёртывании.
  При добавлении базы используется порт сервиса; карточка обновляется под
  него, чтобы `.mcp.json` и агент не разошлись.
- **Autostart в agentmon:** постоянный, как у текущего локального вида;
  имена юнитов/задач — от хэша `code_index_dir`, а не от `mid`.
- **Benchmark:** собственные detached-процессы daemon/serve + PID-файл, без
  systemd/schtasks. При каждом setup старые PID гасятся, `CODE_INDEX_DIR` и
  `<проект>/src/cf/.code-index` удаляются, legacy Docker-контейнер
  `ai1c-mcp-code_index` удаляется best-effort. `CODE_INDEX_DIR` обязателен
  в `benchmark/test.env`.
- **Совместимость:** старые карточки `code-index-local` и docker-code-index
  открываются; при развёртывании docker-карточка переводится в `kind=local`.
  Правило alias не меняется: `alias = project_name`.

## Архитектура

```
app/src/agentmon/env/
  code_index_toml.py      # новый: merge [[paths]], ensure [mcp]/[[cache_targets]]
  code_index_local.py     # переработан: ensure service, service.json, multi-base
  code_index_bench.py     # новый: detached daemon/serve, PID, clean/stop/wait
  autostart.py            # + restart() и stop() для юнитов
  mcp_types.py            # один видимый code-index, скрытый legacy
  mcp_api.py              # deploy-local для code-index, порт сервиса, миграция
  bench_setup.py          # нативный запуск, CODE_INDEX_DIR, удаление Docker-кода
app/web/mcp.js            # одна кнопка «Развернуть», без Docker для code-index
benchmark/
  bench_index.py          # удалить
  tests/test_bench_index.py # удалить
  bench_run.py            # убрать index_refresh
  bench_metrics.py        # убрать строку индекса из дайджеста
template/.claude/skills/mcp-usage/SKILL.md # убрать «раннер обновляет индекс»
docs/mcp/code-index-*.md  # нативный вид, мульти-база, Docker — legacy
```

### `daemon.toml` (несколько баз)

```toml
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[cache_targets]]
url = "http://127.0.0.1:8005"

[mcp]
mass_mode_tools = ["get_object_structure"]

[[paths]]
path = "/project/a/src/cf"
alias = "project_a"
language = "bsl"

[[paths]]
path = "/project/b/src/cf"
alias = "project_b"
language = "bsl"
```

`code_index_toml.merge_path(text, alias, path)`:
- сохраняет преамбулу и все секции, кроме `[[paths]]`;
- заменяет блок с тем же `alias` (обновление базы) или добавляет новый;
- экранирует `\` и `"` в значениях;
- `ensure_sections(text, port)` добавляет `[mcp] mass_mode_tools` и
  `[[cache_targets]] url=http://127.0.0.1:<port>`, если их нет.

### `service.json`

```json
{"port": 8005, "version": 1}
```

Пишется атомарно. Читается API до развёртывания, чтобы взять порт сервиса.
При отсутствии (legacy) порт берётся из карточки и файл создаётся.

### `benchmark-pids.json` (только benchmark)

```json
{"daemon": 1234, "serve": 1235}
```

Пишется после запуска процессов. При cleanup PID читаются, процессы гасятся
(SIGTERM → SIGKILL на POSIX, `taskkill /PID /T /F` на Windows), затем
`CODE_INDEX_DIR` и `<catalog>/.code-index` удаляются.

## Потоки

### Agentmon: первое развёртывание

1. `_resolve_local` принимает `standard_key` из `{code-index, code-index-local}`,
   требует `catalog_dir`, `project_name`, `code_index_dir`; порт — из
   `service.json`, иначе из карточки; docker-карточка переводится в `kind=local`.
2. `code_index_local.deploy_local`:
   - скачивает бинарь, если его нет;
   - создаёт `daemon.toml` с одной базой и `service.json`;
   - ставит autostart daemon+serve (имена от хэша каталога) и запускает.
3. Карточка обновляется под фактический порт; `.mcp.json` при следующем
   обновлении окружения указывает на него.

### Agentmon: добавление базы

1. `service.json` уже есть → порт сервиса.
2. `merge_path` добавляет/обновляет `[[paths]]` по alias.
3. `bsl-indexer daemon reload` (best-effort; watcher демона тоже видит файл).
4. `autostart.restart` сервиса serve — новый alias становится виден.
5. Карточка обновляется под порт сервиса.

### Benchmark setup

1. `CODE_INDEX_DIR` обязателен; проверяется, что он вне каталога проекта.
2. `stop` старых PID; удаление `CODE_INDEX_DIR`; удаление
   `<проект>/src/cf/.code-index`; best-effort `docker rm -f ai1c-mcp-code_index`.
3. Скачивание бинаря, `daemon.toml` на одну базу, detached daemon и serve,
   PID-файл.
4. Ожидание: `daemon status --json` = ready + TCP-доступность порта serve.
5. Процессы живут между задачами; нативный watcher обновляет индекс.
6. При следующем setup шаги 1-4 повторяются; между задачами рестартов нет.

## Критерии приёмки

- В форме MCP нет Docker-вида code-index; у единственного code-index кнопка
  «Развернуть», без «Развернуть в Docker».
- Старая карточка code-index-local открывается и развертывается нативно;
  старая docker-карточка code-index показывает нативную кнопку и после
  развёртывания имеет `kind=local`.
- Два развёртывания с одним `code_index_dir` и разными alias дают
  `daemon.toml` с двумя `[[paths]]`; вторая база не затирает первую;
  `serve` перезапускается, `get_stats`/`repo` видят оба alias.
- Второе развёртывание использует порт из `service.json`; карточка обновлена.
- Benchmark setup с `CODE_INDEX_DIR`: старые процессы гасятся, каталог и
  старый `.code-index` очищаются, daemon/serve поднимаются, индекс ready.
- `bench_index.py`, `--no-index-refresh`, `index_refresh` в метриках/дайджесте
  и упоминания в `mcp-usage` удалены.
- Docker-рецепт code-index и Docker-функции benchmark удалены; Docker для
  остальных MCP не затронут.
- `pytest benchmark/tests -q` и `pytest app/tests/env -q` зелёные.
- Коммиты локально в `main`, push не выполняется.

## Тестирование

- `app/tests/env/test_code_index_toml.py` — merge/escape/sections.
- `app/tests/env/test_code_index_local.py` — первое развёртывание, вторая база,
  сохранение секций, service.json, порт, имена сервисов, reload/restart.
- `app/tests/env/test_autostart.py` — restart/stop на Linux/Windows/macOS.
- `app/tests/env/test_mcp_api.py` — deploy-local для code-index, legacy,
  порт сервиса, миграция `kind`.
- `app/tests/env/test_mcp_types.py` — один видимый вид, legacy скрыт.
- `app/tests/env/test_code_index_bench.py` — clean/start/stop/wait, PID,
  detached spawn, очистка каталогов, legacy container.
- `app/tests/env/test_bench_setup.py` — `CODE_INDEX_DIR`, нативный launch,
  откат, удаление Docker-тестов.
- `benchmark/tests` — удаление bench_index-тестов, отсутствие index_refresh.
- Полные suites.

## Вне области

- Upstream `PollWatcher`/`POST /reindex` в `deps/code-index-mcp`.
- Федеративный `serve.toml` вместо перезапуска serve.
- Docker-развёртывание code-index (удаляется); Docker остальных MCP остаётся.
- Ручное управление несколькими сервисами в UI сверх поля `code_index_dir`.
