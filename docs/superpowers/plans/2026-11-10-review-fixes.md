# План исправлений по код-ревью AgentMon (2026-11-10)

**Цель:** устранить 15 главных и ~12 дополнительных дефектов, найденных при глубоком ревью first-party кода, не меняя модель данных без миграции и не ломая существующие тесты.

**Архитектурные решения (согласованы):**
- SSH/Docker: удалённый detached-раннер. Monitor запускает `ssh`/`docker exec` локально, log/exit-файлы и PID живут на мониторе, JSONL читается бэкендом через `SessionFiles`.
- Доступ: fail-fast при не-loopback bind без `AGENTMON_TOKEN`; проверка `Authorization: Bearer`/`X-Agentmon-Token`, `Host` и `Origin`; UI получает токен из URL и хранит локально.
- Issues: локальный план + задачи (этот файл).
- Объём: все находки, включая дополнительные.

**Порядок:** каждый этап завершается зелёными тестами `cd app && python -m pytest`. Коммиты не делаем без отдельной просьбы.

---

## Phase 0. Гигиена репозитория

### Task 0.1. `.1c-devbase.json` в .gitignore
**Files:** `template/.gitignore`, `app/src/agentmon/env/devbase.py`, `app/tests/env/test_devbase_gitignore.py` (новый)
- [x] Добавить `.1c-devbase.json` в `template/.gitignore`.
- [x] `git_init_project()` при наличии `.gitignore` дописывает отсутствующие строки `.1c-devbase.json`, `.venv`, `.agentmon`, `logs/`, `*.log` (идемпотентно).
- [x] Тест: после `deploy_content`/`git_init_project` файл `.1c-devbase.json` игнорируется (`git check-ignore`), а существующие строки не дублируются.

## Phase 1. Доступ и секреты

### Task 1.1. Токен, Host/Origin, fail-fast
**Files:** `app/src/agentmon/config.py`, `app/src/agentmon/__main__.py`, `app/src/agentmon/api.py`, `app/web/header.js`, `app/web/start.js`, `app/tests/test_auth.py` (новый)
- [x] `AGENTMON_TOKEN`, `AGENTMON_ALLOWED_HOSTS` в config; `is_loopback(host)`.
- [x] При старте: `HOST` не loopback и нет токена → `SystemExit` с понятным сообщением.
- [x] Middleware: проверяет `Host` (loopback + allowed hosts), `Origin` (если есть — должен совпадать с Host), токен для `/api/*` и `/ws/*` (`Authorization: Bearer`, `X-Agentmon-Token` или `?token=`).
- [x] Статика и страницы доступны без токена только для loopback; при внешнем bind — токен обязателен на всех путях, кроме `/static` и `/`.
- [x] `header.js`: перехват `?token=`, localStorage, глобальная обёртка `fetch` с заголовком; `start.js` добавляет токен к WebSocket URL.

### Task 1.2. Валидация `claude_cmd`
**Files:** `app/src/agentmon/registry.py`, `app/tests/test_registry.py`
- [x] `claude_cmd` после `shlex.split` должен начинаться с `claude`/`claude.exe` или абсолютного пути к существующему файлу; запрещены `sh`, `bash`, `cmd`, `powershell`, `python -c`, пустые команды.
- [x] Тесты: разрешённые команды, отказ на `sh -c id`, отказ на несуществующий абсолютный путь.

### Task 1.3. Пароль 1С не попадает в git
**Files:** `app/src/agentmon/env/devbase.py`, `app/tests/env/test_devbase.py`
- [x] `write_devbase` пишет пароль в `.1c-devbase.json` (нужен 1c-batch), но `git_init_project` гарантирует ignore; добавить тест, что `git add .` его не берёт.
- [x] Маскировать пароль в логах/ошибках провижининга (если встречается в `ProgressEvent.detail`).

## Phase 2. Удалённый detached-раннер

### Task 2.1. Планировщик запуска по бэкенду
**Files:** `app/src/agentmon/monitor.py`, `app/src/agentmon/runner_detached.py`, `app/src/agentmon/backends/docker.py`, `app/src/agentmon/backends/ssh.py`, `app/tests/test_monitor_remote.py` (новый)
- [x] `runner_detached.launch(..., cwd)` для remote получает `ssh -tt -p ... user@host 'cd <path> && exec <cmd...>'` или `docker [-H ...] exec -t -w <workdir> <container> <cmd...>`; `cwd` — локальный временный каталог.
- [x] `Monitor._run_paths`: для `local` — `<project>/.agentmon/runs`, для `ssh/docker` — `config.RUNS_DIR` (по умолчанию рядом с БД).
- [x] `Monitor.start` выбирает команду по `project.backend`; `monitor._cmd_for` остаётся для local.
- [x] `Monitor.stop` для remote убивает локальный PID (ssh с `-tt` шлёт SIGHUP; docker exec с `-t` — тоже).
- [x] Тесты: ssh-команда содержит `ssh -tt`, удалённый `cd`, экранирование пути; docker-команда содержит `exec -t -w`; log/exit-пути локальные.

