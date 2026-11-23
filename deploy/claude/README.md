# Обёртки запуска Claude Code

Готовые обёртки для `AGENTMON_CLAUDE_CMD` (AgentMon) и для
`benchmark/test.env` / `--claude-cmd` (benchmark-раннеры). Скрипты не
содержат секретов: ключ DeepSeek читается из файла или переменной окружения.

| Файл | Назначение |
|------|------------|
| `claude-ds.bat` / `claude-ds.sh` | DeepSeek: адрес, токен и модель задаются обёрткой |
| `claude-local.bat` / `claude-local.sh` | Локальная LLM (Strata и любая другая): настройки берутся из `.claude/settings.local.json` проекта |

Обе обёртки **не меняют рабочий каталог** и передают все аргументы в
`claude --dangerously-skip-permissions`.

## Установка в PATH

Каталог `%USERPROFILE%\.local\bin` (Windows) или `~/.local/bin` (Linux/macOS)
должен быть в `PATH`.

Windows (cmd):

```bat
copy deploy\claude\claude-ds.bat "%USERPROFILE%\.local\bin\"
copy deploy\claude\claude-local.bat "%USERPROFILE%\.local\bin\"
where claude-ds
where claude-local
```

Linux/macOS:

```bash
cp deploy/claude/claude-ds.sh ~/.local/bin/claude-ds
cp deploy/claude/claude-local.sh ~/.local/bin/claude-local
chmod +x ~/.local/bin/claude-ds ~/.local/bin/claude-local
```

Проверка: `claude-ds --version` и `claude-local --version`.

## DeepSeek

Ключ берётся из переменной `DEEPSEEK_API_KEY`, иначе из файла
`%USERPROFILE%\.config\deepseek\key` (`~/.config/deepseek/key` на Linux/macOS).
Если ключа нет, обёртка завершается с кодом 1 и пишет, куда его положить.

Адрес, модель (`deepseek-flash[1m]`) и лимиты заданы в самой обёртке.

## Локальная LLM

Настройки модели (адрес сервера, токен, id модели, лимиты контекста) лежат в
`<проект>/.claude/settings.local.json`:

- автоматически — `BENCH_STRATA_SETTINGS=1` в `benchmark/test.env`;
  `setup_benchmark.py` берёт значения у `strata connect claude-code` и пишет
  файл сам (см. `benchmark/README.md`, раздел «Настройки из Strata»);
- вручную — `strata connect claude-code`, затем перенести env-блок в
  `settings.local.json`.

Запускайте обёртку **из каталога проекта**: cwd не меняется, и Claude Code
читает `.claude/settings.local.json` именно оттуда. AgentMon и benchmark-раннеры
передают каталог проекта сами.

Обёртка сбрасывает унаследованные `ANTHROPIC_*` (чтобы не подхватить DeepSeek
из внешнего окружения) и выставляет `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` —
иначе на Windows вывод скриптов 1С приходит в cp1251.

Не кладите обёртку внутрь benchmark-проекта: `setup_benchmark.py` пересоздаёт
каталог целиком, и скрипт пропадёт.

## `AGENTMON_CLAUDE_CMD`

AgentMon Web UI читает переменную из `.ai1c.env`:

```ini
AGENTMON_CLAUDE_CMD=claude-ds
# или
AGENTMON_CLAUDE_CMD=claude-local
```

После правки перезапустите AgentMon. Настройка глобальная — для всех проектов.
Переопределение команды у отдельного проекта через API допускает только
команду с именем `claude` (`claude`, `claude.exe`, `claude.cmd`, `claude.bat`;
защита от запуска произвольных бинарников), поэтому обёртки задавайте здесь,
в `.ai1c.env`.

Benchmark-раннеры читают тот же ключ из `benchmark/test.env`:

```ini
AGENTMON_CLAUDE_CMD=claude-ds
```

`run_benchmark.py` и `stage_run.py` берут команду оттуда, `--claude-cmd`
переопределяет её, а если значения нет ни там, ни там — останавливаются с
ошибкой.

Формат значения: короткое имя (ищется в `PATH`, включая `.exe`/`.bat`/`.cmd`
на Windows) или полный путь. Команда может содержать аргументы; путь с
пробелами берите в кавычки:

```ini
AGENTMON_CLAUDE_CMD="C:\Program Files\Claude\claude.bat" --flag
```

`AGENTMON_CLAUDE_CMD` в `.ai1c.env` и в `benchmark/test.env` — разные файлы:
первый задаёт агента для Web UI, второй — для benchmark-прогона. Указывайте в
них одну и ту же обёртку, если прогон идёт и так, и так.

## Почему PATH, а не каталог проекта

`benchmark/setup_benchmark.py` при каждом запуске удаляет и создаёт проект
заново. Обёртки внутри проекта теряются; в `PATH` они переживают setup и
подходят сразу для всех проектов.
