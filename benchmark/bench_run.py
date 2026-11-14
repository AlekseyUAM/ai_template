"""Оркестрация benchmark-прогона: конфиг, preflight, запуск задач, git, процесс агента."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class BenchError(RuntimeError):
    """Ожидаемая ошибка benchmark-раннера."""


_MINUTES_RE = re.compile(
    r"^(\d+)\s*(м|мин|m|min|ч|час|часа|часов|h|hour|hours)?$",
    re.IGNORECASE)


@dataclass(frozen=True)
class TaskInfo:
    folder: str
    path: Path
    identifier: str
    max_minutes: int
    status: str
    raw: dict


@dataclass(frozen=True)
class RunOptions:
    repo_root: Path
    project_dir: Path
    tasks: list[TaskInfo]
    limits: dict[str, int]
    claude_cmd: str
    analysis_timeout_min: int
    skip_analysis: bool
    force: bool
    run_dir: Path | None
    env_file: Path


def parse_minutes(value: str) -> int:
    """Разобрать длительность: 30, 30м, 30m, 2ч, 2h."""
    match = _MINUTES_RE.fullmatch((value or "").strip())
    if not match:
        raise BenchError(f"некорректная длительность: {value!r}")
    number = int(match.group(1))
    unit = (match.group(2) or "м").lower()
    if number < 1:
        raise BenchError(f"длительность должна быть больше нуля: {value!r}")
    if unit in ("ч", "час", "часа", "часов", "h", "hour", "hours"):
        return number * 60
    return number


def parse_limit_arg(value: str) -> tuple[str, int]:
    """Разобрать --limit <селектор>=<длительность>."""
    if "=" not in value:
        raise BenchError(f"--limit: ожидается <задача>=<минуты>, получено {value!r}")
    selector, raw = value.split("=", 1)
    selector = selector.strip()
    if not selector:
        raise BenchError(f"--limit: пустой селектор в {value!r}")
    return selector, parse_minutes(raw)


def read_env_file(path: Path) -> dict[str, str]:
    """Простой парсер key=value: комментарии и пустые строки игнорируются."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def resolve_project_dir(cli_project: str | None, env_path: Path,
                        repo_root: Path) -> Path:
    raw = cli_project
    if not raw:
        raw = read_env_file(env_path).get("BENCH_PROJECT_DIR")
        if not raw:
            raise BenchError(
                f"BENCH_PROJECT_DIR не задан: укажите --project или заполните {env_path}")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    path = path.resolve()
    if not path.is_dir():
        raise BenchError(f"каталог проекта не найден: {path}")
    return path


