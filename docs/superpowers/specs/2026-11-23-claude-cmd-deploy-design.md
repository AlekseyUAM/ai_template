# AGENTMON_CLAUDE_CMD: обёртки запуска, инструкция и настройки Strata

Дата: 2026-11-23
Статус: утверждён. `--claude-cmd` остаётся переопределением с приоритетом
над `AGENTMON_CLAUDE_CMD` из `test.env`.

## Зачем

`benchmark/setup_benchmark.py` пересоздаёт проект целиком, поэтому обёртки
`claude-*.bat`, положенные в корень проекта, теряются при каждом setup
(факт: `claude-strata.bat` в `D:\projects\test` уже пропал). Нужны скрипты
вне проекта — в `PATH` (`%USERPROFILE%\.local\bin`), — единая инструкция
«какую обёртку куда положить и что записать в `AGENTMON_CLAUDE_CMD`»,
и автоматическая настройка локальной LLM через Strata.

## Цели

1. `deploy/claude/` — единственный источник обёрток `claude-ds` и
   `claude-local` (`.bat` + `.sh`) и инструкция `deploy/claude/README.md`.
2. `benchmark/claude-local.*.example` удаляются, `benchmark/README.md`
   ссылается на `deploy/claude/`.
3. `AGENTMON_CLAUDE_CMD` в `benchmark/example.test.env` — обязательный для
   `run_benchmark.py` и `stage_run.py`; отсутствие → понятная ошибка.
   `--claude-cmd` остаётся переопределением.
4. `BENCH_STRATA_SETTINGS=1` в `test.env` → `setup_benchmark.py` сам получает
   env-блок у `strata connect claude-code --show-key` и пишет
   `<проект>/.claude/settings.local.json`.
5. Bench-раннер запускает `.bat`/`.cmd` по короткому имени — резолв через
   `shutil.which` с учётом `PATHEXT` (сейчас `Popen(["claude-ds", ...])` на
   Windows падает с `WinError 2`).
6. Ссылка на инструкцию из корневого `README.md`.

## Не цели

- Не менять поведение самого AgentMon при запуске агента и не ослаблять
  `registry._validate_claude_cmd` (команда проекта через API по-прежнему
  только `claude*`).
- Не автоматизировать установку скриптов в `PATH` — инструкция и скрипты,
  установка копированием.
- Не добавлять Linux-специфичные менеджеры пакетов.

## Принятые решения (обсуждены с пользователем)

| Вопрос | Решение |
|--------|---------|
| Источник настроек Strata | `strata connect claude-code --show-key`, парсинг JSON-блока |
| Семантика `AGENTMON_CLAUDE_CMD` в test.env | дефолт bench-раннеров; нет значения → ошибка |
| Судьба benchmark-примеров обёрток | перенести в `deploy/claude/`, примеры удалить |
| Запуск `.bat` по короткому имени | починить резолв в `claude_proc` |

## Дизайн

### `deploy/claude/`

| Файл | Назначение |
|------|------------|
| `claude-ds.bat` / `claude-ds.sh` | DeepSeek: ключ из `DEEPSEEK_API_KEY` или `~/.config/deepseek/key`, `ANTHROPIC_*` на `api.deepseek.com/anthropic`, запуск `claude --dangerously-skip-permissions "$@"`. |
| `claude-local.bat` / `claude-local.sh` | Локальная LLM: сбрасывает унаследованные `ANTHROPIC_*`, ставит `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`, запускает `claude`. **Без `cd "%~dp0"`**: настройки берутся из `.claude/settings.local.json` проекта текущего каталога (раннеры передают `cwd=проект`). |
| `README.md` | Куда копировать (`%USERPROFILE%\.local\bin` / `~/.local/bin`, PATH), как получить ключ DeepSeek, как настроить локальную LLM (Strata / вручную), что писать в `AGENTMON_CLAUDE_CMD` для AgentMon (`.ai1c.env`) и для bench (`test.env`), как проверить. |

Обёртки не содержат секретов (ключ читается из файла/env), поэтому коммитятся.

### `benchmark/example.test.env`

```ini
# ─── Агент ───────────────────────────────────────────────────────────────────
# Команда запуска агента для run_benchmark.py/stage_run.py (обязательна).
# --claude-cmd на командной строке переопределяет. Варианты:
#   claude-ds, claude-local, claude --dangerously-skip-permissions
# Для запуска через AgentMon Web UI задайте то же значение в .ai1c.env.
AGENTMON_CLAUDE_CMD=claude-ds

# ─── Локальная LLM (Strata) ──────────────────────────────────────────────────
# 1 — setup_benchmark.py возьмёт настройки у `strata connect claude-code`
# и запишет <проект>/.claude/settings.local.json. 0/не задано — не трогать.
BENCH_STRATA_SETTINGS=0
# Путь к CLI Strata, если её нет в PATH (см. deploy/claude/README.md).
#STRATA_CMD=C:\Users\user\AppData\Local\Strata\terminal\current\bin\strata.cmd
```

`AGENTMON_CLAUDE_CMD`, `BENCH_STRATA_SETTINGS`, `STRATA_CMD` добавляются в
`OPTIONAL_KEYS` (`bench_setup.py`), чтобы setup не предупреждал о неизвестных
ключах. Обязательность `AGENTMON_CLAUDE_CMD` проверяют раннеры, не setup.

### Разбор команд и `.bat` (`benchmark/`)

Новый модуль-хелпер в `benchmark/claude_proc.py`:

- `split_command(cmd) -> list[str]` — `shlex.split` с `posix=False` на Windows
  (backslash-пути), снятие внешних кавычек;
