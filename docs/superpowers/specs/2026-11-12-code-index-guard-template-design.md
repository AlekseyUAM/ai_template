# Хук code-index-guard в template (Python-порт)

Дата: 2026-11-12

## Проблема

В `deps/code-index-mcp` есть `code-index-guard` — нативный `PreToolUse`-хук
(Rust, ~2 100 строк, зависимости `serde_json` + `rusqlite`), который
перенаправляет нативные `Read`/`Grep`/`Glob`/`Bash`/`PowerShell` по
индексированным каталогам в инструменты code-index. Он блокирует **только
доказуемо отдаваемые** файлы (проверка членства в `.code-index/index.db`,
свежесть по `mtime`, исключения проекта) и на сомнительном воздерживается —
именно это защищает от дед-эндов вида «MCP этот файл не отдаёт, а нативный
Read запрещён».

В `template` такого детерминированного гарда нет: правило «по индексу читай
через code_index» живёт только текстом в агентах и навыках и под нагрузкой
деградирует. Upstream-бинарь не подходит как зависимость: template
разворачивается на произвольную ОС (Windows/Linux/macOS, в т.ч. через SSH), а
готовый exe — платформенный артефакт, который надо скачивать и обновлять.

## Цель

Дать template самодостаточный хук на Python (только stdlib), повторяющий
поведение upstream `code-index-guard` v1.15.4 для инструментов Claude Code:
`Read`, `Grep`, `Glob`, `Bash`, `PowerShell`. Конфиг с индексированными корнями
генерируется при развёртывании окружения; без конфига хук ничего не
перехватывает.

## Решения, принятые при обсуждении

- **Реализация:** Python-порт на stdlib, файл в `template/.claude/hooks/`.
  Никаких pip-пакетов, бинарей и сетевых вызовов.
- **Охват:** полный паритет с upstream — `Read`, `Grep`, `Glob`, `Bash`
  (`cat`/`head`/`tail`, `grep`/`rg`/`find`/`ls`), `PowerShell`
  (`Get-Content`, `Select-String`, `Get-ChildItem`, `findstr`).
- **Источник корней:** конфиг, который `deploy_content` пишет при создании и
  обновлении проекта из карточек MCP (`catalog_dir` + `project_name` уже есть
  в `mcp_servers`). Автопоиска `.code-index` нет.
- **Активация:** `PreToolUse`-блок добавляется в `settings.json` только когда
  в проекте выбран MCP вида `code-index`/`code-index-local`.
- **Не входит в v1:** журнал событий `events_db`, режим `--list-roots` для
  `SessionStart`, автопоиск корней, перехват `Edit`/`Write`. Это осознанный
  YAGNI: контекст сессии не тратим, правила про code_index уже есть в навыках.
- **Коммиты:** локально в `main`, без push.

## Архитектура

```
template/.claude/hooks/
  code_index_guard.py              # точка входа (exec по пути, ~15 строк)
  code_index_guard_lib/
    cli.py                         # stdin/stdout, контракт хука, dispatch
    config.py                      # разбор code-index-guard.toml, daemon.toml
    paths.py                       # нормализация, match_indexed, исключения, glob
    index_db.py                    # serveability по index.db (ленивый sqlite3)
    shell.py                       # разбор цепочек Bash/PowerShell
    bash.py                        # решения для Bash
    powershell.py                  # решения для PowerShell
    redirect.py                    # общий хвост redirect-веток
    decisions.py                   # Read / Grep / Glob
    tools.py                       # имена MCP-инструментов с префиксом
  code-index-guard.toml            # генерируется deploy-ем (в template — нет)
  code-index-guard.toml.example    # образец для ручного развёртывания
```

Пакет `code_index_guard_lib` — рядом с точкой входа; при запуске скрипта его
каталог уже в `sys.path`, поэтому импорт работает без установки. Разделение на
модули — чтобы каждый кусок можно было тестировать и менять независимо;
точка входа остаётся одной командой в `settings.json`.

### Контракт хука

- **stdin:** JSON `{ "tool_name", "tool_input", "cwd" }`.
- **stdout:** `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "deny"|"allow", "permissionDecisionReason": ...}}`
  либо ничего (воздержаться).
- **exit:** всегда 0. Любая ошибка/исключение → пустой stdout.
- `Read(offset=1, limit=1)` по индексированному файлу — `allow` (ритуальное
  чтение для гейта `Edit`).
- Тексты отказов содержат точные имена инструментов code-index
  (`mcp__<имя>__read_file`, `...__grep_code`, `...__grep_text`,
  `...__list_files`, `...__get_function`, `...__get_file_summary`,
  `...__stat_file`, `...__get_stats`).

### Конфиг хука

