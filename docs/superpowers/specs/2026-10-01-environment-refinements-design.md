# Доработки окружения (v2) — дизайн

Дата: 2026-10-01
Статус: утверждён к реализации (автономный режим; развилка по внешним скилам — выбрана пользователем)

## Контекст

Доработки по обратной связи после готовых №1-№4. Правим уже сделанный контент
окружения и установщик. Рамочные решения проекта действуют (кросс-платформа,
русский, Вариант A, без лишних зависимостей сверх необходимого).

## Изменения

### 1. Деградируемый `## Вход` субагентов (частичный набор этапов)

Проблема: агенты жёстко требуют артефакты предыдущих этапов; при включённой только
части этапов (напр. только «разработка») файлов `ANALYZE.md`/`ARCHITECT.md`/тестов
нет. Решение:
- В каждом агенте раздел `## Вход` формулируется деградируемо: «используй имеющиеся
  артефакты (`ANALYZE.md`, `ARCHITECT.md`, тесты), если их нет — опирайся на
  `TASK.md` (цель/план/ограничения)».
- В скиле `task-orchestration`: оркестратор передаёт субагенту **только реально
  существующие** артефакты + всегда `TASK.md`.

### 2. Убрать YaxUnit из `tester`

`tester.md` и `sdd-tdd-workflow` не должны хардкодить YaxUnit (его в окружении нет).
Обобщить до «тесты средствами, принятыми в проекте»; конкретный тест-раннер — вопрос
проекта/задачи, не шаблона.

### 3. Хук маршрутизации запроса к оркестратору

Нет хука, отдающего задачу оркестратору. Добавить `template/hooks/route_to_orchestrator.py`
на событие **`UserPromptSubmit`**: если промпт относится к выполнению задачи (содержит
`tasks/task#`), инжектировать `additionalContext` — «действуй как оркестратор, следуй
навыку `task-orchestration`, делегируй субагентам». Зарегистрировать в `settings.json`.
Самодостаточный Python (без agentmon), как `bsl_nudge.py`.

### 4. Вендоринг cc-1c-skills (кроме дублей 1c-batch) + 1c-batch

- **Вендорить весь не-дублирующий набор cc-1c-skills** в `template/skills/` в
  **Python-рантайме** (через их `scripts/switch.py --runtime python`), со скриптами.
- **Исключить дубли 1c-batch:** `db-create`, `db-update`, `db-run`, `db-dump-cf`,
  `db-load-cf`, `db-dump-xml`, `db-load-xml`, `db-dump-dt`, `db-load-dt`,
  `db-cfe-admin`, `epf-build`, `epf-dump`, `erf-build`, `erf-dump`. (db-repo/db-list/
  db-load-git — не дубли, оставляем.)
- **Вендорить 1c-batch** как скил в `template/skills/1c-batch/` (из `deps/1c-batch-py/src/1c-batch`).
- **Хуки cc-1c-skills** (`support-guard`, `skill-suggester`, Node) — НЕ тащим (Node-зависимость, вне нашего стека); остаёмся на своих Python-хуках.
- Зависимости их скриптов (`lxml`, `Pillow`, `psutil`) и CLI `1c-batch` ставятся **при разворачивании** (см. п.5-install).

### 5. Установщик: git init src + установка внешних инструментов + .1c-devbase.json

Дополнить установщик №1 (`installer.py`):
- Новый шаг `git-init`: `git init` в `<project>/src` (если ещё не репозиторий) + базовый `.gitignore` (logs/, *.log).
- Новый шаг `tools-install` (опциональная галка в мастере, по умолчанию вкл.):
  - `pip install` CLI `1c-batch` (из вендоренного `template/skills/1c-batch/scripts` → деплоится в `.claude/skills/1c-batch/scripts`), и зависимостей скиптов cc-1c-skills (`lxml`, `Pillow`, `psutil`).
  - Сгенерировать `<project>/.1c-devbase.json` из `ai1c.config.json` (platform_path, connection{type,path/ref}, cf_dir=src/cf, cfe_dir=src/cfe).
- Порядок шагов: layout → config → content → mcp → git-init → [dump-cf] → [dump-cfe] → [tools-install] → register.
  (git-init до выгрузки, чтобы первая выгрузка уже легла в репозиторий; коммит первичной выгрузки — опционально оркестратором/пользователем.)

### 6. Ветка git на старте задачи

Оркестратор в начале задачи создаёт ветку в `src/`:
- Добавить тул `template/tools/task_branch.py` (самодостаточный): `python task_branch.py <src_dir> <task_id>` → `git -C <src_dir> checkout -b task/<task_id>` (если ветка есть — переключиться). Используется оркестратором.
- В скиле `task-orchestration` и правиле `task-lifecycle`: перед первым изменяющим этапом создать/переключиться на `task/<id>`; все изменения — в ней.

## Границы

- Node-хуки cc-1c-skills не переносим.
- Авто-коммит изменений по этапам — не делаем (ветку создаём; коммит оставляем на усмотрение оркестратора/пользователя; можно добавить позже).
- №5 (бенчмарки) остаётся отложенной.

## Тестирование

- Агенты: `## Вход` содержит деградируемую формулировку (упоминание TASK.md как fallback); YaxUnit отсутствует в `tester.md`/`sdd-tdd-workflow`.
- `route_to_orchestrator.py`: промпт с `tasks/task#` → `additionalContext` с `task-orchestration`; без — пусто.
- `task_branch.py`: на временном git-репозитории создаёт ветку `task/<id>`; повторный вызов переключается без ошибки.
- Вендоринг: в `template/skills/` присутствуют ключевые cc-1c-skills (напр. `meta-info`, `form-edit`, `web-test`) и `1c-batch`; исключённые (напр. `db-dump-cf`, `epf-build`) отсутствуют; SKILL.md ссылается на python-скрипты (не powershell).
- Установщик: шаг `git-init` создаёт `.git` в `src/`; `.1c-devbase.json` сгенерирован с cf_dir/cfe_dir; (tools-install проверяется моками pip).
- Деплой контента: `content.py` разворачивает новые хук/тул и вендоренные скилы в `.claude/`.
- Полный набор тестов зелёный.
