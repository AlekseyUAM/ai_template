"""API-роутер дерева проектов и задач: GET /api/env/tree."""
import time
from fastapi import APIRouter, HTTPException


STATUS_LABELS = {
    "planned": "запланирована",
    "queued": "в очереди",
    "running": "выполняется",
    "stopped": "остановлена",
    "awaiting_user": "ожидает пользователя",
    "done": "выполнена",
    "failed": "ошибка",
}


def build_tree_router(store, now_fn=None) -> APIRouter:
    """Строит APIRouter для /api/env/tree.

    store — объект Db (P1.1) или None.
    now_fn — функция для получения текущего времени (по умолчанию time.time).

    Если store is None, возвращает 503.
    """
    if now_fn is None:
        now_fn = time.time

    router = APIRouter()

    @router.get("/api/env/tree")
    def get_tree():
        if store is None:
            raise HTTPException(status_code=503, detail="хранилище не настроено")

        from agentmon.store.projects import ProjectRepo
        from agentmon.store.tasks import TaskRepo
        from .project_checks import current_env_version

        proj_repo = ProjectRepo(store)
        task_repo = TaskRepo(store)

        # Get version
        version = current_env_version()

        # Build project list with tasks
        projects = []
        for project in proj_repo.list():
            tasks = []
            for task in task_repo.list(project_id=project["id"]):
                # Calculate elapsed_min
                started = task.get("started_at")
                if started is None:
                    elapsed_min = 0
                else:
                    finished = task.get("finished_at")
                    finished = finished if finished is not None else now_fn()
                    elapsed_min = round((finished - started) / 60, 1)

                # Get russian status label
                status = task.get("status", "")
                russian_status = STATUS_LABELS.get(status, status)

                # Build task_path. Каталог задачи именуется task#{identifier};
                # для старых записей без идентификатора — task#{id}.
                ident = (task.get("identifier") or "").strip()
                task_path = f"{project['path']}/tasks/task#{ident or task['id']}"

                tasks.append({
                    "id": task["id"],
                    "name": task["name"],
                    "task_path": task_path,
                    "elapsed_min": elapsed_min,
                    "status": russian_status,
                    "status_raw": status,
                    "stage": task.get("stage"),
                })

            projects.append({
                "id": project["id"],
                "name": project["name"],
                "path": project["path"],
                "tasks": tasks,
            })

        return {
            "version": version,
            "projects": projects,
        }

    return router
