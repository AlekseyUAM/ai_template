import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import version


class _NoCacheStatic(StaticFiles):
    """Статика без кеша — чтобы правки css/js/страниц подхватывались сразу."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


def create_app(registry, queue, monitor, lifespan=None, store=None, run=None):
    app = FastAPI(lifespan=lifespan)
    from .env.api import build_env_router
    app.include_router(build_env_router(registry))
    from .env.mcp_api import build_mcp_router
    app.include_router(build_mcp_router(store))
    from .env.project_api import build_project_router
    router_kwargs = {} if run is None else {"run": run}
    app.include_router(build_project_router(store, registry, monitor, **router_kwargs))
    from .env.task_api2 import build_task2_router
    app.include_router(build_task2_router(store))
    from .env.tree_api import build_tree_router
    app.include_router(build_tree_router(store))
    from .env.stack_api import build_stack_router
    app.include_router(build_stack_router(store, monitor))

    def project_or_404(project_id):
        project = registry.get(project_id)
        if project is None:
            raise HTTPException(status_code=404,
                                detail=f"нет проекта с id={project_id}")
        return project

    def project_json(project):
        return {
            "id": project.id,
            "name": project.name,
            "path": project.path,
            "backend": project.backend,
            "host": project.host,
            "conn": project.conn,
            "claude_cmd": project.claude_cmd,
            "alive": monitor.is_alive(project),
            "error": monitor.last_error(project),
        }

    # ── проекты ─────────────────────────────────────────────────────────────
    @app.get("/api/projects")
    def list_projects():
        return {"projects": [project_json(p) for p in registry.list()]}

    @app.post("/api/projects")
    def create_project(body: dict):
        try:
            project = registry.add(
                name=body.get("name") or "",
                path=body["path"],
                backend=body.get("backend", "local"),
                conn=body.get("conn"),
                claude_cmd=body.get("claude_cmd"),
            )
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"не задано поле {exc}")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"project": project_json(project)}

    @app.put("/api/projects/{project_id}")
    def update_project(project_id: int, body: dict):
        old = project_or_404(project_id)
        fields = {k: v for k, v in body.items()
                  if k in ("name", "path", "backend", "conn", "claude_cmd")}
        try:
            project = registry.update(project_id, **fields)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if project.key != old.key:
            # Ключ проекта — это и id агента: старый агент по новому ключу
            # уже недостижим, is_alive вернёт False, и диспетчер поднимет
            # второго агента на тот же текст задачи. Поэтому старого убиваем.
            try:
                monitor.stop(old, "kill")
            except Exception:
                pass                  # агента могло и не быть — это не ошибка
            monitor.forget(old)
        if monitor.backend_key(project) != monitor.backend_key(old):
            # Сменились параметры подключения — старое соединение к новому
            # проекту отношения не имеет и переиспользовано быть не должно.
            # Но бэкенд общий для всех проектов одного подключения, а его
            # закрытие гасит их агентов, поэтому решение принимает монитор:
            # выбросить только то соединение, которым больше никто не занят.
            # Проверка идёт после registry.update — новый ключ уже в силе.
            monitor.release_backend(old)
        return {"project": project_json(project)}

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: int):
        project = project_or_404(project_id)
        try:
            monitor.stop(project, "kill")
        except Exception:
            pass                      # агента могло и не быть — это не ошибка удаления
        monitor.forget(project)
        registry.delete(project_id)
        return {"ok": True}

    @app.post("/api/projects/{project_id}/check")
    def check_project(project_id: int):
        project = project_or_404(project_id)
        try:
            monitor.check(project)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "error": None}

    @app.post("/api/projects/{project_id}/start")
    def start_project(project_id: int):
        project = project_or_404(project_id)
        nxt = queue.next(project.id)
        if nxt is None:
            raise HTTPException(status_code=400, detail="очередь пуста")
        # Захват до запуска: атомарный queued→running не даёт параллельному
        # старту (другой HTTP-запрос или диспетчер) запустить ту же задачу дважды.
        if not queue.mark_running(nxt.id, session_id=None):
            raise HTTPException(status_code=409, detail="задача уже запущена")
        try:
            agent_id = monitor.start(project, nxt.text, task_id=nxt.id)
        except Exception as exc:
            # Старт не удался — возвращаем задачу в очередь, чтобы захват её не терял.
            queue.requeue(nxt.id)
            raise HTTPException(status_code=502, detail=str(exc))
        return {"agent_id": agent_id}

    @app.post("/api/projects/{project_id}/stop")
    def stop_project(project_id: int, body: dict | None = None):
        project = project_or_404(project_id)
        mode = (body or {}).get("mode", "interrupt")
        try:
            monitor.stop(project, mode)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return {"ok": True}

    # ── сессии ──────────────────────────────────────────────────────────────
    @app.get("/api/version")
    def get_version():
        """Код, загруженный в процесс, против кода на диске.

        Расхождение означает, что сервер надо перезапустить: морда отдаётся
        с диска и обновляется сама, а питоновские модули — нет.
        """
        return version.status()

    @app.get("/api/sessions")
    def get_sessions():
        return {"sessions": monitor.sessions()}

    @app.websocket("/ws/sessions")
    async def ws_sessions(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                # monitor.sessions() блокирующий (обходит бэкенды, включая ssh) —
                # в пуле потоков, чтобы медленный хост не вешал событийный цикл.
                sessions = await run_in_threadpool(monitor.sessions)
                await ws.send_json({"sessions": sessions})
                await asyncio.sleep(2)
        except WebSocketDisconnect:
            return

    # ── очередь ─────────────────────────────────────────────────────────────
    @app.get("/api/queue")
    def get_queue(project_id: int | None = None):
        return {"tasks": [asdict(t) for t in queue.list(project_id)]}

    @app.post("/api/queue")
    def add_task(body: dict):
        try:
            project_id = int(body["project_id"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="не задано поле project_id")
        project_or_404(project_id)
        return {"id": queue.enqueue(project_id, body.get("text", ""))}

    @app.delete("/api/queue/{task_id}")
    def del_task(task_id: int):
        queue.delete(task_id)
        return {"ok": True}

    # ── статика ─────────────────────────────────────────────────────────────
    web_dir = Path(__file__).resolve().parents[2] / "web"
    if web_dir.exists():
        @app.get("/")
        def index():
            # no-cache, чтобы страница всегда ссылалась на актуальный app.js
            return FileResponse(web_dir / "index.html",
                                headers={"Cache-Control": "no-cache"})

        @app.get("/mcp")
        def mcp_page():
            return FileResponse(web_dir / "mcp.html",
                                headers={"Cache-Control": "no-cache"})

        @app.get("/project-wizard")
        def project_wizard_page():
            return FileResponse(web_dir / "project-wizard.html",
                                headers={"Cache-Control": "no-cache"})

        @app.get("/projects")
        def projects_page():
            return FileResponse(web_dir / "projects.html",
                                headers={"Cache-Control": "no-cache"})

        @app.get("/tasks")
        def tasks_page():
            return FileResponse(web_dir / "tasks.html",
                                headers={"Cache-Control": "no-cache"})

        @app.get("/task-wizard")
        def task_wizard_page():
            return FileResponse(web_dir / "task-wizard.html",
                                headers={"Cache-Control": "no-cache"})

        app.mount("/static", _NoCacheStatic(directory=web_dir), name="static")

    return app
