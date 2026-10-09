"""API-роутер мастера создания проекта и справочника проектов."""
import subprocess
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .config_schema import SCHEMA_VERSION, EnvConfig, McpSelection, AgentModel
from .installer import install_environment
from .project_checks import (validate_name, requirements, check_db,
                             current_env_version, is_empty_dir, infer_db_kind)


_REQUIRED_FIELDS = ("name", "path", "identifier", "email",
                    "platform_dir", "platform_version")
# db_connection может быть пустой строкой (файловая БД), но поле должно присутствовать
_PRESENT_FIELDS = ("db_connection",)


def build_project_router(store, registry, monitor=None, run=subprocess.run) -> APIRouter:
    """Строит APIRouter для /api/env/projects/* и /api/env/version.

    store — объект Db (P1.1) или None.
    Если store is None, все операции с БД возвращают 503.
    registry — ProjectRegistry (для регистрации при создании).
    run — функция запуска подпроцессов (замена в тестах).
    """
    router = APIRouter()

    def require_store():
        if store is None:
            raise HTTPException(status_code=503, detail="хранилище не настроено")
        return store

    def get_repos():
        db = require_store()
        from agentmon.store.projects import ProjectRepo
        from agentmon.store.mcp import McpRepo
        return ProjectRepo(db), McpRepo(db)

    def _register(config: EnvConfig) -> None:
        """Идемпотентная регистрация в registry при создании проекта."""
        for p in registry.list():
            if p.path == config.project_dir:
                return
        try:
            registry.add(
                name=config.project_name,
                path=config.project_dir,
                backend="local",
            )
        except ValueError:
            pass  # уже есть — идемпотентно

    # ── validate-name ────────────────────────────────────────────────────────

    @router.post("/api/env/projects/validate-name")
    def validate_name_route(body: dict):
        name = body.get("name", "")
        ok, error = validate_name(name)
        return {"ok": ok, "error": error}

    # ── requirements ─────────────────────────────────────────────────────────

    @router.get("/api/env/projects/requirements")
    def get_requirements():
        return {"requirements": requirements()}

    # ── check-db ─────────────────────────────────────────────────────────────

    @router.post("/api/env/projects/check-db")
    def check_db_route(body: dict):
        result = check_db(
            platform_dir=body.get("platform_dir", ""),
            db_kind=body.get("db_kind", ""),
            db_connection=body.get("db_connection", ""),
            user=body.get("user", ""),
            password=body.get("password", ""),
            run=run,
        )
        return result

    # ── version ──────────────────────────────────────────────────────────────

    @router.get("/api/env/version")
    def get_env_version():
        return {"version": current_env_version()}

    def _prepare_install(body: dict):
        """Валидирует тело, сохраняет проект+MCP в БД, строит EnvConfig.

        Возвращает (pid, config). Бросает HTTPException при ошибке ввода.
        """
        missing = [f for f in _REQUIRED_FIELDS if not body.get(f)]
        absent = [f for f in _PRESENT_FIELDS if f not in body]
        if missing or absent:
            all_missing = missing + absent
            raise HTTPException(
                status_code=400,
                detail=f"не заданы обязательные поля: {', '.join(all_missing)}",
            )
        ok, error = validate_name(body["name"])
        if not ok:
            raise HTTPException(status_code=400, detail=error)
        if not is_empty_dir(body["path"]):
            raise HTTPException(
                status_code=400,
                detail=f"каталог проекта должен быть пустым: {body['path']}",
            )

        project_repo, mcp_repo = get_repos()
        db_kind = body.get("db_kind") or infer_db_kind(body.get("db_connection", ""))
        pid = project_repo.add(
            name=body["name"], path=body["path"],
            identifier=body["identifier"], email=body["email"],
            platform_dir=body["platform_dir"],
            platform_version=body["platform_version"],
            db_kind=db_kind, db_connection=body["db_connection"],
            web_publication=body.get("web_publication", ""),
            env_version=current_env_version(),
        )

        mcp_selections, valid_mcp_ids = [], []
        for mcp_id in body.get("mcp_ids", []):
            row = mcp_repo.get(mcp_id)
            if row is None:
                continue
            valid_mcp_ids.append(row["id"])
            mcp_selections.append(McpSelection(
                id=row.get("standard_key") or row["name"],
                enabled=True, mode="managed",
                connection=row.get("connection_json"),
            ))
        if valid_mcp_ids:
            mcp_repo.set_for_project(pid, valid_mcp_ids)

        config = EnvConfig(
            schema_version=SCHEMA_VERSION,
            project_name=body["name"], project_dir=body["path"],
            developer_id=body["identifier"], developer_email=body["email"],
            platform_dir=body["platform_dir"],
            platform_version=body["platform_version"],
            db_kind=db_kind, db_connection=body["db_connection"],
            web_publication=body.get("web_publication", ""),
            mcp=mcp_selections,
            agents=[AgentModel(**a) for a in body.get("agents", [])],
        )
        return pid, config

    def _install_iter(config, body):
        return install_environment(
            config,
            update=bool(body.get("update")),
            register=lambda c: _register(c),
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
            install_tools=bool(body.get("install_tools")),
            git_init=bool(body.get("git_init", True)),
            db_user=body.get("user", ""),
            db_password=body.get("password", ""),
            run=run,
        )

    # ── create project (блокирующе) ───────────────────────────────────────────

    @router.post("/api/env/projects/create")
    def create_project(body: dict):
        pid, config = _prepare_install(body)
        events = list(_install_iter(config, body))
        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        return {"project": project, "events": [asdict(e) for e in events]}

    # ── create project со стримингом лога ──────────────────────────────────────

    @router.post("/api/env/projects/create/stream")
    def create_project_stream(body: dict):
        # Валидация и запись в БД — до стрима (чтобы 400 возвращался статусом)
        pid, config = _prepare_install(body)

        def gen():
            yield f"▶ Создание проекта «{config.project_name}» ({config.project_dir})\n"
            failed = False
            try:
                for ev in _install_iter(config, body):
                    detail = f" {ev.detail}" if ev.detail else ""
                    yield f"[{ev.step}] {ev.status}{detail}\n"
                    if ev.status == "error":
                        failed = True
            except Exception as exc:                       # noqa: BLE001
                failed = True
                yield f"✗ Ошибка: {exc}\n"
            yield ("\n✓ Проект создан\n" if not failed
                   else "\n✗ Установка завершилась с ошибкой\n")

        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    # ── list projects ────────────────────────────────────────────────────────

    @router.get("/api/env/projects")
    def list_projects():
        project_repo, _ = get_repos()
        return {"projects": project_repo.list()}

    # ── get project ──────────────────────────────────────────────────────────

    @router.get("/api/env/projects/{pid}")
    def get_project(pid: int):
        project_repo, mcp_repo = get_repos()
        project = project_repo.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail=f"нет проекта с id={pid}")
        # добавить id выбранных MCP для предзаполнения мастера
        mcp_rows = mcp_repo.for_project(pid)
        project = dict(project)
        project["mcp_ids"] = [row["id"] for row in mcp_rows]
        return {"project": project}

    # ── delete project ───────────────────────────────────────────────────────

    @router.delete("/api/env/projects/{pid}")
    def delete_project(pid: int):
        """Удаляет запись проекта и все его задачи из БД, останавливает прогоны.

        Каталог проекта на диске НЕ трогается.
        """
        from types import SimpleNamespace
        from agentmon.store.tasks import TaskRepo
        from agentmon.store.stacks import StackRepo

        project_repo, mcp_repo = get_repos()
        row = project_repo.get(pid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет проекта с id={pid}")

        task_repo = TaskRepo(store)
        stack_repo = StackRepo(store)
        tasks = task_repo.list(project_id=pid)

        # остановить живой прогон проекта (если есть выполняющиеся задачи)
        if monitor is not None and any(t.get("status") == "running" for t in tasks):
            proj = SimpleNamespace(
                id=row["id"], path=row["path"], name=row["name"],
                key="local||" + row["path"], backend="local", claude_cmd=None)
            try:
                if monitor.is_alive(proj):
                    monitor.stop(proj)
            except Exception:
                pass

        task_ids = {t["id"] for t in tasks}
        # снять задачи проекта из всех стеков
        for stack in stack_repo.list():
            for item in stack_repo.items(stack["id"]):
                if item["task_id"] in task_ids:
                    stack_repo.remove_item(item["id"])
        # удалить задачи, связи проект→MCP и сам проект
        for t in tasks:
            task_repo.delete(t["id"])
        mcp_repo.set_for_project(pid, [])
        project_repo.delete(pid)

        # снять регистрацию в registry по совпадению пути (каталог не удаляем)
        try:
            for p in registry.list():
                if p.path == row["path"]:
                    registry.delete(p.id)
                    break
        except Exception:
            pass

        return {"ok": True}

    # ── update-env ───────────────────────────────────────────────────────────

    def _build_update_config(pid: int):
        """Собирает (project, EnvConfig) из сохранённого проекта и его MCP.

        Бросает HTTPException 404, если проекта нет. Общая логика для
        блокирующего и стримингового эндпоинтов обновления окружения.
        """
        project_repo, mcp_repo = get_repos()
        project = project_repo.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail=f"нет проекта с id={pid}")

        # Получить MCP проекта (если есть связи через project_mcp)
        try:
            mcp_rows = mcp_repo.for_project(pid)
        except Exception:
            mcp_rows = []

        mcp_selections = []
        for row in mcp_rows:
            mcp_id_str = row.get("standard_key") or row["name"]
            mcp_selections.append(McpSelection(
                id=mcp_id_str,
                enabled=True,
                mode="managed",
                connection=row.get("connection_json"),
            ))

        config = EnvConfig(
            schema_version=SCHEMA_VERSION,
            project_name=project["name"],
            project_dir=project["path"],
            developer_id=project.get("identifier", ""),
            developer_email=project.get("email", ""),
            platform_dir=project.get("platform_dir", ""),
            platform_version=project.get("platform_version", ""),
            db_kind=project.get("db_kind", "file"),
            db_connection=project.get("db_connection", ""),
            web_publication=project.get("web_publication", ""),
            mcp=mcp_selections,
            agents=[],
        )
        return project, config

    @router.post("/api/env/projects/{pid}/update-env")
    def update_env(pid: int, body: dict | None = None):
        body = body or {}
        project, config = _build_update_config(pid)
        project_repo, _ = get_repos()

        events = list(install_environment(
            config,
            update=True,
            register=lambda c: _register(c),
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
            install_tools=bool(body.get("install_tools")),
            run=run,
        ))

        project_repo.update(pid, env_version=current_env_version())
        project = project_repo.get(pid)
        return {"project": project, "events": [asdict(e) for e in events]}

    # ── update-env со стримингом лога ──────────────────────────────────────────

    @router.post("/api/env/projects/{pid}/update-env/stream")
    def update_env_stream(pid: int, body: dict | None = None):
        body = body or {}
        # Валидация проекта — до стрима (чтобы 404 возвращался статусом).
        project, config = _build_update_config(pid)

        def gen():
            yield (f"▶ Обновление окружения «{config.project_name}» "
                   f"({config.project_dir})\n")
            failed = False
            try:
                for ev in install_environment(
                    config,
                    update=True,
                    register=lambda c: _register(c),
                    dump_cf=False,
                    dump_cfe=False,
                    install_tools=bool(body.get("install_tools")),
                    run=run,
                ):
                    detail = f" {ev.detail}" if ev.detail else ""
                    yield f"[{ev.step}] {ev.status}{detail}\n"
                    if ev.status == "error":
                        failed = True
            except Exception as exc:                       # noqa: BLE001
                failed = True
                yield f"✗ Ошибка: {exc}\n"
            if not failed:
                project_repo, _ = get_repos()
                project_repo.update(pid, env_version=current_env_version())
            yield ("\n✓ Окружение обновлено\n" if not failed
                   else "\n✗ Обновление завершилось с ошибкой\n")

        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    return router
