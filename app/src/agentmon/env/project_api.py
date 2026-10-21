"""API-роутер мастера создания проекта и справочника проектов."""
import subprocess
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .config_schema import SCHEMA_VERSION, EnvConfig, McpSelection, AgentModel
from .installer import install_environment
from .project_checks import (validate_name, requirements, check_db,
                             current_env_version, is_empty_dir, infer_db_kind)
from .task_schema import task_folder_name
from ..backends.local import LocalProvisioner
from ..backends.docker import DEFAULT_PLATFORM_DIR, docker_host_from_conn
from . import docker_image


_REQUIRED_FIELDS = ("name", "path", "identifier", "email",
                    "platform_dir", "platform_version")
# db_connection может быть пустой строкой (файловая БД), но поле должно присутствовать
_PRESENT_FIELDS = ("db_connection",)


def build_project_router(store, registry, monitor=None,
                         popen=subprocess.Popen,
                         image_exists_fn=docker_image.image_exists,
                         build_image_fn=docker_image.build_agent_image) -> APIRouter:
    """Строит APIRouter для /api/env/projects/* и /api/env/version.

    store — объект Db (P1.1) или None.
    Если store is None, все операции с БД возвращают 503.
    registry — ProjectRegistry (для регистрации при создании).
    popen — неблокирующий запуск подпроцесса (для открытия VS Code; замена в тестах).
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

    def _provisioner_for(backend, conn, path=""):
        if (backend and backend != "local"
                and monitor is not None
                and getattr(monitor, "backends", None) is not None):
            from ..models import Project
            probe = Project(id=0, name="probe", path=path, backend=backend,
                            conn=conn or {}, claude_cmd=None, created_at=0.0)
            return monitor.backends.get(probe).provisioner
        return LocalProvisioner()

    def _register(config: EnvConfig, backend="local", conn=None) -> None:
        """Идемпотентная регистрация в registry при создании проекта."""
        for p in registry.list():
            if p.path == config.project_dir:
                return
        try:
            registry.add(
                name=config.project_name,
                path=config.project_dir,
                backend=backend,
                conn=conn,
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
        return {"requirements": requirements(LocalProvisioner())}

    # ── check-db ─────────────────────────────────────────────────────────────

    @router.post("/api/env/projects/check-db")
    def check_db_route(body: dict):
        result = check_db(
            _provisioner_for(body.get("backend", "local"), body.get("conn"),
                             body.get("path", "")),
            platform_dir=body.get("platform_dir", ""),
            db_kind=body.get("db_kind", ""),
            db_connection=body.get("db_connection", ""),
            user=body.get("user", ""),
            password=body.get("password", ""),
        )
        return result

    # ── check-image ──────────────────────────────────────────────────────────

    @router.post("/api/env/projects/check-image")
    def check_image_route(body: dict):
        """Есть ли уже образ ai1c-agent:<версия> на нужном docker-демоне."""
        tag = docker_image.image_tag(body.get("platform_version", ""))
        docker_host = docker_host_from_conn(body.get("conn"))
        try:
            exists = bool(image_exists_fn(tag, docker_host=docker_host))
        except Exception:                                   # noqa: BLE001
            exists = False
        return {"exists": exists, "tag": tag}

    # ── version ──────────────────────────────────────────────────────────────

    @router.get("/api/env/version")
    def get_env_version():
        return {"version": current_env_version()}

    def _prepare_install(body: dict):
        """Валидирует тело, сохраняет проект+MCP в БД, строит EnvConfig.

        Возвращает (pid, config, prov, backend, conn, docker_build). Бросает HTTPException при ошибке ввода.

        docker_build — кортеж (distr_path, version, docker_host), если нужна сборка образа,
        либо None, если образ уже существует или backend не docker.
        """
        # Docker: образ тегируется версией платформы и переиспользуется.
        # platform_dir вшит в образ (single source of truth: docker.py).
        docker_build = None  # (distr_path, version, docker_host) если нужна сборка
        if body.get("backend") == "docker":
            if not body.get("platform_dir"):
                body = {**body, "platform_dir": DEFAULT_PLATFORM_DIR}
            tag = docker_image.image_tag(body.get("platform_version", ""))
            conn = dict(body.get("conn") or {})
            conn["image"] = tag
            body = {**body, "conn": conn}
            docker_host = docker_host_from_conn(conn)
            if not image_exists_fn(tag, docker_host=docker_host):
                if not body.get("distr_path"):
                    raise HTTPException(
                        status_code=400,
                        detail=("для docker нужно указать путь к дистрибутиву "
                                "платформы: образа %s ещё нет" % tag),
                    )
                docker_build = (body["distr_path"],
                                body.get("platform_version", ""), docker_host)

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

        backend = body.get("backend", "local")
        conn = body.get("conn")
        prov = _provisioner_for(backend, conn, body.get("path", ""))

        # Для docker каталог проекта — это том внутри контейнера. Проверить его
        # пустоту до сборки образа нельзя: is_empty_dir поднимает контейнер
        # (_ensure → container.ensure), а образа ai1c-agent:<версия> ещё нет →
        # хук _build бросает RuntimeError (→ 500). Том нового docker-проекта пуст
        # по построению, образ соберётся следующим шагом — поэтому для docker
        # предварительный гейт пустоты пропускаем.
        if backend != "docker" and not is_empty_dir(prov, body["path"]):
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
            license_server=body.get("license_server"),
        )
        return pid, config, prov, backend, conn, docker_build

    def _install_iter(config, body, prov, backend, conn):
        return install_environment(
            config,
            update=bool(body.get("update")),
            register=lambda c: _register(c, backend, conn),
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
            install_tools=bool(body.get("install_tools")),
            git_init=bool(body.get("git_init", True)),
            db_user=body.get("user", ""),
            db_password=body.get("password", ""),
            prov=prov,
        )

    # ── create project (блокирующе) ───────────────────────────────────────────

    @router.post("/api/env/projects/create")
    def create_project(body: dict):
        pid, config, prov, backend, conn, docker_build = _prepare_install(body)
        if docker_build is not None:
            # собрать образ до установки окружения; лог не стримим (блокирующий путь)
            for _ in build_image_fn(docker_build[0], docker_build[1],
                                    docker_host=docker_build[2]):
                pass
        events = list(_install_iter(config, body, prov, backend, conn))
        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        return {"project": project, "events": [asdict(e) for e in events]}

    # ── create project со стримингом лога ──────────────────────────────────────

    @router.post("/api/env/projects/create/stream")
    def create_project_stream(body: dict):
        # Валидация и запись в БД — до стрима (чтобы 400 возвращался статусом)
        pid, config, prov, backend, conn, docker_build = _prepare_install(body)

        def gen():
            yield f"▶ Создание проекта «{config.project_name}» ({config.project_dir})\n"
            failed = False
            try:
                if docker_build is not None:
                    yield f"[образ] сборка ai1c-agent:{docker_build[1]} из дистрибутива\n"
                    for line in build_image_fn(docker_build[0], docker_build[1],
                                               docker_host=docker_build[2]):
                        yield line
                for ev in _install_iter(config, body, prov, backend, conn):
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

        backend, conn = "local", None
        for p in registry.list():
            if p.path == project["path"]:
                backend, conn = p.backend, p.conn
                break
        prov = _provisioner_for(backend, conn, project["path"])

        events = list(install_environment(
            config,
            update=True,
            register=lambda c: _register(c),
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
            install_tools=bool(body.get("install_tools")),
            prov=prov,
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

        backend, conn = "local", None
        for p in registry.list():
            if p.path == project["path"]:
                backend, conn = p.backend, p.conn
                break
        prov = _provisioner_for(backend, conn, project["path"])

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
                    prov=prov,
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

    # ── refresh: синхронизировать статусы задач из их task.json ───────────────

    @router.post("/api/env/projects/{pid}/refresh")
    def refresh_project(pid: int):
        """Читает task.json каждой задачи проекта и переносит в БД актуальные
        status / stage / started_at / finished_at.

        Закрывает разрыв «файл → БД»: оркестратор правит task.json, но дерево
        монитора читает БД. Статусы `queued`/`stopped` — состояния стека, в файле
        их нет, поэтому `status` для них не перезаписываем (чтобы не выбить задачу
        из очереди); stage и отметки времени синхронизируем всегда.

        Та же логика синка task.json → БД работает в фоновом стек-раннере на
        завершении прогона (см. agentmon.env.task_sync) — чтобы гейты доезжали
        до БД без ручного refresh.
        """
        from agentmon.store.tasks import TaskRepo
        from .task_sync import sync_task_from_file

        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail=f"нет проекта с id={pid}")

        task_repo = TaskRepo(store)
        updated = 0
        for task in task_repo.list(project_id=pid):
            if sync_task_from_file(store, project["path"], task):
                updated += 1

        return {"ok": True, "updated": updated}

    # ── open-vscode: открыть каталог проекта в VS Code ────────────────────────

    @router.post("/api/env/projects/{pid}/open-vscode")
    def open_vscode(pid: int):
        """Открывает каталог проекта в VS Code (`code <path>`) на хосте монитора."""
        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        if project is None:
            raise HTTPException(status_code=404, detail=f"нет проекта с id={pid}")
        try:
            popen(["code", project["path"]])
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="команда 'code' не найдена в PATH — установите VS Code CLI")
        except Exception as exc:                           # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail=f"не удалось открыть VS Code: {exc}")
        return {"ok": True}

    # ── open-report: открыть артефакт этапа задачи в VS Code ─────────────────

    @router.post("/api/env/tasks/{tid}/open-report")
    def open_report(tid: int, body: dict):
        """Открывает артефакт указанного этапа задачи в VS Code."""
        import json
        from pathlib import Path
        from agentmon.store.tasks import TaskRepo
        task_repo = TaskRepo(store)
        task = task_repo.get(tid)
        if task is None:
            raise HTTPException(status_code=404, detail=f"нет задачи с id={tid}")
        stage_name = (body or {}).get("stage")
        try:
            stages = json.loads(task.get("stages_json") or "[]")
        except (ValueError, TypeError):
            stages = []
        stage = next((s for s in stages if s.get("name") == stage_name), None)
        if stage is None or not stage.get("artifact"):
            raise HTTPException(status_code=404,
                                detail=f"этап {stage_name!r} или его артефакт не найден")
        project_repo, _ = get_repos()
        project = project_repo.get(task["project_id"])
        if project is None:
            raise HTTPException(status_code=404, detail="проект задачи не найден")
        folder = task_folder_name(task["id"], task.get("identifier"))
        artifact_path = Path(project["path"]) / "tasks" / folder / stage["artifact"]
        if not artifact_path.exists():
            raise HTTPException(status_code=404,
                                detail=f"файл отчёта не найден: {stage['artifact']}")
        try:
            popen(["code", str(artifact_path)])
        except FileNotFoundError:
            raise HTTPException(status_code=500,
                                detail="команда 'code' не найдена в PATH — установите VS Code CLI")
        except Exception as exc:                           # noqa: BLE001
            raise HTTPException(status_code=500,
                                detail=f"не удалось открыть VS Code: {exc}")
        return {"ok": True}

    return router