- `resolve_command(cmd) -> list[str]` — резолв `argv[0]` через
  `Path`/`shutil.which` (учитывает `PATHEXT`: `.exe/.bat/.cmd`), остальные
  аргументы сохраняются; не найден → `FileNotFoundError`.

`run_claude_process` строит `argv = resolve_command(cmd) + ["-p", ...]`.
`ensure_claude_cmd` (`bench_run.py`) вызывает `resolve_command` и превращает
`FileNotFoundError` в `BenchError` (сообщение и поведение для e2e-теста
«команда агента» сохраняются).

`bench_run.build_options` и `stage_run.main`:

- `--claude-cmd` (default теперь `None`) → если задан, используется он;
- иначе `AGENTMON_CLAUDE_CMD` из `test.env` (`read_env_file`);
- иначе `BenchError` с путём к файлу и подсказкой про `--claude-cmd`.

### Настройки Strata (`bench_setup.py`)

- `parse_strata_env(output) -> dict[str, str]` — первый JSON-объект через
  `json.JSONDecoder().raw_decode`; обязательны непустые `env`,
  `env.ANTHROPIC_BASE_URL`, `env.ANTHROPIC_MODEL`, `env.ANTHROPIC_AUTH_TOKEN`;
  иначе `SetupError`.
- `fetch_strata_env(strata_cmd, *, run=subprocess.run, timeout=60)` —
  `resolve_command(strata_cmd) + ["connect", "claude-code", "--show-key"]`,
  UTF-8 с `errors="replace"`; ненулевой код/таймаут → `SetupError` без вывода
  токена.
- `build_strata_settings(env) -> dict` — `env` из strata + недостающие
  benchmark-ключи: `PYTHONUTF8`, `PYTHONIOENCODING`, `MAX_MCP_OUTPUT_TOKENS=8000`,
  `BASH_MAX_OUTPUT_LENGTH=12000`, `CLAUDE_CODE_TOTAL_TOKENS_REMINDER=off`;
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW = int(context * 0.95)`, если strata дала
  `CLAUDE_CODE_MAX_CONTEXT_TOKENS`; верхнеуровневые `permissions.deny`
  (как в `template/.claude/settings.local.json.example`) и
  `claudeMdExcludes`; `modelOverrides {"claude-sonnet-4-6": ANTHROPIC_MODEL}`.
- `write_strata_settings(project_dir, settings)` → `.claude/settings.local.json`
  (UTF-8, `indent=2`), лог без токена: модель, контекст, путь.

Интеграция:

- `BenchConfig` получает `strata_settings: bool` и `strata_cmd: str`;
  `BENCH_STRATA_SETTINGS` принимает `0/1` (иначе `SetupError`).
- `setup_benchmark.main` при включённом флаге вызывает `fetch_strata_env`
  **до** `run_setup_with_lock_retry` (сбой не уничтожает существующий проект)
  и передаёт `strata_env` в `run_setup`.
- `run_setup` после шага «окружение проекта» пишет настройки, если передан
  `strata_env`; без него и с флагом — получает сам (совместимость с тестами).
- `.claude/settings.local.json` в шаблоне в `.gitignore`, `deploy_content`
  его не создаёт — файл setup'а не затирается.

### Документация

- `README.md`: в строке таблицы `AGENTMON_CLAUDE_CMD` — ссылка на
  `deploy/claude/README.md`; абзац после таблицы с одной фразой о выборе
  обёртки.
- `benchmark/README.md`: прогон по умолчанию — команда из `test.env`;
  миграционная заметка «добавьте `AGENTMON_CLAUDE_CMD`»; раздел поэтапного
  прогона ссылается на `deploy/claude/`; в «Настройках из Strata» —
  автоматический режим `BENCH_STRATA_SETTINGS=1`.

## Тесты

- `app/tests/env/test_bench_setup.py`: `load_config` принимает новые ключи без
  предупреждения; `BENCH_STRATA_SETTINGS=1` парсится; мусорное значение →
  `SetupError`; `parse_strata_env` на реальном выводе CLI (фикстура) и на
  битом выводе; `build_strata_settings` (merge, auto-compact, modelOverrides);
  `write_strata_settings` пишет файл; `run_setup` с `strata_env` пишет
  настройки (инъекция).
- `benchmark/tests/test_bench_run.py`: `build_options` берёт команду из
  test.env; флаг приоритетнее; без значения → `BenchError`;
  `split_command`/`resolve_command` (короткое имя через `shutil.which`,
  многословная команда, абсолютный `.bat`).
- `benchmark/tests/test_setup_benchmark.py`: `fetch_strata_env` не логирует
  токен, ошибки CLI → `SetupError` (если не покрыто в app-тестах).
- Прогон: `pytest app/tests/env/test_bench_setup.py benchmark/tests -q`.

## Совместимость

- Старый `benchmark/test.env` без `AGENTMON_CLAUDE_CMD` → раннеры падают с
  понятным сообщением; README содержит миграционную заметку.
- `benchmark/claude-local.*.example` удаляются; все ссылки обновляются.
- Полный путь к `.bat` в `--claude-cmd`/`AGENTMON_CLAUDE_CMD` продолжает
  работать; короткое имя теперь тоже.

## Мои решения (не обсуждались, можно оспорить)

- Обёртки `claude-ds.*` и `claude-local.*` делаю для Windows и POSIX.
- Обязательность `AGENTMON_CLAUDE_CMD` — только в раннерах; setup терпит
  отсутствие (он не запускает агента).
- `--claude-cmd` остаётся переопределением и имеет приоритет над test.env.
- `CLAUDE_CODE_AUTO_COMPACT_WINDOW` вывожу как 95 % контекста.
- Дополнительные env-ключи (UTF-8, лимиты MCP/вывода) добавляются, только
  если strata их не задала.