Путь: env `CODE_INDEX_GUARD_CONFIG` → иначе `code-index-guard.toml` рядом с
точкой входа. Формат совместим с upstream; добавлен необязательный
`mcp_prefix` (в upstream это флаг `--mcp-prefix`):

```toml
mcp_prefix = "mcp__code_index__"

# Либо прямой список корней:
[[local]]
path = "C:/proj/src/cf"
alias = "proj"

# Либо daemon.toml индексатора (можно вместе с [[local]] — списки
# объединяются, приоритет у путей из daemon.toml):
# daemon_toml = "C:/tools/code-index/daemon.toml"
```

- `[[local]]` и `[[paths]]` из `daemon.toml` объединяются с дедупликацией по
  пути; приоритет у `daemon.toml`.
- env `CODE_INDEX_DAEMON_TOML` переопределяет `daemon_toml`.
- Нет конфига / нет корней → индексированных путей нет, хук воздерживается.
- `mcp_prefix` по умолчанию `mcp__code_index__`; CLI `--mcp-prefix <p>`
  переопределяет его (паритет с upstream).
- `--list-roots` принимается и завершает работу с пустым stdout (режим не
  реализуется в v1).

### Проверка членства в индексе

Повторяет upstream:

- БД: `<root>/.code-index/index.db`, открытие read-only
  (`file:...?mode=ro`).
- Схема v5: `text_contents`; v4: `text_files`; выбор по наличию таблицы.
- SQL: строка `files` по `path = rel` (на Windows/macOS — `COLLATE NOCASE`),
  подзапрос наличия текста и `file_contents.oversize`, `files.mtime`.
- `Serveable`: есть текст **или** `oversize = 0`. `oversize = 1`, голая строка
  или отсутствие строки — не отдаётся.
- Свежесть: файл на диске новее `files.mtime` → индекс отстал, воздерживаемся.
- Нет локального `index.db` → пер-файловая проверка невозможна, `Read`
  пропускается.

### Исключения из индекса

- Встроенные сегменты: `.git`, `node_modules`, `.code-index`, `target`,
  `__pycache__`, `.venv`.
- Конкретный существующий файл, который `read_is_blockable` не подтверждает,
  считается неиндексируемым (дотфайлы, `Dockerfile`, `.svg` и т.п.).
- `.code-index/config.json` проекта: `exclude_dirs` (сегмент) и
  `exclude_file_patterns` (glob по каждому сегменту, `*` — любой отрезок).

### Разбор Bash/PowerShell

Порт upstream-функций без упрощений:

- Цепочка делится по `&&`, `||`, `;`, `\n` с учётом кавычек; одиночная труба
  обрывает разбор (правее — фильтрация чужого вывода, а не файлы).
- Тела heredoc'ов и here-string'ов вырезаются как данные.
- Присваивания `root="..."` учитываются для последующих звеньев; подстановки
  `$VAR`/`$(...)`/обратные кавычки → цель неизвестна → воздержаться.
- `cd`/`pushd`/`Set-Location`/`Push-Location` меняют базу; `popd`/`cd -` →
  база неизвестна → воздержаться. `~`, `..`, `.`, `/d`, `-Path`/`-LiteralPath`
  раскрываются.
- `git grep`/`git log -S` — история, индексом не покрыта → пропуск.
- `ls`/`Get-ChildItem` по существующим файлам — взгляд на размер/дату →
  пропуск; по каталогу/маске/без целей — отказ.
- `cat`/`head`/`tail`/`Get-Content` по одному индексированному файлу →
  `read_file` после проверки членства и свежести; пайпы/редиректы/маски/
  несколько файлов/неизвестные флаги → воздержаться.
- Repo-wide `grep`/`rg`/`find`/`ls`/`Select-String`/`Get-ChildItem`/`findstr`
  → `grep_code`/`grep_text`/`list_files`; cwd-fallback только для команд без
  явного пути; бинарные расширения → пропуск.
- MSYS-пути `/c/...` → `c:/...`. Регистр путей: Windows/macOS — без учёта,
  Linux — с учётом; имена команд и ключи — без учёта везде.

### Интеграция с env-системой

1. `config_schema.McpSelection` получает необязательные поля
   `catalog_dir: str | None = None`, `project_name: str | None = None`.
2. Обе точки сборки `EnvConfig` (`project_api._create`,
   `project_api._build_update_config`) заполняют их из строки `mcp_servers`.
