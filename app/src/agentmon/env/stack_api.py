"""API стеков выполнения.

Маршруты (префикс /api/env/stacks и /api/env/tasks):
- GET  /api/env/stacks                       → список стеков с элементами
- POST /api/env/stacks                       → создать стек
- DELETE /api/env/stacks/{id}               → удалить стек (срубить прогоны)
- POST /api/env/stacks/{id}/items           → добавить задачу (только planned)
- DELETE /api/env/stacks/{id}/items/{item_id} → удалить элемент
- POST /api/env/stacks/{id}/reorder         → переставить (только не-running)
- POST /api/env/stacks/{id}/start           → запустить стек
- POST /api/env/stacks/{id}/stop            → остановить стек
- POST /api/env/tasks/test                  → создать тестовую задачу

503 возвращается для всех маршрутов, если store=None.
"""
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from agentmon.store.stacks import StackRepo
from agentmon.store.tasks import TaskRepo
from agentmon.store.projects import ProjectRepo


def _project_like(project_row) -> SimpleNamespace:
    """Строит лёгкий объект проекта из строки ProjectRepo для передачи в monitor."""
    return SimpleNamespace(
        id=project_row["id"],
        path=project_row["path"],
        name=project_row["name"],
        key="local||" + project_row["path"],
        backend="local",
        claude_cmd=None,
    )


