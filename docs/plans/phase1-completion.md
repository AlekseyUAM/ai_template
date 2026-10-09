# План: завершение Фазы 1

Источники требований: `docs/PHASES.md` (раздел «## Фаза 1»), `tmp/NOTE.md`,
`tmp/NOTE1.md` (справочник MCP). Канонические имена стандартных MCP («Имя в .mcp.json»,
т.е. ключ в `.mcp.json`) — из NOTE1 / `app/src/agentmon/env/mcp_types.py`:
`1c-md`, `bsl_ls`, `1c_platform`, `1c_naparnic`, `code_index` (+ вид
`1c-md-queries` с `mcp_name` `1c-md`).

## Глобальные ограничения
- TDD: сначала падающий тест, затем реализация. Тест-набор запускается
  `~/.local/bin/pytest` из каталога `app` (pytest в venv не установлен).
- Не ломать существующие 509 тестов. JS проверять `node --check`.
- Работаем на ветке `master`, по одному коммиту на задачу, trailer
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Бэкенд БД — sqlite в тестах/деве, postgres в проде (один и тот же код).

## Задача 1 — Зависимость postgres + версия в заголовке страницы
- Добавить `psycopg[binary]` в `app/pyproject.toml` (раздел dependencies).
- Стартовая страница: `document.title` = `Agent Monitor v{версия}` (спек NOTE.md:5).
  Версию брать из `/api/env/version` (как уже делает `header.js`).
- Тесты: проверка наличия psycopg в pyproject; проверка установки document.title
  в `header.js`/`start.js` (grep-уровень в тесте страницы).
Файлы: `app/pyproject.toml`, `app/web/header.js`, тесты.

## Задача 2 — Починка drag запланированных задач + статус «остановлена»
- `tree_api.py`: добавить в каждую задачу дерева поле `status_raw` (сырой статус БД)
  рядом с русским `status`. `start.js`: фильтр перетаскивания использует
  `status_raw === "planned"` (сейчас сравнение с `"planned"` против русского текста —
  баг, drag не работает).
- `stack_api.py` `stop_stack`: для каждой running-задачи стека после `monitor.stop`
  проставлять `tr.set_status(task_id, "stopped")` (спек статус «остановлена»).
- Тесты: `test_tree_api.py` — наличие `status_raw`; `test_stack_api.py` — после
  `/stop` задача имеет статус `stopped`.
Файлы: `app/src/agentmon/env/tree_api.py`, `app/web/start.js`,
`app/src/agentmon/env/stack_api.py`, тесты.

## Задача 3 — Многостраничный мастер проекта + валидации
Спек NOTE.md:36-52.
- `project-wizard.html`/`project-wizard.js`: пошаговые страницы
  (Проект → Разработчик → Платформа → База → MCP → Модели агентов → Действия),
  кнопки Далее/Назад, «Создать» только на последней странице.
- Живая проверка имени: при вводе вызывать `/api/env/projects/validate-name`,
  ошибку показывать в `#nameError`.
- Проверка пустого каталога: `project_checks.validate_path_empty(path)` +
  вызов в `create_project` при создании (не update); отражать в UI.
- Блок требований: вызвать `GET /api/env/projects/requirements`, показать статус.
- Кнопка «Проверить доступ к базе» на шаге База → `POST .../check-db`, лог в `#dbLog`.
- Карточка «обновить версию окружения»: мастер с `?id=PID` при сабмите вызывает
  `POST /api/env/projects/{pid}/update-env` (а не create); предзаполнять MCP проекта.
- Тесты: `project_checks` пустой каталог; `project_api` update-env (happy + 404) и
  отказ при непустом каталоге; страница — наличие пошаговой разметки/кнопок.
Файлы: `app/web/project-wizard.html`, `app/web/project-wizard.js`,
`app/src/agentmon/env/project_checks.py`, `app/src/agentmon/env/project_api.py`, тесты.

## Задача 4 — `.mcp.json` проекта из справочника MCP
- Генерировать `.mcp.json` проекта из сохранённого `connection_json` связанных
  серверов справочника (поле «Подключение»), а не через `CATALOG` по `standard_key`
  (новые виды `bsl-ls`/`1c-platform`/`1c-md-queries`/`custom` отсутствуют в CATALOG →
  текущий путь падает). Каждый `connection_json` — фрагмент вида
  `"<mcp_name>": { ... }`; собрать их в `{"mcpServers": { ... }}`.
- Точка интеграции: `project_api.create_project`/`update-env` → `scaffold`.
  Сохранить обратную совместимость тестов `build_mcp_json` (мастер-пресеты) либо
  обновить их согласованно.
- Тесты: генерация `.mcp.json` из набора серверов справочника (custom + стандартные).
Файлы: `app/src/agentmon/env/mcp_catalog.py` (или новый билдер),
`app/src/agentmon/env/project_api.py`, `app/src/agentmon/env/scaffold.py`, тесты.

## Задача 5 — Возможности MCP/скилов в template/agents
Спек NOTE.md:65-66.
- Во всех 6 агентах (`template/agents/*.md`) привести имена стандартных MCP к
  каноническим: `1c-md`, `bsl_ls`, `1c_platform`, `1c_naparnic`, `code_index`;
  добавить вид `1c-md-queries` (произвольные запросы к данным).
- Отразить недостающие скилы `template/skills`: `db-*`, `interface-*`, `epf-bsp-*`,
  `erf-*`, `support-edit`, `v8-xsd-fetch`, `form-patterns`.
- Синхронизировать имена MCP в `template/skills/mcp-usage/SKILL.md`.
- Обновить `test_agent_capabilities.py` под канонические имена + покрытие скилов.
Файлы: `template/agents/*.md`, `template/skills/mcp-usage/SKILL.md`,
`app/tests/env/test_agent_capabilities.py`.

## Задача 6 — Задачи: валидация проекта до вставки + прогон тест-заглушки
- `task_api2.py`: проверять существование проекта ДО `task_repo.add`
  (сейчас задача вставляется, затем 400 — задача остаётся в БД).
- Тест диспетчера: тест-заглушка (`kind=test`) доходит от `running` до `done`
  (убедиться, что `monitor.task_status` детектит exit_code=0 → done для cmd-процесса).
- Тесты: `test_task_api2.py` — при несуществующем проекте запись не создаётся;
  `test_stack_dispatcher.py` — завершение тест-заглушки.
Файлы: `app/src/agentmon/env/task_api2.py`, тесты.

## Порядок (последовательно, без параллельных имплементеров)
1, 2, 5, 6 (независимые, низкий риск) → 3 → 4 (обе трогают project_api.py; 3 раньше).
Финал: whole-branch review субагентом, затем полный прогон и один коммит плана.
