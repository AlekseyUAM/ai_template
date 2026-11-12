# template/ — шаблон разворачиваемого окружения

Здесь хранится содержимое окружения Claude-агентов, которое разворачивается в `.claude/` проекта:

- `agents/` — промпты субагентов (analyst, architect, developer-tests, developer, reviewer, technical-writer); этап `testing` ведёт оркестратор сам, субагента-тестировщика нет
- `skills/` — навыки агентов (каждый в отдельном подкаталоге со своим `SKILL.md`)
- `rules/` — правила работы агентов
- `hooks/` — хуки (например, `bsl_nudge.py` для подсказок при редактировании BSL)
- `code_index_guard.py` — PreToolUse-хук: перенаправляет нативные
  Read/Grep/Glob/Bash/PowerShell по индексированным каталогам в инструменты
  `code_index`. Конфиг `code-index-guard.toml` генерируется при развёртывании
  окружения; без него хук инертен. Откат — удалить блок `PreToolUse` из
  `.claude/settings.json`.
- `tools/` — вспомогательные инструменты (например, `task_status.py`)

Развёртывание выполняется функцией `content.deploy_content` из пакета `agentmon.env`.
Все правки содержимого окружения вносятся здесь — в одном очевидном месте.
