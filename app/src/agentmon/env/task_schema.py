import json
from dataclasses import dataclass, asdict
from pathlib import Path

# Единый источник этапов — task_model (живая DB-модель). Файловая система задач
# использует те же определения, чтобы они не разъезжались.
from .task_model import DEFAULT_STAGES, STAGE_NAMES

ID_BASE = 100001


@dataclass
class Stage:
    name: str
    enabled: bool
    subagent: str
    artifact: str
    status: str
    changed_files: list


@dataclass
class TaskSpec:
    id: str
    title: str
    goal: str
    plan: str
    constraints: str
    created_at: float | None
    stages: list

    def to_dict(self) -> dict:
        base = {k: getattr(self, k) for k in
                ("id", "title", "goal", "plan", "constraints", "created_at")}
        base["stages"] = [asdict(s) for s in self.stages]
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        data = dict(data)
        data["stages"] = [Stage(**s) for s in data.get("stages", [])]
        return cls(**data)


def build_stages(enabled_names) -> list:
    enabled = set(enabled_names)
    stages = []
    for d in DEFAULT_STAGES:
        on = d["name"] in enabled
        stages.append(Stage(name=d["name"], enabled=on, subagent=d["subagent"],
                            artifact=d["artifact"],
                            status="pending" if on else "skipped",
                            changed_files=[]))
    return stages


def _tasks_dir(project_dir) -> Path:
    return Path(project_dir) / "tasks"


def next_task_id(project_dir) -> str:
    tasks, ids = _tasks_dir(project_dir), []
    if tasks.exists():
        for p in tasks.iterdir():
            if p.is_dir() and p.name.startswith("task#"):
                tail = p.name[len("task#"):]
                if tail.isdigit():
                    ids.append(int(tail))
    return f"{(max(ids) + 1) if ids else ID_BASE:06d}"


def task_dir(project_dir, task_id) -> Path:
    return _tasks_dir(project_dir) / f"task#{task_id}"


def _task_md(spec) -> str:
    return (f"# {spec.title}\n\n## Цель\n{spec.goal}\n\n## План\n{spec.plan}\n\n"
            f"## Ограничения\n{spec.constraints}\n")


def save_task(task_dir_path, spec) -> None:
    (Path(task_dir_path) / "task.json").write_text(
        json.dumps(spec.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def load_task(task_dir_path) -> TaskSpec:
    data = json.loads((Path(task_dir_path) / "task.json").read_text(encoding="utf-8"))
    return TaskSpec.from_dict(data)


def create_task(project_dir, *, title, goal, plan, constraints,
                enabled_stages, now=None) -> TaskSpec:
    task_id = next_task_id(project_dir)
    spec = TaskSpec(id=task_id, title=title, goal=goal, plan=plan,
                    constraints=constraints, created_at=now,
                    stages=build_stages(enabled_stages))
    d = task_dir(project_dir, task_id)
    d.mkdir(parents=True, exist_ok=True)
    save_task(d, spec)
    (d / "TASK.md").write_text(_task_md(spec), encoding="utf-8")
    return spec


def list_tasks(project_dir) -> list:
    tasks, out = _tasks_dir(project_dir), []
    if tasks.exists():
        for p in sorted(tasks.iterdir()):
            if p.is_dir() and (p / "task.json").exists():
                out.append(load_task(p))
    return out


def update_stage(task_dir_path, stage_name, *, status, changed_files=None) -> None:
    spec = load_task(task_dir_path)
    for s in spec.stages:
        if s.name == stage_name:
            s.status = status
            for f in (changed_files or []):
                if f not in s.changed_files:
                    s.changed_files.append(f)
            save_task(task_dir_path, spec)
            return
    raise ValueError(f"неизвестный этап: {stage_name}")


def task_folder_name(task_id, identifier=None) -> str:
    """Имя каталога задачи: task#{identifier} (v2) или task#{id} (файловые/старые).

    Префикс `task#` обязателен — по нему хук route_to_orchestrator распознаёт
    выполнение задачи (ищет `tasks/task#` в промпте).
    """
    ident = (identifier or "").strip()
    return f"task#{ident}" if ident else f"task#{task_id}"


def orchestration_prompt(task_id, identifier=None) -> str:
    folder = task_folder_name(task_id, identifier)
    return (f"Выполни задачу tasks/{folder} по этапам из её task.json. "
            f"Следуй навыку task-orchestration.")
