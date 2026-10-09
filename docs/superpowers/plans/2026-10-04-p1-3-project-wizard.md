# P1.3 — Мастер и карточка проекта — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Многостраничный мастер проекта (валидации, проверки БД/требований, лог разворачивания, версия окружения), справочник/карточка проектов; хранение в ProjectRepo, разворачивание через существующий install_environment.

**Tech:** Python 3.10+, FastAPI, pytest. Без сборки. Тексты на русском.

## Global Constraints
- ProjectRepo — источник истины метаданных + env_version; при создании также registry.add (local).
- Разворачивание = `env/installer.install_environment` (reuse). EnvConfig строится из полей мастера; mcp_ids резолвятся из McpRepo в McpSelection(mode="managed").
- Версия окружения — `template/VERSION` (semver).
- `create_app` уже получает `store` (P1.2). Проверки БД/dump/tools — через инъекцию runner (тесты без докера/платформы).

## Files
- Create: `template/VERSION` (например `1.0.0`)
- Create: `app/src/agentmon/env/project_checks.py` (validate_name, requirements, build_check_db_command, check_db)
- Create: `app/src/agentmon/env/project_api.py` (роутер) ; Modify `app/src/agentmon/api.py` (подключить + страницы)
- Create: `app/web/project-wizard.html/.js`, `app/web/projects.html/.js`; Modify `app/web/index.html` (меню)
- Tests: `app/tests/env/test_project_checks.py`, `test_project_api.py`, `test_project_pages.py`

---

## Task 1: Проверки + версия (project_checks.py + template/VERSION)
**Interfaces:**
- `validate_name(name) -> (ok: bool, error: str|None)` — `name.isidentifier()` и `not keyword.iskeyword(name)`; иначе error на русском.
- `requirements(run=subprocess.run) -> list[dict]` — проверяет наличие `python3`/`docker`/`git`/`claude` (через `shutil.which`) + возвращает `[{name, ok, detail}]`. (platform_dir проверяется отдельно при наличии пути.)
- `current_env_version() -> str` — читает `template/VERSION` (корень репо).

- [ ] Step1 failing test `app/tests/env/test_project_checks.py`:
```python
from agentmon.env import project_checks as pc

def test_validate_name():
    assert pc.validate_name("demo")[0] is True
    assert pc.validate_name("2bad")[0] is False
    assert pc.validate_name("import")[0] is False      # ключевое слово
    assert pc.validate_name("with space")[0] is False

def test_requirements_structure():
    reqs = pc.requirements()
    names = {r["name"] for r in reqs}
    assert {"python3", "docker", "git", "claude"} <= names
    assert all(set(r) >= {"name", "ok", "detail"} for r in reqs)

def test_current_env_version():
    assert pc.current_env_version().strip() != ""
```
- [ ] Step2 run (fails). `cd app && PYTHONPATH=src python -m pytest tests/env/test_project_checks.py -q`
- [ ] Step3 implement: create `template/VERSION` with `1.0.0`; implement project_checks (validate_name via `keyword`/`str.isidentifier`; requirements via `shutil.which`; current_env_version reads `Path(__file__).resolve().parents[4] / "template" / "VERSION"`). Russian details.
- [ ] Step4 pass. Step5 commit `feat(project): проверки имени/требований + версия окружения`.

---

## Task 2: Проверка доступа к базе (project_checks.check_db)
**Interfaces:** `build_check_db_command(platform_dir, db_kind, db_connection, user, password) -> list[str]` (вызов `1c-batch` проверки подключения; форма уточняется при интеграции); `check_db(*, platform_dir, db_kind, db_connection, user, password, run=subprocess.run) -> dict{ok, log}`.

- [ ] Step1 failing test (инъекция фейкового run: ok при rc=0 с логом; fail при rc!=0 с stderr в log; команда содержит db_connection).
- [ ] Step2 run (fails).
- [ ] Step3 implement (аналогично `platform_dump`: собрать команду, выполнить через run, вернуть {ok, log}). Комментарий, что точные флаги 1c-batch уточняются.
- [ ] Step4 pass. Step5 commit `feat(project): проверка доступа к базе`.