### Task 2.2. PID reuse
**Files:** `app/src/agentmon/runner_detached.py`, `app/src/agentmon/store/schema.py`, `app/src/agentmon/store/runs.py`, `app/tests/test_runner_detached.py`
- [x] Хранить `pid_start` (поле 22 `/proc/<pid>/stat`) при launch; `is_running(pid, pid_start)` сверяет; `terminate` не убивает при несовпадении.
- [x] Миграция `runs.pid_start DOUBLE PRECISION` (`_ensure_columns`), NULL для старых строк — считать «неизвестно» и не убивать по группе, если процесс не наш.
- [x] Тест: подменить start-time → is_running False, terminate no-op.

### Task 2.3. run_wrapper без exec
**Files:** `app/src/agentmon/run_wrapper.py`, `app/tests/test_run_wrapper.py`
- [x] POSIX: `os.execv(sys.executable, [sys.executable, "-m", "agentmon.run_wrapper", ...])`? Нет — wrapper должен заменить себя целевой командой: `os.execvp(cmd[0], cmd)` после записи exit-кода не получится; писать exit-код должно само приложение. Вместо exec: запускать дочерний процесс, но `prctl(PR_SET_PDEATHSIG, SIGTERM)` на Linux, чтобы гибель wrapper убивала claude; на остальных — текущее поведение + предупреждение.
- [x] Тест: Linux-only, wrapper получает SIGKILL → дочерний процесс завершается (PDEATHSIG).

## Phase 3. Оркестрация и task.json

### Task 3.1. Стек: защита от бесконечных перезапусков
**Files:** `app/src/agentmon/env/stack_dispatcher.py`, `app/tests/env/test_stack_dispatcher.py`
- [x] Хранить `_last_progress[task_id] = (stages_json)`, `_no_progress[task_id]`.
- [x] Если после exit 0 `stages_json` не изменился — инкремент; после 2 подряд — `failed` с логом, без нового запуска. Если изменился — сброс.
- [x] При исключении `monitor.start` — счётчик `_start_failures`, после 3 подряд `failed`.
- [x] Тесты: два пустых прогона → failed; прогресс сбрасывает счётчик; три ошибки старта → failed.

### Task 3.2. SSE-откат при обрыве
**Files:** `app/src/agentmon/env/project_api.py`, `app/tests/env/test_project_stream.py`
- [x] Обернуть тело генератора в `try/except BaseException/finally`; откат при `failed`, `GeneratorExit`, `asyncio.CancelledError`; флаг `rolled_back` от повторного удаления.
- [x] То же для `update-env/stream`.
- [x] Тест: `gen.close()` после первого yield → проект удалён из БД и registry.

### Task 3.3. Контракт task.json
**Files:** `app/src/agentmon/env/task_schema.py`, `app/src/agentmon/env/task_sync.py`, `app/tests/env/test_task_schema.py`
- [x] Добавить `gate: bool = False`, `approved: bool = False` в `Stage`; `from_dict` игнорирует неизвестные поля; `to_dict` сохраняет `status` верхнего уровня.
- [x] `sync_task_from_file` whitelisted статусы (`planned/running/awaiting_user/done/failed`), неизвестные не пишет.
- [x] Тест: v2 task.json c gate/approved читается и пересохраняется без потерь.

### Task 3.4. Атомарная запись task.json
**Files:** `template/.claude/tools/task_status.py`, `app/src/agentmon/env/task_sync.py`, `app/tests/env/test_task_json_atomic.py`
- [x] Общий паттерн: temp-файл в том же каталоге + `os.replace`; межпроцессный lock-файл `task.json.lock` с retry 5×50 мс.
- [x] `task_status.py`: `_atomic_write_json`; `write_stage_approval` использует тот же паттерн.
- [x] Тест: два параллельных writer'а не теряют `approved` и не оставляют битый JSON.

### Task 3.5. Гейты и awaiting_user в task_status
**Files:** `template/.claude/tools/task_status.py`, `app/tests/test_task_status_cli.py`
- [x] `_gate_block`: блокирует только если гейтированный этап `done` и не approved, и целевой этап идёт после него.
- [x] `_overall_status` добавляет `awaiting_user` по тем же правилам, что `task_model.overall_status`.
- [x] Тесты: pending-гейт не блокирует; done+!approved блокирует следующий; overall → awaiting_user.

