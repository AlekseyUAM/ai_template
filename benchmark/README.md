# Benchmark

Эталонный набор задач для оценки работы ИИ-агентов AgentMon на реальной
конфигурации 1С.

## Состав

| Путь | Назначение |
|------|------------|
| `cf/` | Конфигурация 1С в формате XML-выгрузки — исходное состояние, на котором выполняются задачи из `tasks/`. Объектов, создаваемых задачами, в ней нет. |
| `tasks/` | Задачи в состоянии сразу после заведения в AgentMon: только `TASK.md` и `task.json`, без артефактов выполнения (отчётов этапов, `task.diff`, служебных файлов). |

## Задачи

Задачи выполнялись последовательно на одной конфигурации: каждая следующая
может опираться на объекты, созданные предыдущими.

| Каталог | id | Задача |
|---------|----|--------|
| `tasks/task#001` | #23 | Метаданные оперативного учета |
| `tasks/task#002` | #24 | Учетная политика |
| `tasks/task#003` | #25 | Приходная накладная |
| `tasks/task#004` | #26 | Расходная накладная |
| `tasks/task#005` | #27 | Форма документа Расходная накладная |
| `tasks/task#006` | #28 | Отчет Продажи |
| `tasks/task#007` | #29 | Отчет Остатки товаров |

`id` — внутренний номер задачи в AgentMon (он же в заголовке `TASK.md` и в
логах `logs/task#NN`); каталог и `identifier` в `task.json` — `task#NNN`/`#NNN`.
Полный набор этапов включён только в `task#004` (`plan`, `tests`, `develop`,
`testing`, `review`); у остальных задач включён только `develop`. Состав
этапов задаётся флагами `enabled` в `task.json`.

## Использование

Конфигурация загружается из `cf/` в `src/cf` проекта, задачи копируются в
`tasks/` проекта и выполняются через AgentMon.

## Подготовка окружения

Команды выполняются из корня репозитория. Интерпретатор виртуального окружения:
`.venv/bin/python` на Linux/macOS и `.venv\Scripts\python.exe` на Windows
(venv создаётся командой `python bootstrap.py`).

1. Скопируйте пример и заполните значения:

   ```bash
   # Linux / macOS
   cp benchmark/example.test.env benchmark/test.env
   ```

   ```bat
   :: Windows (cmd)
   copy benchmark\example.test.env benchmark\test.env
   ```

   `benchmark/test.env` содержит пароль 1С и в git не попадает.

2. Запустите из корня репозитория:

   ```bash
   # Linux / macOS
   .venv/bin/python benchmark/setup_benchmark.py
   ```

   ```bat
   :: Windows (cmd)
   .venv\Scripts\python.exe benchmark\setup_benchmark.py
   ```

   В PowerShell команда та же, путь можно записать как
   `.\.venv\Scripts\python.exe .\benchmark\setup_benchmark.py`.

   Если проект с таким именем или каталогом уже есть, скрипт сначала проверяет
   конфигурацию и доступность MCP, затем удаляет его каталог, запись в store и
   реестре и создаёт проект заново. Непустой каталог без признаков
   benchmark-проекта (`.1c-devbase.json`, `.claude`, `tasks`) не удаляется.

   Скрипт создаст проект, окружение, базу (из `.dt` или из `cf/` +
   расширений), выгрузки `src/cf`/`src/cfe`, задачи в `tasks/` и БД AgentMon,
   запустит нативный code-index и дождётся полной индексации.
   При ошибке каталог проекта остаётся для диагностики; следующий запуск
   удалит его автоматически.

   code-index ставится нативно (без Docker): бинарь `bsl-indexer` скачивается
   в каталог `CODE_INDEX_DIR` из `test.env` (обязательный ключ, абсолютный путь
   вне `BENCH_PROJECT_DIR`). Каталог при каждом setup удаляется и создаётся
   заново — не указывайте общий каталог другого сервиса. Там же остаются
   `daemon.toml`, PID-файл и логи `daemon.log`/`serve.log`. Перед запуском
   старые процессы этого каталога гасятся, а откат неудачного setup
   останавливает уже запущенные процессы.

   Карточки MCP переиспользуются только при точном совпадении подключения
   (для code-index — ещё каталога базы, проекта и `CODE_INDEX_DIR`); изменение
   любого из них создаёт новую карточку.

3. Для структурных проверок `query-analyze` нужен Node.js (LTS) в `PATH`:
   `node --version`. Без него работают только текстовые правила, а метрики
   помечают проверки как неполные.

## Прогон и анализ

После подготовки окружения выполните из корня репозитория:

```bash
# Linux / macOS
.venv/bin/python benchmark/run_benchmark.py \
    --limit task#001=45 --limit task#004=180
```

```bat
:: Windows (cmd) — одной строкой, перенос через «\» не работает
.venv\Scripts\python.exe benchmark\run_benchmark.py --limit task#001=45 --limit task#004=180
```

Скрипт выполняет все задачи проекта `tasks/task#*` по очереди в `claude-ds`.
Лимит по умолчанию — `max_minutes` из `task.json`; `--limit` переопределяет его.
Значение `--limit` — целое число минут, без единиц измерения (`120`, не `2ч`).
Первый `timeout`/`failed`/`incomplete` останавливает следующие задачи, но анализ
по собранным данным всё равно выполняется.

Результаты:

- `<проект>/tmp/RESULT.md` — отчёт и рекомендации по улучшению template;
- `<проект>/tmp/benchmark/<run-id>/` — `metrics.json`, `digest.md`, диффы,
  транскрипты, промпт аналитика и сырой ответ.

Токены и стоимость не собираются: `metrics.json` и дайджест содержат время,
итерации, инструменты и тестовые прогоны, но не `usage`/`cost_usd`.