---

## Task 3: API мастера/справочника (project_api.py)
**Interfaces:** `build_project_router(store, registry) -> APIRouter`; `create_app(...)` подключает его (store уже есть; передать registry). McpRepo/ProjectRepo поверх store.
Маршруты:
- `POST /api/env/projects/validate-name` → `{ok,error}`.
- `GET /api/env/projects/requirements` → `{requirements:[...]}`.
- `POST /api/env/projects/check-db` → `{ok,log}`.
- `GET /api/env/version` → `{version}`.
- `POST /api/env/projects/create` body `{name,path,identifier,email,platform_dir,
  platform_version,db_kind,db_connection,web_publication?,mcp_ids[],agents[],update?,
  dump_cf?,dump_cfe?,install_tools?}` →:
  1. validate_name; обязательные поля → 400 при отсутствии; (пустой каталог — предупреждение, не блок в тестах).
  2. `pid = ProjectRepo.add(..., env_version=current_env_version())`.
  3. build EnvConfig (mcp из McpRepo по mcp_ids → McpSelection(id, enabled=True, mode="managed"); agents из тела).
  4. `events = list(install_environment(config, update=update, register=lambda c: _reg(registry,c), dump_cf=..., dump_cfe=..., install_tools=..., run=run))` (в тестах run — фейковый rc=0).
  5. `{project: ProjectRepo.get(pid), events:[asdict...]}`.
- `GET /api/env/projects` / `GET /api/env/projects/{id}` (карточка).
- `POST /api/env/projects/{id}/update-env` → перезапустить deploy (update=True) + `ProjectRepo.update(id, env_version=current_env_version())`.
- 503 если store None.

- [ ] Step1 failing test `test_project_api.py` (TestClient с store=connect(tmp)+init_schema и registry; create с фейковым run → проект в ProjectRepo + события; validate-name; version; requirements). Для install_environment inject run через параметр роутера или модульный дефолт — в тесте передать небольшой проект на tmp-каталоге, dump/tools=False.
- [ ] Step2 run (fails). `PYTHONPATH=src:tests`.
- [ ] Step3 implement project_api.py + wire create_app (передать registry в build_project_router; create_app уже имеет registry и store).
- [ ] Step4 pass + FULL suite. Step5 commit `feat(project): API мастера и справочника проектов`.

---

## Task 4: Web — мастер и справочник
- `app/web/project-wizard.html/.js` — SPA с шагами Проект/Разработчик/Платформа/База/MCP/
  Модели/Действия (Далее/Назад; обязательные поля с `*`; кнопка «Проверить имя»→validate-name;
  «Проверить требования»→requirements; на шаге База «Проверить доступ»→check-db; MCP из
  `/api/mcp`; Модели — 6 субагентов model+effort; Действия — галки dump_cf/dump_cfe/
  install_tools + «Создать» → create, показать лог событий). Тёмная тема.
- `app/web/projects.html/.js` — список (`/api/env/projects`), «Создать проект» (→
  `/project-wizard`), карточка (имя/каталог readonly, версия, «Обновить версию окружения»
  → wizard?update с предзаполнением).
- Маршруты `/project-wizard`, `/projects` в api.py; ссылки в верхнем меню index.html.

- [ ] Step1 failing test `test_project_pages.py` (GET `/project-wizard` и `/projects` → 200 + заголовки «Создать проект»/«Проекты»; create_app со `store`).
- [ ] Step2 run (fails). Step3 implement. Step4 pass + FULL suite. Step5 commit `feat(project): web-мастер и справочник проектов`.

## Self-Review
- Проверки (T1-T2), API+deploy reuse (T3), UI (T4) покрывают спек. ProjectRepo+registry при создании. Версия из template/VERSION.
- Отложено: удаление старого `/create-project` (позже); точные флаги 1c-batch проверки БД; пустой-каталог как жёсткая блокировка (сейчас предупреждение).
