"""API-роутер задач v2 с гейтами: создание, статусы, approve.

Prefix: /api/env/tasks
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .task_model import build_stages, overall_status, validate_task


def build_task2_router(store) -> APIRouter:
    """Строит APIRouter для /api/env/tasks/*.

    store — объект Db (P1.1) или None.
    Если store is None, все операции возвращают 503.
    """
    router = APIRouter()

    def require_store():
        if store is None:
            raise HTTPException(status_code=503, detail="хранилище не настроено")
        return store

    def get_repos():
        db = require_store()
        from agentmon.store.tasks import TaskRepo
        from agentmon.store.projects import ProjectRepo
        return TaskRepo(db), ProjectRepo(db)

    def task_or_404(task_repo, tid: int) -> dict:
        task = task_repo.get(tid)
        if task is None:
            raise HTTPException(status_code=404, detail=f"нет задачи с id={tid}")
        return task

    # ── POST /api/env/tasks — создать задачу ─────────────────────────────────

    @router.post("/api/env/tasks")
    def create_task(body: dict):
        task_repo, project_repo = get_repos()

        project_id = body.get("project_id")
        name = body.get("name", "")
        identifier = body.get("identifier", "")
        goal = body.get("goal", "")
        plan = body.get("plan", "")
        constraints = body.get("constraints", "")
        tests = body.get("tests", "")
        enabled_stages = body.get("enabled_stages", [])
        gated_stages = body.get("gated_stages", [])
        update_db = bool(body.get("update_db", False))
        interactive = bool(body.get("interactive", False))
        mark_changes = bool(body.get("mark_changes", False))

        # Валидация project_id
        if not project_id:
            raise HTTPException(status_code=400, detail={"errors": ["project_id обязателен"]})

        # Максимальная длительность: положительное целое число минут (по умолчанию 60).
        try:
            max_minutes = int(body.get("max_minutes", 60))
        except (TypeError, ValueError):
            max_minutes = 0
        if max_minutes < 1:
            raise HTTPException(status_code=400, detail={
                "errors": ["Максимальная длительность выполнения должна быть "
                           "положительным числом минут"]})

        # Валидация
        errors = validate_task(
            name=name,
            identifier=identifier,
            goal=goal,
            plan=plan,
            constraints=constraints,
            tests=tests,
            enabled_names=enabled_stages,
        )
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})

        # Проверить что проект существует
        project = project_repo.get(project_id)
        if project is None:
            raise HTTPException(status_code=400, detail={"errors": ["проект не найден"]})

        # Идентификатор должен быть уникален в рамках проекта (из него строится имя каталога).
        identifier = identifier.strip()
        for existing in task_repo.list(project_id=project_id):
            if (existing.get("identifier") or "").strip() == identifier:
                raise HTTPException(status_code=400, detail={
                    "errors": [f"Задача с идентификатором '{identifier}' уже существует в проекте"]})

        # Построить этапы
        stages = build_stages(enabled_stages, gated_stages)

        # Сохранить в БД
        tid = task_repo.add(
            project_id=project_id,
            name=name,
            identifier=identifier,
            goal=goal,
            plan=plan,
            constraints=constraints,
            tests=tests,
            stages_json=json.dumps(stages, ensure_ascii=False),
            status="planned",
            stage=None,
            update_db=update_db,
            max_minutes=max_minutes,
            interactive=interactive,
            mark_changes=mark_changes,
        )

        # Записать файлы на диск
        project_path = Path(project["path"])
        task_dir = project_path / "tasks" / f"task#{identifier}"
        task_dir.mkdir(parents=True, exist_ok=True)

        # TASK.md
        task_md_content = f"""# Задача {identifier} (#{tid}): {name}

## Цель
{goal}

## План
{plan}

## Ограничения
{constraints}

## Тесты
{tests}

## Параметры выполнения
- Обновлять базу данных и расширения: {"да" if update_db else "нет"}
- Выделять изменения в коде идентификаторами: {"да" if mark_changes else "нет"}
- Максимальная длительность выполнения: {max_minutes} мин
"""
        (task_dir / "TASK.md").write_text(task_md_content, encoding="utf-8")

        # task.json — дамп без stages_json (только parsed stages)
        task_row = task_repo.get(tid)
        task_data = dict(task_row) if task_row else {}
        task_data.pop("stages_json", None)
        # interactive нужен только монитору агентов, при реализации задачи не
        # используется — в task.json его не пишем.
        task_data.pop("interactive", None)
        # update_db / mark_changes в task.json — булевы (true/false), а не 0/1 из БД.
        task_data["update_db"] = bool(task_data.get("update_db"))
        task_data["mark_changes"] = bool(task_data.get("mark_changes"))
        # developer_id — идентификатор разработчика (из проекта). Нужен разработчику
        # для обрамления кода маркерами при включённом mark_changes.
        task_data["developer_id"] = project.get("identifier", "")
        task_data["stages"] = stages
        (task_dir / "task.json").write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        task = task_repo.get(tid)
        return {"task": task}

    # ── GET /api/env/tasks — список ───────────────────────────────────────────

    @router.get("/api/env/tasks")
    def list_tasks(project_id: int | None = None):
        task_repo, _ = get_repos()
        tasks = task_repo.list(project_id=project_id)
        return {"tasks": tasks}

    # ── GET /api/env/tasks/{id} — получить задачу ─────────────────────────────

    @router.get("/api/env/tasks/{tid}")
    def get_task(tid: int):
        task_repo, _ = get_repos()
        task = task_or_404(task_repo, tid)
        return {"task": task}

    # ── DELETE /api/env/tasks/{id} ────────────────────────────────────────────

    @router.delete("/api/env/tasks/{tid}")
    def delete_task(tid: int):
        task_repo, _ = get_repos()
        task_or_404(task_repo, tid)
        task_repo.delete(tid)
        return {"ok": True}

    # ── POST /api/env/tasks/{id}/stage — обновить статус этапа ───────────────

    @router.post("/api/env/tasks/{tid}/stage")
    def update_stage(tid: int, body: dict):
        task_repo, _ = get_repos()
        task = task_or_404(task_repo, tid)

        stage_name = body.get("stage")
        stage_status = body.get("status")
        changed_files = body.get("changed_files", [])

        if not stage_name or not stage_status:
            raise HTTPException(status_code=400, detail="stage и status обязательны")

        stages = json.loads(task.get("stages_json") or "[]")

        # Проверить что этап существует
        stage_names = [s["name"] for s in stages]
        if stage_name not in stage_names:
            raise HTTPException(status_code=400, detail=f"неизвестный этап: {stage_name}")

        # Обновить нужный этап
        for stage in stages:
            if stage["name"] == stage_name:
                stage["status"] = stage_status
                if changed_files:
                    stage["changed_files"] = list(dict.fromkeys(list(stage.get("changed_files", [])) + list(changed_files)))
                break

        # Пересчитать overall
        new_overall = overall_status(stages)

        # Обновить в БД
        task_repo.update(tid, stages_json=json.dumps(stages, ensure_ascii=False))
        task_repo.set_status(tid, new_overall, stage=stage_name)

        task = task_repo.get(tid)
        return {"task": task}

    # ── POST /api/env/tasks/{id}/approve — одобрить гейт ─────────────────────

    @router.post("/api/env/tasks/{tid}/approve")
    def approve_stage(tid: int, body: dict):
        task_repo, _ = get_repos()
        task = task_or_404(task_repo, tid)

        stage_name = body.get("stage")

        stages = json.loads(task.get("stages_json") or "[]")

        # Проверить что этап существует
        stage_names = [s["name"] for s in stages]
        if stage_name not in stage_names:
            raise HTTPException(status_code=400, detail=f"неизвестный этап: {stage_name}")

        # Проставить approved=True для указанного этапа
        for stage in stages:
            if stage["name"] == stage_name:
                stage["approved"] = True
                break

        # Пересчитать overall
        new_overall = overall_status(stages)

        # Обновить в БД
        task_repo.update(tid, stages_json=json.dumps(stages, ensure_ascii=False))
        task_repo.set_status(tid, new_overall)

        task = task_repo.get(tid)
        return {"task": task}

    # ── GET /api/env/tasks/{id}/overall ───────────────────────────────────────

    @router.get("/api/env/tasks/{tid}/overall")
    def get_overall(tid: int):
        task_repo, _ = get_repos()
        task = task_or_404(task_repo, tid)

        stages = json.loads(task.get("stages_json") or "[]")
        ov = overall_status(stages)
        return {"overall": ov}

    return router
