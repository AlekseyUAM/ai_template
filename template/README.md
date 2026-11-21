# template/ — шаблон разворачиваемого окружения

Здесь хранится содержимое окружения Claude-агентов, которое разворачивается в `.claude/` проекта:

- `checklists/` — чеклисты этапов задачи (analyst, architect, developer-tests, developer,
  reviewer, technical-writer). Это не субагенты: задача выполняется одним потоком,
  чеклист читается и проходится исполнителем. Этап `testing` отдельного чеклиста не
  имеет — его ведёт исполнитель по правилу `single-agent-workflow`.
- `skills/` — навыки агентов (каждый в отдельном подкаталоге со своим `SKILL.md`)
- `rules/` — правила работы; основное — `single-agent-workflow.md` (этапы, git,
  загрузка в ИБ, тесты, циклы)
- `hooks/` — хуки:
  - `bsl_nudge.py` — подсказки при редактировании BSL;
  - `route_to_checklists.py` — UserPromptSubmit-хук: включает single-agent режим и
    перечисляет enabled-этапы задачи как чеклисты (с учётом `TASK_STAGE`);
  - `code_index_guard.py` — PreToolUse-хук: перенаправляет нативные
    Read/Grep/Glob/Bash/PowerShell по индексированным каталогам в инструменты
    `code_index`. Конфиг `code-index-guard.toml` генерируется при развёртывании
    окружения; без него хук инертен. `max_denies` (по умолчанию 2) ограничивает
    число отказов подряд для одного вызова — после исчерпания нативный вызов
    разрешается, чтобы локальная модель не зациклилась. Откат — удалить блок
    `PreToolUse` из `.claude/settings.json`; обновление окружения впишет его
    заново, для постоянного отключения уберите MCP code-index из проекта.
- `tools/` — вспомогательные инструменты (например, `task_status.py`)
- `CLAUDE.md` — краткий протокол single-agent режима (разворачивается в корень проекта)
- `settings.local.json.example` — пример локального профиля LLM (лимиты контекста,
  deny на Agent/Task, `claudeMdExcludes`). Скопируйте в `.claude/settings.local.json`
  и подставьте адрес/токен/модель; файл не входит в git.

Развёртывание выполняется функцией `content.deploy_content` из пакета `agentmon.env`.
Все правки содержимого окружения вносятся здесь — в одном очевидном месте.

## Миграция старого проекта (agents → checklists)

Начиная с версии `1.1.0` шаблон использует single-agent режим: вместо
`.claude/agents/` разворачиваются `.claude/checklists/`, а навык
`task-orchestration` удалён. Обновление окружения не удаляет устаревшие файлы,
поэтому в старом проекте один раз вручную удалите:

- `.claude/agents/` (или перенесите свои правки в `.claude/checklists/`);
- `.claude/skills/task-orchestration/`;
- `.claude/hooks/route_to_orchestrator.py`.

После этого обновите окружение из AgentMon — появится `CLAUDE.md`,
`checklists/` и новый хук `route_to_checklists.py`.
