# Исправление окружения по итогам benchmark-прогона

> **Superseded (2026-11-21):** обход с перезапуском контейнера
> (`bench_index.py`) удалён — code-index переведён на нативный запуск,
> см. `docs/superpowers/specs/2026-11-21-native-code-index-design.md`.

Дата: 2026-11-21

## Проблема

Прогон задач `benchmark/tasks` на тестовом проекте выявил дефекты **окружения**,
которое создаёт текущий репозиторий: раннера benchmark, метрик, шаблона
`.claude`, генератора `.mcp.json` и подготовки code_index. Журнал проблем —
`tmp/ISSUES.md` (файл не коммитится).

Часть пунктов журнала помечена `fixed`/`env-fixed`, но в репозитории этих
исправлений нет: правки остались в копии тестового проекта
(`D:\projects\test`). Следующий `setup_benchmark.py` их потеряет. Задача —
перенести и дополнить исправления в репозиторий, чтобы они воспроизводились
на **любом** создаваемом окружении.

## Цель

Сделать так, чтобы:

1. многострочные промпты задач/этапов/аналитика не зависели от cmd.exe и
   argv-лимита Windows;
2. метрики не путали отказы хуков с ошибками MCP, а недоступность AST-слоя
   была видна как неполнота проверок;
3. аналитик не видел собственное ещё не записанное состояние;
4. индекс code_index обновлялся между задачами автоматически;
5. сгенерированный `.mcp.json` не тратил ходы на `ToolSearch`;
6. Python-вывод на Windows не превращался в cp1251-кракозябры;
7. чеклисты и правила не заставляли модель обходить устаревший индекс
   Python-скриптами;
8. предупреждение о нераспознанной модели гасилось конфигурацией.

## Решения

- **Промпт через stdin.** `claude -p` без позиционного промпта читает stdin.
  Оба раннера (`bench_run.py`, `stage_run.py`) используют общий модуль
  `benchmark/claude_proc.py`; флаги остаются в argv, промпт пишется в stdin
  UTF-8. Это убирает зависимость от `.bat`/cmd.exe.
- **Метрики.** `tool_errors` остаётся общим счётчиком; `mcp_errors` и
  `hook_denials` — непересекающиеся подтипы, считаются по имени события и
  тексту результата, а не по подстроке в сигнатуре. Дополнительно считаются
  вызовы `Skill mcp-usage` и повторные вызовы инструментов (одна метрика).
- **Аналитик.** Перед запуском пишется снимок
  `run/analysis-inputs/metrics.json` без ключа `analysis`; дайджест
  копируется рядом. Транскрипты аналитика пишутся в
  `run/analysis-transcripts/`, а не в общий `transcripts/`. `run.finished_at`
  выставляется до запуска аналитика.
- **AST-проверки.** `query-analyze` без `node` помечается в метриках как
  `partial`; дайджест явно пишет, что структурные проверки пропущены. Node.js
  добавляется в prerequisites benchmark.
- **Индекс.** Новый `benchmark/bench_index.py` сравнивает mtime
  `src/cf/.code-index/index.db` с исходниками; при отставании перезапускает
  контейнер `ai1c-mcp-code_index` и ждёт `ready`. Включается по умолчанию,
  отключается `--no-index-refresh`.
- **MCP-схемы.** `build_mcp_json` добавляет `"alwaysLoad": true` серверам
  `code_index` и `bsl_ls` (включая переименованные карточки).
- **UTF-8.** `PYTHONUTF8=1` и `PYTHONIOENCODING=utf-8` попадают в
  отслеживаемый `template/.claude/settings.json`, в пример локальных настроек
  и в обёртки запуска. Часто вызываемые entrypoint'ы дополнительно
  переключают stdout/stderr на UTF-8.
- **Модель.** В `settings.local.json.example` добавляется `modelOverrides`
  (распознаваемый Anthropic id → фактический id модели). Предупреждение
  `[claude-code:unrecognized_model]` диагностическое, поведение не меняет.