### Task 3.6. run-tests.py: коды возврата
**Files:** `template/.claude/tools/run-tests.py`, `app/tests/test_run_tests_cli.py`
- [x] Маппинг: rc 0 → ok; rc 1/2 от check-modules, но с сообщением о запуске/лицензии/платформе → `RC_ENV_ERROR` (3), не `RC_COMPILE_ERROR`; только явные маркеры компиляции (regex) → 2.
- [x] Тест: поддельный `run_batch` с rc=1 и stderr «license» → 3; rc=1 с «Syntax error» → 2.

### Task 3.7. Хуки: не блокировать промпт
**Files:** `template/.claude/hooks/route_to_orchestrator.py`, `template/.claude/hooks/bsl_nudge.py`, `app/tests/test_hooks.py`
- [x] `main()` в `try/except BaseException`: любое исключение → `exit 0`, диагностика в stderr.
- [x] `_paths()` проверяет `isinstance(value, str)`.
- [x] Тесты: prompt=123 → exit 0; кривой tool_input → exit 0.

### Task 3.8. update-env: бэкапы и MCP-имена
**Files:** `app/src/agentmon/env/content.py`, `app/src/agentmon/backends/local.py`, `app/src/agentmon/backends/ssh.py`, `app/src/agentmon/backends/docker.py`, `app/tests/env/test_content.py`
- [x] `put_tree(..., backup=True)` при update: для каждого существующего файла с отличием писать `<file>.bak` перед заменой.
- [x] `mcp_subs = mcp_name_overrides(config.mcp)` и при update (не сбрасывать в `{}`).
- [x] Тест: правка `.claude/skills/x/SKILL.md` → после update-env есть `.bak`, имя MCP переподставлено.

## Phase 4. Telegram

### Task 4.1. Bot API ok=false и маскировка токена
**Files:** `app/src/agentmon/telegram/client.py`, `app/tests/telegram/test_client.py`
- [x] `_call`: HTTP 200 + `ok:false` → `TelegramError` с `error_code`/`description`, без токена в тексте.
- [x] Обернуть `raise_for_status` в `except HTTPStatusError` → `TelegramError` с маской `bot<TOKEN>` → `bot***`.
- [x] Тесты: 403 ok=false → ошибка без токена; 500 → ошибка без токена.

### Task 4.2. Нотификатор: без дублей
**Files:** `app/src/agentmon/telegram/notifier.py`, `app/tests/telegram/test_notifier.py`
- [x] `_sent_parts[(scope, ref_id, status)]` — сколько частей уже отправлено; сдвигать после каждой успешной; сбрасывать при смене статуса.
- [x] Тест: падение на 2-й части → повтор шлёт только 2-ю и последующие.

### Task 4.3. Pending-замечание: команды и TTL
**Files:** `app/src/agentmon/telegram/handlers.py`, `app/tests/telegram/test_handlers.py`
- [x] Хранить `(task_id, stage, ts)`; TTL 10 минут; сообщение, начинающееся с `/`, сбрасывает pending и обрабатывается как команда; callback тоже сбрасывает.
- [x] Ошибки `approve` (HTTP 4xx/5xx) сообщать пользователю, не глотать.
- [x] Тесты: `/tasks` после «Замечание» не пишет feedback; approve 500 → сообщение об ошибке.

## Phase 5. Bootstrap и PostgreSQL

### Task 5.1. merge `.ai1c.env`
**Files:** `bootstrap.py`, `app/tests/test_bootstrap_env.py`
- [x] `write_env` читает существующий файл, обновляет только `AGENTMON_DSN/AGENTMON_DB/AI1C_PG_MODE`, сохраняет остальные строки и комментарии.
- [x] Тест: токен и `AGENTMON_CLAUDE_CMD` выживают повторный bootstrap.

### Task 5.2. PG: checksum, кэш по платформе, порт, фолбэк
**Files:** `pg_portable.py`, `bootstrap.py`, `run.py`, `app/tests/test_pg_portable.py`
- [x] Кэш: `.ai1c/pg/<version>/<system>-<arch>`; старый путь игнорируется.
- [x] Проверка архива: `AI1C_PG_SHA256`; если задан — сверить; если нет — скачать `<url>.sha256` и сверить, при недоступности — warning.
- [x] Порт: `free_port()` при старте проверяет занятость; при занятости сохраняет новый и обновляет `.ai1c.env`; `run.py` перед стартом сверяет `ai1c.port` с DSN.
- [x] Docker health timeout → SQLite DSN + предупреждение (фолбэк), `compose up` при ошибке → SQLite.
- [x] README: «PostgreSQL в Docker» → «портативная PG (host) или Docker (AI1C_PG_MODE=docker)».
- [x] Тесты на merge/write и выбор DSN с моками.

