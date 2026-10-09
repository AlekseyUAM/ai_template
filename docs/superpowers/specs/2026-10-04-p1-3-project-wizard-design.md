# P1.3 — Мастер и карточка проекта — дизайн

Дата: 2026-10-04. Статус: утверждён (Фаза 1, одобрено заранее).

## Контекст
Проекты хранятся в `ProjectRepo` (P1.1). Многостраничный мастер создаёт проект,
валидирует, проверяет БД/требования, разворачивает окружение (переиспользуя установщик
Фазы 0) и пишет `env_version`. Карточка показывает проект (имя/каталог неизменяемы) и
даёт «обновить версию окружения» (мастер с предзаполненными полями). Источник
требований — `tmp/NOTE.md`.

## Решения
- `ProjectRepo` — источник истины метаданных проекта (+ `env_version`). При создании
  проект также регистрируется в agentmon-registry (path/backend=local), чтобы монитор
  Фазы 0 мог его запускать.
- Разворачивание переиспользует существующий `env/installer.install_environment` (он
  уже делает content/mcp/git-init/dump/tools). `EnvConfig` строится из данных мастера.
- Версия окружения — файл `template/VERSION` (semver). Проект хранит версию, с которой
  развёрнут; «обновить» перезапускает deploy и пишет текущую версию.
- MCP на шаге мастера выбираются из справочника MCP (P1.2).

## API (`env/project_api.py`, в create_app)
- `POST /api/env/projects/validate-name` `{name}` → `{ok, error?}` (python-идентификатор:
  `name.isidentifier()` и не ключевое слово).
- `POST /api/env/projects/check-requirements` → список `{name, ok, detail}` (python,
  docker, git, каталог платформы, claude в PATH).
- `POST /api/env/projects/check-db` `{platform_dir, db_kind, db_connection, user,
  password}` → `{ok, log}` (через `1c-batch`/платформу; инъекция runner).
- `POST /api/env/projects/create` `{...все поля..., mcp_ids[], agents[], actions{dump_cf,
  dump_cfe, install_tools}}` → создаёт запись ProjectRepo + registry + разворачивает;
  возвращает `{project, events}` (события установщика как лог).
- `GET /api/env/projects` / `GET /api/env/projects/{id}` (карточка) / `POST
  /api/env/projects/{id}/update-env` (перезапуск deploy, bump версии).
- `GET /api/env/version` → содержимое `template/VERSION`.

## Валидации и обязательные поля
Обязательные: имя, каталог, идентификатор, email, каталог платформы, версия, тип базы,
строка подключения. Имя — python-идентификатор (проверка на вводе). Каталог нового
проекта должен быть пустым (или отсутствовать). На шаге «Действия» — лог разворачивания.

## Web — мастер и карточка
- `/project-wizard` — одностраничный SPA с шагами Проект → Разработчик → Платформа →
  База → MCP → Модели агентов → Действия (Далее/Назад, обязательные поля отмечены,
  проверка имени/БД/требований, лог разворачивания). Открывается в отдельной вкладке.
- `/projects` — справочник: список проектов, кнопка «Создать проект» (→ wizard), карточка
  (имя/каталог только чтение, версия окружения, «Обновить версию окружения» → wizard
  предзаполненный). Тёмная тема GitHub.

## Границы
- Старый одностраничный `/create-project` остаётся (не удаляем в P1.3), но верхнее меню
  ведёт на новый `/projects`/`/project-wizard`.
- Стартовая страница/дерево — P1.5; задачи v2 — P1.4.

## Тестирование
- validate-name (идентификатор/не-идентификатор/ключевое слово); check-requirements
  (структура, инъекция проверок); check-db (инъекция runner, ok/fail+log).
- create: пишет ProjectRepo + registry + разворачивает (на tmp, фейковый run для dump/
  tools), env_version из template/VERSION; get/list/card; update-env перезапускает.
- template/VERSION существует; `/api/env/version` отдаёт.
- Страницы `/project-wizard` и `/projects` отдаются.
- Полный набор зелёный.