- **Документация.** Правила про индекс, `read_file`, `validate_query`, BOM и
  обязательный `mcp-usage` правятся в `template/.claude` (текст на английском,
  как остальное окружение). Хук `route_to_checklists` выносит обязательный
  первый шаг в начало injected-context.

## Что вне области

- Изменения в `deps/code-index-mcp` (polling watcher, `POST /reindex`,
  эвристика путей в `read_file`). Это внешний репозиторий с пином на SHA;
  отдельный PR upstream.
- Конкретный тестовый проект `D:\projects\test` и его `settings.local.json`.
- Дефекты кода #9–#12 из журнала: их уже ловят `code-analyze`, `bsl_ls` и
  `validate_query`; менять нечего.

## Изменяемые компоненты

```
benchmark/
  claude_proc.py            # новый: запуск claude -p с промптом в stdin
  bench_index.py            # новый: проверка свежести и перезапуск индекса
  bench_run.py              # stdin, снимок входов аналитика, refresh, опции
  bench_analysis.py         # снимок входов, текст промпта
  bench_metrics.py          # счётчики, partial, digest
  stage_run.py              # stdin, первый шаг mcp-usage
  README.md                 # Node.js, modelOverrides
template/.claude/
  settings.json             # UTF-8 env
  settings.local.json.example
  checklists/developer.md
  skills/mcp-usage/SKILL.md
  skills/query-analyze/SKILL.md
  skills/1c-batch/scripts/1c-batch.py
  tools/run-tests.py, load-config-optimized.py, task_status.py
  hooks/route_to_checklists.py, bsl_nudge.py
  hooks/code_index_guard_lib/redirect.py
app/src/agentmon/env/
  mcp_catalog.py            # alwaysLoad
app/tests/env/
  test_mcp_catalog*.py, test_content_deploy.py, test_route_hook.py,
  test_bsl_nudge.py, test_content_conditions.py
benchmark/tests/
  test_bench_run.py, test_bench_e2e.py, test_bench_metrics.py,
  test_bench_analysis.py, test_bench_index.py
```

## Критерии приёмки

- На Windows многострочный промпт (5+ КБ) доходит до `claude` целиком; в
  `argv` его нет.
- `metrics.json` при отказе хука на `Bash` даёт `hook_denials=1`,
  `mcp_errors=0`; реальная ошибка MCP даёт `mcp_errors=1`, `hook_denials=0`.
- При отсутствии `node` дайджест показывает `query-analyze: AST пропущен`, а
  не «проверки пройдены».
- Аналитик получает `metrics.json` без ключа `analysis` и не видит
  `analyst.stream.jsonl` в списке входов.
- Перед второй задачей при устаревшем индексе раннер сам перезапускает
  контейнер и ждёт готовности; при свежем — ничего не делает.
- `.mcp.json` для `code_index`/`bsl_ls` содержит `alwaysLoad: true`.
- После деплоя в `.claude/settings.json` есть `PYTHONUTF8` и
  `PYTHONIOENCODING`.
- Чеклисты содержат: путь `read_file` без дубля типа, разрешённый native
  fallback для новых/устаревших файлов, первый вызов `list_files`, правило
  «один профиль объекта на задачу», формат `queryText` без `|`, напоминание
  про BOM.
- `pytest benchmark/tests -q` и `pytest app/tests/env -q` зелёные.
- Все изменения закоммичены локально в `main`, push не выполняется.

## Тестирование

- `pytest benchmark/tests -q` — раннер, метрики, аналитик, индекс.
- `pytest app/tests/env -q` — деплой настроек, MCP-каталог, хуки.
- Ручной прогон e2e-теста benchmark с фейковым `claude`, читающим stdin.
- Ручная проверка на Windows после `setup_benchmark.py`: промпт аналитика,
  отсутствие кракозябр, отсутствие ложных `mcp_errors`.