Полезные флаги:

- `--task task#001` — ограничить набор задач;
- `--skip-analysis` — только выполнить задачи и собрать метрики;
- `--force` — разрешить прогон на непустом проекте (результат помечается как
  потенциально загрязнённый);
- `--claude-cmd` — другая команда агента (по умолчанию `claude-ds`);
- `--analysis-timeout` — лимит сессии-аналитика в минутах (по умолчанию 30).

Качественный анализ выполняет отдельная сессия `claude-ds` с запретом на
`Edit`/`Write`; она возвращает markdown, который скрипт записывает в `RESULT.md`.

## Поэтапный прогон на локальной LLM

Для локальной модели предпочтителен **stage-scoped** режим: каждый этап
`task.json` выполняется отдельным процессом `claude -p` с чистым контекстом,
состояние передаётся через артефакты задачи и `task.json`.

1. Настройте проект на локальную LLM: скопируйте
   `template/.claude/settings.local.json.example` в
   `<проект>/.claude/settings.local.json`, подставьте `ANTHROPIC_BASE_URL`,
   токен и id модели. Файл не коммитится. Если модель обслуживает Strata,
   значения печатает `strata connect` — см. «Настройки из Strata» ниже.
2. Скопируйте обёртку в корень проекта; модель и адрес приходят из
   `settings.local.json`:

   ```bash
   # Linux / macOS
   cp benchmark/claude-local.sh.example <проект>/claude-local.sh
   chmod +x <проект>/claude-local.sh
   ```

   ```bat
   :: Windows (cmd)
   copy benchmark\claude-local.bat.example <проект>\claude-local.bat
   ```

   Обёртка сбрасывает унаследованные `ANTHROPIC_*` (чтобы не подхватить
   `claude-ds` из внешнего окружения) и запускает `claude` с
   `--dangerously-skip-permissions`.
3. Запустите этапы (лимиты по умолчанию — в `DEFAULT_STAGE_LIMITS`):

   ```bash
   # Linux / macOS
   .venv/bin/python benchmark/stage_run.py \
     --task task#004 --project ~/projects/test \
     --claude-cmd ~/projects/test/claude-local.sh \
     --stages plan,tests --limit-stage tests=30
   ```

   ```bat
   :: Windows (cmd) — одной строкой
   .venv\Scripts\python.exe benchmark\stage_run.py --task task#004 --project D:\projects\test --claude-cmd D:\projects\test\claude-local.bat --stages plan,tests --limit-stage tests=30
   ```

   Раннер останавливается, если этап не дошёл до `done`, не создал артефакт
   или вышел по таймауту; результаты — в `<проект>/tmp/stage-runs/<run_id>/`
   (`run.json`, `summary.md`, `<этап>.stream.jsonl`, `<этап>.prompt.txt`).
   `--dry-run` печатает промпты этапов без запуска.

Порядок этапов по умолчанию: `analyze → plan → tests → develop → testing →
review → docs`. Для локальной модели этапы `analyze`/`docs` можно отключить в
`task.json` (`enabled: false`) — раннер выполнит только включённые. Сейчас
полный набор включён только у `task#004`, у остальных задач — только `develop`,
поэтому `--stages` имеет смысл прежде всего для неё.

### Настройки из Strata

Если локальную модель обслуживает [Strata](https://github.com/Niko1221/Strata),
готовые параметры подключения печатает её CLI:

```bash
strata launch                       # запустить сервер, если ещё не запущен
strata connect claude-code          # блок env для settings.local.json
strata connect claude-code --show-key  # то же, но с реальным ключом
strata connect claude-code --check  # пробный запрос и вызов инструмента
```

`strata connect` берёт адрес, ключ и имя модели у запущенного сервера
(`strata launch`), а если сервера нет — подставляет умолчания
(`http://127.0.0.1:8080`, токен `strata-local`, модель `strata`). Перенесите
значения из блока `Environment` в `<проект>/.claude/settings.local.json`:

- `ANTHROPIC_BASE_URL` — адрес **без** `/v1`: Claude Code сам добавляет
  `/v1/messages`;
- `ANTHROPIC_AUTH_TOKEN` — ключ сервера (при запуске без ключа — `strata-local`);
- `ANTHROPIC_MODEL` и `ANTHROPIC_SMALL_FAST_MODEL`/`ANTHROPIC_DEFAULT_*` —
  имя, которое отдаёт сервер (в примере без сервера — `strata`, у реального
  запуска — имя модели);
- `CLAUDE_CODE_MAX_CONTEXT_TOKENS` и `CLAUDE_CODE_MAX_OUTPUT_TOKENS` — реальный
  контекст и лимит вывода сервера; их же печатает `strata connect`. Без них
  Claude Code считает окно равным 100K и либо не компактит, либо компактит
  каждый ход.

Флаг `--write` записывает настройки в глобальный `~/.claude/settings.json`
(с резервной копией). Для benchmark предпочтителен проектный
`settings.local.json`, чтобы не менять окружение остальных проектов.

Если Claude Code пишет в stderr `[claude-code:unrecognized_model]`, это
диагностика, а не ошибка. Погасить её можно в `settings.local.json`:

```json
"modelOverrides": {"claude-sonnet-4-6": "<фактический id модели>"}
```

При сбое аналитика отчёт всё равно создаётся — с объективной сводкой и описанием
ошибки. Старый `RESULT.md` не сохраняется.

Тесты раннера (без 1С, сети и реального `claude`):

```bash
# Linux / macOS
.venv/bin/python -m pytest benchmark/tests -q
```

```bat
:: Windows (cmd)
.venv\Scripts\python.exe -m pytest benchmark\tests -q
```