def discover_tasks(project_dir: Path) -> list[TaskInfo]:
    tasks_root = project_dir / "tasks"
    if not tasks_root.is_dir():
        raise BenchError(f"нет каталога задач: {tasks_root}")
    tasks: list[TaskInfo] = []
    for path in sorted(tasks_root.iterdir(), key=lambda p: p.name):
        if not path.is_dir() or not path.name.startswith("task##"):
            continue
        task_json = path / "task.json"
        if not task_json.is_file():
            raise BenchError(f"{path.name}: нет task.json")
        try:
            data = json.loads(task_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchError(f"{path.name}/task.json: {exc}") from exc
        data = data if isinstance(data, dict) else {}
        try:
            max_minutes = int(data.get("max_minutes"))
        except (TypeError, ValueError) as exc:
            raise BenchError(
                f"{path.name}/task.json: max_minutes должен быть целым числом") from exc
        if max_minutes < 1:
            raise BenchError(f"{path.name}/task.json: max_minutes должен быть ≥ 1")
        identifier = str(data.get("identifier") or path.name.removeprefix("task#"))
        tasks.append(TaskInfo(
            folder=path.name,
            path=path,
            identifier=identifier,
            max_minutes=max_minutes,
            status=str(data.get("status") or ""),
            raw=data,
        ))
    if not tasks:
        raise BenchError(f"в {tasks_root} нет задач task##*")
    return tasks


def _task_aliases(task: TaskInfo) -> set[str]:
    aliases = {
        task.folder,
        task.identifier,
        task.identifier.removeprefix("#"),
        task.folder.removeprefix("task##"),
    }
    aliases.discard("")
    return aliases


def _match_task(tasks: list[TaskInfo], selector: str) -> TaskInfo | None:
    matches = [task for task in tasks if selector in _task_aliases(task)]
    if len(matches) != 1:
        return None
    return matches[0]


def select_tasks(tasks: list[TaskInfo], selectors: list[str]) -> list[TaskInfo]:
    if not selectors:
        return list(tasks)
    selected: list[TaskInfo] = []
    missing: list[str] = []
    for selector in selectors:
        task = _match_task(tasks, selector.strip())
        if task is None:
            missing.append(selector)
        elif task not in selected:
            selected.append(task)
    if missing:
        raise BenchError("неизвестные или неоднозначные задачи: " + ", ".join(missing))
    return [task for task in tasks if task in selected]


def apply_limits(tasks: list[TaskInfo], limit_args: list[str]) -> dict[str, int]:
    limits = {task.folder: task.max_minutes for task in tasks}
    seen: set[str] = set()
    for raw in limit_args:
        selector, minutes = parse_limit_arg(raw)
        task = _match_task(tasks, selector)
        if task is None:
            raise BenchError(f"--limit: неизвестная задача {selector!r}")
        if task.folder in seen:
            raise BenchError(f"--limit: лимит для {task.folder} задан дважды")
        seen.add(task.folder)
        limits[task.folder] = minutes
    return limits


def prepare_run_dir(project_dir: Path) -> Path:
    base = project_dir / "tmp" / "benchmark"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base / stamp
    suffix = 2
    while candidate.exists():
        candidate = base / f"{stamp}-{suffix}"
        suffix += 1
    (candidate / "diffs").mkdir(parents=True)
    (candidate / "transcripts").mkdir()
    return candidate


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Прогон benchmark-задач и анализ template")
    parser.add_argument("--project", help="каталог проекта (приоритетнее test.env)")
    parser.add_argument("--env", help="env-файл; по умолчанию benchmark/test.env")
    parser.add_argument("--task", action="append", default=[],
                        dest="task_selectors",
                        help="задача: task##001, #001 или 001 (повторяемый)")
    parser.add_argument("--limit", action="append", default=[], dest="limit_args",
                        help="лимит: task##001=30, #002=2ч (повторяемый)")
    parser.add_argument("--claude-cmd", default="claude-ds",
                        help="команда агента (по умолчанию claude-ds)")
    parser.add_argument("--analysis-timeout", type=int, default=30,
                        help="лимит аналитика в минутах (по умолчанию 30)")
    parser.add_argument("--skip-analysis", action="store_true",
                        help="не запускать сессию-аналитик")
    parser.add_argument("--force", action="store_true",
                        help="разрешить прогон на непустом проекте")
    return parser.parse_args(argv)


def build_options(ns: argparse.Namespace, repo_root: Path) -> RunOptions:
    repo_root = Path(repo_root).resolve()
    if ns.env:
        env_path = Path(ns.env).expanduser()
        if not env_path.is_absolute():
            env_path = (repo_root / env_path).resolve()
    else:
        env_path = repo_root / "benchmark" / "test.env"
    project_dir = resolve_project_dir(ns.project, env_path, repo_root)
    tasks = discover_tasks(project_dir)
    selected = select_tasks(tasks, ns.task_selectors)
    limits = apply_limits(selected, ns.limit_args)
    if ns.analysis_timeout < 1:
        raise BenchError("--analysis-timeout должен быть ≥ 1")
    if not ns.claude_cmd.strip():
        raise BenchError("--claude-cmd не может быть пустым")
    return RunOptions(
        repo_root=repo_root,
        project_dir=project_dir,
        tasks=selected,
        limits=limits,
        claude_cmd=ns.claude_cmd.strip(),
        analysis_timeout_min=ns.analysis_timeout,
        skip_analysis=bool(ns.skip_analysis),
        force=bool(ns.force),
        run_dir=None,
        env_file=env_path,
    )