3. `content.deploy_content`:
   - пишет `.claude/hooks/code-index-guard.toml` из включённых
     `code-index`/`code-index-local` с непустым `catalog_dir`:
     `[[local]] path=<catalog_dir> alias=<project_name | последний сегмент>`;
     при отсутствии таких карточек — пустой файл (нейтрализует устаревший
     конфиг при обновлении);
   - `mcp_prefix` = `mcp__<фактическое имя сервера>__` (из
     `mcp_name_overrides`, дефолт `mcp__code_index__`);
   - если code-index выбран — добавляет в `settings.json` первым
     `PreToolUse`-хуком запись с матчером
     `Read|Grep|Glob|Bash|PowerShell`, `timeout: 10` и командой
     `<venv-python> "$CLAUDE_PROJECT_DIR/.claude/hooks/code_index_guard.py"`;
   - сгенерированный `code-index-guard.toml` исключается из `put_tree`
     (`_is_special`), чтобы при обновлении не появлялся `.bak` и не
     затирался ручной конфиг шаблоном.

## Ошибки и отказоустойчивость

- Любое исключение в хуке → пустой stdout, exit 0 (как у остальных хуков
  template).
- `sqlite3` импортируется лениво: платим только за вызовы `Read`.
- Ошибка SQL (рассинхрон схемы) → stderr-предупреждение, решение
  «воздержаться».
- Битый JSON на stdin / не-dict → воздержаться.
- Нет `index.db` / нет конфига / нет корней → хук не перехватывает.

## Производительность

- Стоимость запуска Python: ожидаемо ~40–80 мс на вызов (импорт пакета ~10–15 мс
  + запуск интерпретатора). Для сессии в сотни вызовов это единицы секунд, на
  фоне задержек модели незаметно.
- Проверка корней идёт только по путям под индексированным префиксом;
  остальные вызовы выходят рано.
- `Read` добавляет открытие `index.db` (~2–4 мс).

## Тестирование

- `app/tests/env/test_code_index_guard_config.py` — разбор `code-index-guard.toml`
  и `daemon.toml`: `[[local]]`, `[[paths]]`, экранирование, комментарии,
  дедупликация, alias по умолчанию, env-override.
- `..._paths.py` — `match_indexed` (вложенные префиксы, MSYS, `\`, регистр),
  `normalize_dir`, исключения, glob.
- `..._index_db.py` — `serveability` на временной `index.db` (v4/v5, текст,
  oversize, отсутствие строки), свежесть `mtime`.
- `..._read_grep_glob.py` — решения Read/Grep/Glob, ритуальный
  `Read(1,1)`, несуществующий путь, бинарные расширения.
- `..._bash.py` — цепочки, пайпы, heredoc, `cd repo && grep`, `git grep`,
  `ls` по файлу, `cat`/`head`/`tail`, присваивания, MSYS.
- `..._powershell.py` — `Get-Content`, `Select-String`, `Get-ChildItem`,
  here-string, `-Path`/`-TotalCount`/`-Tail`.
- `..._cli.py` — контракт stdin/stdout, `deny`/`allow`/пусто, устойчивость к
  битому JSON, `--mcp-prefix`, отсутствие конфига.
- Корпус проб, адаптированный из upstream
  `crates/code-index-guard/tests/probes/probes.json`: ~30 различений
  «отказ/пропуск» на временном фикстурном репо.
- `app/tests/env/test_content_deploy.py` — генерация конфига, пустой конфиг без
  code-index, кастомное имя MCP, вставка/отсутствие `PreToolUse`, `_is_special`.
- `app/tests/env/test_config_schema.py` — round-trip новых полей
  `McpSelection`.
- Опциональный parity-тест против upstream-exe: если задан
  `CODE_INDEX_GUARD_EXE`, прогнать тот же корпус через бинарь и сравнить
  вердикты; иначе skip.

## Ограничения и риски

- **Дрейф от upstream.** Порт фиксируется на v1.15.4 (commit
  `4f55d0d44b4b2789a426a2d2096d6051c0de9c4b`) с MIT-атрибуцией; при обновлении
  `deps/code-index-mcp` — отдельная задача сверки.
- **Ложные отказы.** Смягчаются принципом «при сомнении пропустить», проверкой
  членства и корпусом проб. Если MCP-сервер лежит, а `index.db` есть, отказ
  приведёт к ошибке code-index — как в upstream; health-check не делаем.
- **macOS с регистрозависимой ФС.** Как в upstream, macOS считается
  регистронезависимой; редкий кейс ложного пропуска/отказа принимаем.
- **Производительность.** См. раздел выше; при необходимости хук можно
  отключить, убрав блок из `settings.json` (откат).
- **Ручное развёртывание template.** Конфиг не генерируется — пользователь
  копирует `code-index-guard.toml.example` и правит пути; без конфига хук
  инертен.

## Совместимость

- Python 3.10+ (как весь проект), только stdlib.
- Windows / Linux / macOS; пути и регистр — по правилам ОС.
- Claude Code (имена инструментов с префиксом `mcp__<server>__`). Codex CLI не
  является целью, но `--mcp-prefix` позволяет использовать хук и там.
- Лицензия upstream — MIT; в docstring точки входа и модуля конфига
  указывается источник и версия.