def build_stack_router(store, monitor) -> APIRouter:
    """Строит APIRouter для API стеков.

    Если store=None — все маршруты возвращают 503.
    """
    router = APIRouter()

    def _require_store():
        if store is None:
            raise HTTPException(
                status_code=503,
                detail="хранилище задач не сконфигурировано",
            )

    def _stack_or_404(sr: StackRepo, stack_id: int) -> dict:
        stack = sr.get(stack_id)
        if stack is None:
            raise HTTPException(status_code=404, detail=f"стек id={stack_id} не найден")
        return stack

    def _enrich_items(sr: StackRepo, tr: TaskRepo, pr: ProjectRepo, stack_id: int) -> list:
        """Возвращает элементы стека, обогащённые данными задачи."""
        result = []
        for item in sr.items(stack_id):
            task = tr.get(item["task_id"])
            if task is None:
                continue
            result.append({
                "item_id": item["id"],
                "task_id": task["id"],
                "task_name": task["name"],
                "project_id": task["project_id"],
                "task_status": task["status"],
            })
        return result

    def _stack_json(stack: dict, items: list) -> dict:
        return {
            "id": stack["id"],
            "name": stack["name"],
            "status": stack["status"],
            "items": items,
        }

    # ── GET /api/env/stacks ───────────────────────────────────────────────────

    @router.get("/api/env/stacks")
    def list_stacks():
        _require_store()
        sr = StackRepo(store)
        tr = TaskRepo(store)
        pr = ProjectRepo(store)
        result = []
        for stack in sr.list():
            items = _enrich_items(sr, tr, pr, stack["id"])
            result.append(_stack_json(stack, items))
        return {"stacks": result}

    # ── POST /api/env/stacks ──────────────────────────────────────────────────

    @router.post("/api/env/stacks")
    def create_stack(body: dict):
        _require_store()
        name = (body or {}).get("name") or ""
        if not name:
            raise HTTPException(status_code=400, detail="поле name обязательно")
        sr = StackRepo(store)
        stack_id = sr.add(name=name)
        stack = sr.get(stack_id)
        return {"stack": {"id": stack["id"], "name": stack["name"], "status": stack["status"]}}

    # ── DELETE /api/env/stacks/{id} ───────────────────────────────────────────

    @router.delete("/api/env/stacks/{stack_id}")
    def delete_stack(stack_id: int):
        _require_store()
        sr = StackRepo(store)
        tr = TaskRepo(store)
        pr = ProjectRepo(store)
        _stack_or_404(sr, stack_id)

        # для каждого элемента стека: если задача running и проект жив → stop
        for item in sr.items(stack_id):
            task = tr.get(item["task_id"])
            if task is None:
                continue
            project_row = pr.get(task["project_id"])
            if project_row is None:
                continue
            proj = _project_like(project_row)
            if monitor.is_alive(proj):
                try:
                    monitor.stop(proj)
                except Exception:
                    pass

        sr.delete(stack_id)
        return {"ok": True}

    # ── POST /api/env/stacks/{id}/items ──────────────────────────────────────

    @router.post("/api/env/stacks/{stack_id}/items")
    def add_item(stack_id: int, body: dict):
        _require_store()
        sr = StackRepo(store)
        tr = TaskRepo(store)
        _stack_or_404(sr, stack_id)

        task_id = (body or {}).get("task_id")
        if task_id is None:
            raise HTTPException(status_code=400, detail="поле task_id обязательно")

        task = tr.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"задача id={task_id} не найдена")
        if task["interactive"]:
            raise HTTPException(
                status_code=400,
                detail="интерактивную задачу нельзя добавить в стек — выполните её вручную",
            )
        if task["status"] != "planned":
            raise HTTPException(
                status_code=400,
                detail=f"задачу можно добавить в стек только в статусе 'planned', "
                       f"текущий статус: {task['status']}",
            )

        # проверяем, не находится ли задача уже в каком-либо стеке
        existing = store.one(
            "SELECT id FROM stack_items WHERE task_id=?", [task_id]
        )
        if existing is not None:
            raise HTTPException(status_code=400, detail="задача уже в стеке")

        try:
            sr.add_item(stack_id, task_id)
        except Exception:
            # UNIQUE constraint violation — задача уже добавлена
            raise HTTPException(status_code=400, detail="задача уже в стеке")
        return {"ok": True}

    # ── DELETE /api/env/stacks/{id}/items/{item_id} ───────────────────────────

    @router.delete("/api/env/stacks/{stack_id}/items/{item_id}")
    def remove_item(stack_id: int, item_id: int):
        _require_store()
        sr = StackRepo(store)
        _stack_or_404(sr, stack_id)
        sr.remove_item(item_id)
        return {"ok": True}

    # ── POST /api/env/stacks/{id}/reorder ─────────────────────────────────────

    @router.post("/api/env/stacks/{stack_id}/reorder")
    def reorder_stack(stack_id: int, body: dict):
        _require_store()
        sr = StackRepo(store)
        stack = _stack_or_404(sr, stack_id)

        if stack["status"] == "running":
            raise HTTPException(
                status_code=400,
                detail="нельзя изменить порядок задач в запущенном стеке",
            )

        task_ids = (body or {}).get("task_ids", [])
        sr.reorder(stack_id, task_ids)
        return {"ok": True}

    # ── POST /api/env/stacks/{id}/start ──────────────────────────────────────

    @router.post("/api/env/stacks/{stack_id}/start")
    def start_stack(stack_id: int):
        _require_store()
        sr = StackRepo(store)
        _stack_or_404(sr, stack_id)
        sr.set_status(stack_id, "running")
        return {"ok": True}

    # ── POST /api/env/stacks/{id}/stop ────────────────────────────────────────

    @router.post("/api/env/stacks/{stack_id}/stop")
    def stop_stack(stack_id: int):
        _require_store()
        sr = StackRepo(store)
        tr = TaskRepo(store)
        pr = ProjectRepo(store)
        _stack_or_404(sr, stack_id)

        # срубаем текущий прогон running-задачи стека
        for item in sr.items(stack_id):
            task = tr.get(item["task_id"])
            if task is None:
                continue
            if task["status"] == "running":
                project_row = pr.get(task["project_id"])
                if project_row is None:
                    continue
                proj = _project_like(project_row)
                if monitor.is_alive(proj):
                    try:
                        monitor.stop(proj)
                    except Exception:
                        pass
                tr.set_status(task["id"], "stopped")

        sr.set_status(stack_id, "stopped")
        return {"ok": True}

    # ── POST /api/env/tasks/test ──────────────────────────────────────────────

    @router.post("/api/env/tasks/test")
    def create_test_task(body: dict):
        _require_store()
        project_id = (body or {}).get("project_id")
        if project_id is None:
            raise HTTPException(status_code=400, detail="поле project_id обязательно")

        pr = ProjectRepo(store)
        project_row = pr.get(project_id)
        if project_row is None:
            raise HTTPException(
                status_code=400,
                detail=f"проект id={project_id} не найден",
            )

        name = (body or {}).get("name") or "Тест"
        tr = TaskRepo(store)
        task_id = tr.add(
            project_id=project_id,
            name=name,
            goal="",
            plan="",
            constraints="",
            tests="",
            stages_json="[]",
            status="planned",
            stage=None,
            kind="test",
        )
        task = tr.get(task_id)
        return {"task": dict(task)}

    return router