## Phase 6. Бэкенды и прочее

### Task 6.1. SSH: host key и UTF-8
**Files:** `app/src/agentmon/backends/ssh.py`, `app/tests/test_backend_ssh.py`
- [x] `RejectPolicy` по умолчанию; `conn["strict_host_key"]=False` — AutoAddPolicy; `load_system_host_keys()`.
- [x] Инкрементальный декодер `codecs.getincrementaldecoder("utf-8")("replace")` на агента.
- [x] Тесты: неизвестный host key → SshUnavailable; разрезанный UTF-8 символ не даёт U+FFFD.

### Task 6.2. Docker: liveness и коды возврата
**Files:** `app/src/agentmon/backends/docker.py`, `app/tests/test_backend_docker.py`
- [x] `ensure()` при каждом вызове делает `docker inspect` (кэш 2 с); `exec_run` с rc!=0 → `mark_broken` + исключение для write/mkdir.
- [x] Тесты: контейнер остановлен после первого успеха → следующая запись бросает.

### Task 6.3. Dispatcher: задачи удалённых проектов
**Files:** `app/src/agentmon/dispatcher.py`, `app/src/agentmon/store/tasks.py`, `app/tests/test_dispatcher.py`
- [x] На тике: `queued/running` задачи с `project_id` не из registry → `failed` с причиной «проект удалён».
- [x] Счётчик ретраев сохранять в БД (`tasks.requeues INTEGER DEFAULT 0`), сбрасывать при успешном старте.
- [x] Тесты: удаление проекта → задача failed; рестарт монитора не сбрасывает счётчик.

### Task 6.4. nethasp.ini: каталог платформы
**Files:** `app/src/agentmon/env/nethasp.py`, `app/tests/env/test_nethasp.py`
- [x] Писать и в `<project>/conf/nethasp.ini`, и в `<home>/.1cv8/conf/nethasp.ini` на цели (provisioner).
- [x] Тест: оба пути создаются; содержимое одинаковое.

### Task 6.5. open-report: путь внутри проекта
**Files:** `app/src/agentmon/env/project_api.py`, `app/tests/env/test_project_api.py`
- [x] `resolve()` + `relative_to(project_tasks_dir)`; отказ 400 при выходе.
- [x] Тест: artifact `../../etc/passwd` → 400.

### Task 6.6. MCP: экранирование, порт, удаление item
**Files:** `app/src/agentmon/env/mcp_types.py`, `app/src/agentmon/env/mcp_docker.py`, `app/src/agentmon/env/stack_api.py`, тесты
- [x] JSON-подстановки через `json.dumps(value, ensure_ascii=False)[1:-1]`.
- [x] Порт: `int`, 1..65535, иначе 400.
- [x] `remove_item`: item должен принадлежать `stack_id`, иначе 404.
- [x] Тесты на каждую ветку.

### Task 6.7. bsl_check_server: лимиты
**Files:** `app/docker/mcp/bsl_check_server.py`, `app/tests/env/test_bsl_check_server.py`
- [x] Лимит `code` 5 МБ, `config` 1 МБ; `subprocess.run(..., timeout=300)`; отказ на имя `.bsl-language-server.json`.
- [x] Тесты: большой code → ошибка; таймаут → ошибка.

### Task 6.8. jsonl cursor: пересоздание файла
**Files:** `app/src/agentmon/jsonl_cursor.py`, `app/tests/test_jsonl_cursor.py`
- [x] Хранить `st_dev/st_ino` (POSIX) в ref; при смене inode сбрасывать offset/messages.
- [x] Тест: новый inode при том же mtime → чтение с нуля.

### Task 6.9. web: ошибки approve
**Files:** `app/web/tasks.js`
- [x] Проверять `r.ok`; показывать `detail`; не менять состояние при ошибке.

### Task 6.10. Документация и принятые риски
**Files:** `README.md`, `docs/running-web-ui.md`
- [x] Описать `AGENTMON_TOKEN`, `AGENTMON_ALLOWED_HOSTS`, fail-fast.
- [x] Исправить PG-режимы, SSH/Docker runner, `/P` как известное ограничение 1С.


---

## Дополнительно закрыто сверх первоначального списка

- `mcp_sources`: исходники MCP-серверов клонируются и переключаются на
  pinned-коммит (`repo_sha`), checkout failure удаляет каталог и не даёт собирать
  чужой HEAD.
- TOCTOU «каталог пуст»: повторная проверка в `install_environment` перед
  записью (для docker гейт пропускается — том пуст по построению).
- Docker compose up failure → SQLite-фолбэк (не только health-timeout).
- `web approve`: в текущем UI кнопки approve нет; ошибки одобрения из Telegram
  теперь сообщаются пользователю (см. Task 17).
