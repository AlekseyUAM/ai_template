# Автоматический прогон benchmark-задач и анализ template — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Одна команда после `benchmark/setup_benchmark.py` выполняет задачи проекта в `claude-ds` с лимитами, собирает метрики и силами отдельной сессии-аналитика пишет улучшения template в `<проект>/tmp/RESULT.md`.

**Architecture:** Самостоятельный пакет в `benchmark/` без зависимости от `agentmon`. `run_benchmark.py` — тонкий CLI; `bench_run.py` — конфиг, preflight, цикл задач, git и запуск процесса; `bench_metrics.py` — stream-json, транскрипты/сабагенты, дайджест, статические анализаторы; `bench_analysis.py` — промпт аналитика, извлечение ответа и fallback-отчёт. Все внешние вызовы инъектируются через параметры, тесты не трогают сеть, 1С и реальный `claude`.

**Tech Stack:** Python ≥ 3.10, только stdlib; pytest для тестов; git; `claude-ds` (Claude Code, DeepSeek).

## Global Constraints

- Python ≥ 3.10; раннер и его тесты — только stdlib + pytest (pytest уже есть в корневом `.venv`).
- Весь пользовательский текст (логи, ошибки, отчёт, комментарии) — на русском.
- Не добавлять зависимости в `requirements*.txt`.
- Не менять `benchmark/setup_benchmark.py`, `app/`, `template/`, `benchmark/tasks/*`, `benchmark/cf/*`.
- В коде раннера нет хардкода имён задач, папок и целевых модулей: задачи обнаруживаются в `tasks/`, лимиты — из `task.json`; `benchmark/example.bsl` — необязательный эталон.
- Лимит задачи: `max_minutes` из `task.json`, переопределяется `--limit`; таймаут убивает process group.
- Первый `timeout`/`failed`/`incomplete` останавливает следующие задачи, но анализ по собранным данным выполняется.
- `tmp/RESULT.md` — единственный итоговый отчёт; при сбое аналитика он перезаписывается детерминированной сводкой.
- Коммиты — локально в `main`, без `push`, с трейлером `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Тесты запускать из корня: `.venv/bin/python -m pytest benchmark/tests -q`.
- Секреты (`benchmark/test.env`) не печатать и не коммитить.

## Файлы

| Путь | Ответственность |
|---|---|
| `benchmark/bench_run.py` | Конфиг/CLI-парсинг, preflight, git-диффы, запуск процесса с таймаутом, цикл выполнения, логи |
| `benchmark/bench_metrics.py` | Разбор stream-json и транскриптов, дайджест, метрики этапов/тестов, статические анализаторы |
| `benchmark/bench_analysis.py` | Промпт аналитика, извлечение markdown, детерминированный fallback, запись `RESULT.md` |
| `benchmark/run_benchmark.py` | Тонкий CLI-вход |
| `benchmark/tests/conftest.py` | `sys.path` для импорта модулей `benchmark/` |
| `benchmark/tests/test_bench_run.py` | Конфиг, preflight, git, таймаут-раннер |
| `benchmark/tests/test_bench_metrics.py` | stream-json, транскрипты, метрики, анализаторы, дайджест |
| `benchmark/tests/test_bench_analysis.py` | Промпт аналитика, извлечение ответа, fallback |
| `benchmark/tests/test_bench_e2e.py` | End-to-end с фейковым `claude-cmd` |
| `benchmark/README.md` | Раздел «Прогон и анализ» |

---

### Task 1: Конфигурация, env, задачи и лимиты

**Files:**
- Create: `benchmark/bench_run.py`
- Create: `benchmark/tests/conftest.py`
- Create: `benchmark/tests/test_bench_run.py`

**Interfaces:**
- Produces: `BenchError`, `TaskInfo`, `RunOptions`, `parse_minutes(value: str) -> int`, `parse_limit_arg(value: str) -> tuple[str, int]`, `read_env_file(path: Path) -> dict[str, str]`, `resolve_project_dir(cli_project: str | None, env_path: Path, repo_root: Path) -> Path`, `discover_tasks(project_dir: Path) -> list[TaskInfo]`, `select_tasks(tasks, selectors) -> list[TaskInfo]`, `apply_limits(tasks, limit_args) -> dict[str, int]`, `prepare_run_dir(project_dir: Path) -> Path`, `parse_args(argv) -> argparse.Namespace`, `build_options(ns, repo_root: Path) -> RunOptions`.

- [ ] **Step 1: Написать падающие тесты**

`benchmark/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`benchmark/tests/test_bench_run.py`:

```python
import json
from pathlib import Path

import pytest

from bench_run import (BenchError, apply_limits, build_options, discover_tasks,
                       parse_args, parse_limit_arg, parse_minutes,
                       read_env_file, resolve_project_dir, select_tasks)


def make_project(root: Path) -> Path:
    project = root / "project"
    tasks = project / "tasks"
    for folder, ident, minutes in (("task##001", "#001", 30),
                                   ("task##002", "#002", 60)):
        task_dir = tasks / folder
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(json.dumps({
            "identifier": ident,
            "status": "planned",
            "max_minutes": minutes,
            "stages": [],
        }), encoding="utf-8")
        (task_dir / "TASK.md").write_text("# TASK\n", encoding="utf-8")
    return project


def test_parse_minutes_is_integer_minutes():
    assert parse_minutes("30") == 30
    assert parse_minutes("120") == 120
    for bad in ("0", "-1", "abc", "", "1.5", "30м", "2ч", "2h", "30 min"):
        with pytest.raises(BenchError):
            parse_minutes(bad)


def test_parse_limit_arg():
    assert parse_limit_arg("task##001=30") == ("task##001", 30)
    with pytest.raises(BenchError):
        parse_limit_arg("task##001")
    with pytest.raises(BenchError):
        parse_limit_arg("=30")


def test_read_env_file(tmp_path):
    path = tmp_path / "test.env"
    path.write_text("# comment\nA=1\nB = x y\n\n", encoding="utf-8")
    assert read_env_file(path) == {"A": "1", "B": "x y"}


def test_resolve_project_dir_from_env(tmp_path):
    project = make_project(tmp_path)
    env = tmp_path / "test.env"
    env.write_text(f"BENCH_PROJECT_DIR={project}\n", encoding="utf-8")
    assert resolve_project_dir(None, env, tmp_path) == project.resolve()
    assert resolve_project_dir(str(project), tmp_path / "missing.env",
                               tmp_path) == project.resolve()


def test_resolve_project_dir_requires_value(tmp_path):
    with pytest.raises(BenchError):
        resolve_project_dir(None, tmp_path / "missing.env", tmp_path)


def test_discover_and_select(tmp_path):
    project = make_project(tmp_path)
    tasks = discover_tasks(project)
    assert [t.folder for t in tasks] == ["task##001", "task##002"]
    assert tasks[0].identifier == "#001"
    assert tasks[0].max_minutes == 30
    assert select_tasks(tasks, []) == tasks
    assert [t.folder for t in select_tasks(tasks, ["#002"])] == ["task##002"]
    assert [t.folder for t in select_tasks(tasks, ["001"])] == ["task##001"]
    with pytest.raises(BenchError):
        select_tasks(tasks, ["nope"])


def test_apply_limits_and_duplicates(tmp_path):
    tasks = discover_tasks(make_project(tmp_path))
    assert apply_limits(tasks, []) == {"task##001": 30, "task##002": 60}
    assert apply_limits(tasks, ["#001=45"])["task##001"] == 45
    with pytest.raises(BenchError):
        apply_limits(tasks, ["#001=45", "task##001=50"])
    with pytest.raises(BenchError):
        apply_limits(tasks, ["#999=10"])


def test_build_options(tmp_path):
    project = make_project(tmp_path)
    env = tmp_path / "test.env"
    env.write_text(f"BENCH_PROJECT_DIR={project}\n", encoding="utf-8")
    ns = parse_args(["--env", str(env), "--task", "#001", "--limit", "#001=30",
                     "--analysis-timeout", "15"])
    opts = build_options(ns, tmp_path)
    assert opts.project_dir == project.resolve()
    assert [t.folder for t in opts.tasks] == ["task##001"]
    assert opts.limits == {"task##001": 30}
    assert opts.analysis_timeout_min == 15
    assert opts.run_dir is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'bench_run'`.

- [ ] **Step 3: Реализовать конфигурацию**

`benchmark/bench_run.py`:

```python
"""Оркестрация benchmark-прогона: конфиг, preflight, запуск задач, git, процесс агента."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class BenchError(RuntimeError):
    """Ожидаемая ошибка benchmark-раннера."""


_MINUTES_RE = re.compile(r"^\d+$")


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
    """Разобрать длительность в минутах: только целое число."""
    raw = (value or "").strip()
    if not _MINUTES_RE.fullmatch(raw):
        raise BenchError(
            f"некорректная длительность (нужно целое число минут): {value!r}")
    number = int(raw)
    if number < 1:
        raise BenchError(f"длительность должна быть больше нуля: {value!r}")
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
    return {
        task.folder,
        task.identifier,
        task.identifier.lstrip("#"),
        task.folder.removeprefix("task##"),
    }


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
                        help="лимит в минутах: task##001=30, #002=120 (повторяемый)")
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
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_run.py benchmark/tests/conftest.py benchmark/tests/test_bench_run.py
git commit -m "feat(bench): конфигурация и выбор задач раннера" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Preflight, git-состояние и диффы

**Files:**
- Modify: `benchmark/bench_run.py`
- Modify: `benchmark/tests/test_bench_run.py`

**Interfaces:**
- Consumes: `TaskInfo`, `BenchError`.
- Produces: `GitState`, `git_state(project_dir: Path) -> GitState`, `check_freshness(project_dir, tasks, force=False) -> list[str]`, `ensure_fresh(project_dir, tasks, force=False) -> None`, `changed_files(project_dir, before_head: str) -> list[str]`, `collect_diff(project_dir, before_head: str, out_path: Path, stat_path: Path) -> list[str]`.

- [ ] **Step 1: Дописать падающие тесты**

Добавить в `benchmark/tests/test_bench_run.py`:

```python
import subprocess

from bench_run import (check_freshness, collect_diff, git_state)


def git(project: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=project, text=True,
                          capture_output=True, check=True)
    return proc.stdout


def make_git_project(root: Path) -> Path:
    project = make_project(root)
    git(project, "init", "-q")
    git(project, "config", "user.email", "bench@example.ru")
    git(project, "config", "user.name", "Bench")
    (project / ".gitignore").write_text("/tmp\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    git(project, "commit", "-q", "--allow-empty", "-m", "baseline before task#001")
    return project


def test_check_freshness_clean_and_problems(tmp_path):
    project = make_git_project(tmp_path)
    tasks = discover_tasks(project)
    assert check_freshness(project, tasks) == []
    (tasks[0].path / "DEVELOP.md").write_text("# x\n", encoding="utf-8")
    assert any("DEVELOP" in problem for problem in check_freshness(project, tasks))
    (tasks[0].path / "DEVELOP.md").unlink()
    (project / "changed.txt").write_text("x", encoding="utf-8")
    assert any("незакоммиченные" in problem for problem in check_freshness(project, tasks))
    assert check_freshness(project, tasks, force=True) == []


def test_check_freshness_requires_planned_and_baseline(tmp_path):
    project = make_git_project(tmp_path)
    tasks = discover_tasks(project)
    data = json.loads((tasks[0].path / "task.json").read_text(encoding="utf-8"))
    data["status"] = "running"
    (tasks[0].path / "task.json").write_text(json.dumps(data), encoding="utf-8")
    problems = check_freshness(project, tasks)
    assert any("planned" in problem for problem in problems)

    project2 = make_project(tmp_path / "second")
    git(project2, "init", "-q")
    git(project2, "config", "user.email", "bench@example.ru")
    git(project2, "config", "user.name", "Bench")
    git(project2, "add", "-A")
    git(project2, "commit", "-q", "-m", "init")
    assert any("baseline" in problem
               for problem in check_freshness(project2, discover_tasks(project2)))


def test_collect_diff_includes_tracked_and_untracked(tmp_path):
    project = make_git_project(tmp_path)
    before = git_state(project).head
    tracked = project / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    git(project, "add", "tracked.txt")
    git(project, "commit", "-q", "-m", "add tracked")
    (project / "new.txt").write_text("new\n", encoding="utf-8")
    out = tmp_path / "diff.txt"
    stat = tmp_path / "stat.txt"
    changed = collect_diff(project, before, out, stat)
    text = out.read_text(encoding="utf-8")
    assert "tracked.txt" in text and "new.txt" in text
    assert "tracked.txt" in changed and "new.txt" in changed
    assert "tracked.txt" in stat.read_text(encoding="utf-8")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: FAIL с `ImportError` на `check_freshness`/`collect_diff`.

- [ ] **Step 3: Реализовать preflight и git**

Добавить в `benchmark/bench_run.py` после `RunOptions`:

```python
@dataclass(frozen=True)
class GitState:
    head: str
    status: str


_ARTIFACT_GLOBS = (
    "ANALYZE.md", "ARCHITECT.md", "TESTS*.md", "DEVELOP*.md", "TESTING*.md",
    "REVIEW*.md", "DOCS*.md", "task.diff", "USER_FEEDBACK.md",
)


def _git(project_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=project_dir, text=True,
                          capture_output=True, encoding="utf-8",
                          errors="replace")
    if check and proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip()
        raise BenchError(f"git {' '.join(args)}: {message}")
    return proc


def git_state(project_dir: Path) -> GitState:
    head = _git(project_dir, "rev-parse", "HEAD").stdout.strip()
    status = _git(project_dir, "status", "--porcelain").stdout
    return GitState(head=head, status=status)


def check_freshness(project_dir: Path, tasks: list[TaskInfo],
                    force: bool = False) -> list[str]:
    if force:
        return []
    problems: list[str] = []
    for task in tasks:
        if task.status != "planned":
            problems.append(f"{task.folder}: статус {task.status!r}, ожидается 'planned'")
        for pattern in _ARTIFACT_GLOBS:
            for _ in task.path.glob(pattern):
                problems.append(f"{task.folder}: найден артефакт выполнения {pattern}")
    state = git_state(project_dir)
    if state.status.strip():
        problems.append("в проекте есть незакоммиченные изменения (git status не пуст)")
    subject = _git(project_dir, "log", "-1", "--format=%s").stdout.strip()
    if not subject.startswith("baseline before task"):
        problems.append(
            f"HEAD не является baseline-коммитом setup'а (сейчас: {subject!r})")
    return problems


def ensure_fresh(project_dir: Path, tasks: list[TaskInfo],
                 force: bool = False) -> None:
    problems = check_freshness(project_dir, tasks, force=force)
    if problems:
        raise BenchError(
            "проект не готов к benchmark-прогону:\n- " + "\n- ".join(problems)
            + "\nПересоздайте проект через benchmark/setup_benchmark.py "
              "или запустите с --force.")


def _untracked_files(project_dir: Path) -> list[str]:
    out = _git(project_dir, "ls-files", "--others", "--exclude-standard").stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def changed_files(project_dir: Path, before_head: str) -> list[str]:
    out = _git(project_dir, "diff", "--name-only", before_head,
               check=False).stdout
    files = {line.strip() for line in out.splitlines() if line.strip()}
    files.update(_untracked_files(project_dir))
    return sorted(files)


def collect_diff(project_dir: Path, before_head: str, out_path: Path,
                 stat_path: Path) -> list[str]:
    diff = _git(project_dir, "diff", before_head, check=False).stdout
    stat = _git(project_dir, "diff", "--stat", before_head, check=False).stdout
    parts = [diff]
    stat_parts = [stat]
    for rel in _untracked_files(project_dir):
        path = project_dir / rel
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parts.append(f"\n--- /dev/null\n+++ b/{rel}\n")
        parts.extend(f"+{line}\n" for line in content.splitlines())
        stat_parts.append(f" {rel} | new file\n")
    out_path.write_text("".join(parts), encoding="utf-8")
    stat_path.write_text("".join(stat_parts), encoding="utf-8")
    return changed_files(project_dir, before_head)
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_run.py benchmark/tests/test_bench_run.py
git commit -m "feat(bench): preflight и git-диффы раннера" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Запуск агента с таймаутом и поиск транскрипта

**Files:**
- Modify: `benchmark/bench_run.py`
- Create: `benchmark/bench_metrics.py`
- Modify: `benchmark/tests/test_bench_run.py`

**Interfaces:**
- Produces: `StreamSummary`, `SessionFiles`, `parse_stream(path)`, `find_session_files(session_id, projects_root=None)`, `ClaudeRun`, `run_claude(*, cmd, prompt, cwd, timeout_sec, stream_path, stderr_path, extra_args=()) -> ClaudeRun`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `benchmark/tests/test_bench_run.py`:

```python
import sys

from bench_metrics import find_session_files, parse_stream
from bench_run import run_claude


def write_fake_claude(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_parse_stream(tmp_path):
    stream = tmp_path / "s.jsonl"
    stream.write_text("\n".join([
        json.dumps({"type": "system", "subtype": "init",
                    "session_id": "sid-1"}),
        "not json",
        json.dumps({"type": "result", "is_error": False, "result": "ok",
                    "session_id": "sid-1", "duration_ms": 5}),
    ]) + "\n", encoding="utf-8")
    summary = parse_stream(stream)
    assert summary.session_id == "sid-1"
    assert summary.result["result"] == "ok"
    assert summary.parse_errors == 1


def test_find_session_files(tmp_path):
    sid = "abc"
    project = tmp_path / "projects" / "-tmp-x"
    project.mkdir(parents=True)
    main = project / f"{sid}.jsonl"
    main.write_text("", encoding="utf-8")
    sub = project / sid / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a.jsonl").write_text("", encoding="utf-8")
    files = find_session_files(sid, projects_root=tmp_path / "projects")
    assert files.main == main
    assert files.subagents == (sub / "agent-a.jsonl",)
    assert find_session_files("missing", projects_root=tmp_path / "projects").main is None


def test_run_claude_result(tmp_path):
    fake = write_fake_claude(tmp_path / "fake", "\n".join([
        "import json",
        f"print(json.dumps({{'type':'system','subtype':'init','session_id':'sid-2'}}))",
        f"print(json.dumps({{'type':'result','is_error':False,'result':'ok','session_id':'sid-2'}}))",
    ]) + "\n")
    run = run_claude(cmd=str(fake), prompt="hi", cwd=tmp_path, timeout_sec=10,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.exit_code == 0
    assert run.timed_out is False
    assert run.stream.result["result"] == "ok"
    assert run.stream.session_id == "sid-2"


def test_run_claude_timeout_kills_process(tmp_path):
    fake = write_fake_claude(tmp_path / "sleep", "import time\ntime.sleep(30)\n")
    run = run_claude(cmd=str(fake), prompt="hi", cwd=tmp_path, timeout_sec=0.5,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.timed_out is True
    assert run.duration_sec < 10
    assert run.exit_code is not None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'bench_metrics'`.

- [ ] **Step 3: Реализовать разбор stream-json**

Создать `benchmark/bench_metrics.py`:

```python
"""Метрики benchmark-прогона: stream-json, транскрипты, дайджест, анализаторы."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StreamSummary:
    session_id: str | None = None
    init: dict = field(default_factory=dict)
    result: dict | None = None
    parse_errors: int = 0


@dataclass(frozen=True)
class SessionFiles:
    main: Path | None
    subagents: tuple[Path, ...]


def parse_stream(path: Path) -> StreamSummary:
    summary = StreamSummary()
    if not path.is_file():
        return summary
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                summary.parse_errors += 1
                continue
            if not isinstance(event, dict):
                summary.parse_errors += 1
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                summary.init = event
                summary.session_id = event.get("session_id") or summary.session_id
            elif event.get("type") == "result":
                summary.result = event
                summary.session_id = summary.session_id or event.get("session_id")
    return summary


def find_session_files(session_id: str | None,
                       projects_root: Path | None = None) -> SessionFiles:
    if not session_id:
        return SessionFiles(None, ())
    root = Path(projects_root) if projects_root else Path.home() / ".claude" / "projects"
    matches = sorted(root.glob(f"*/{session_id}.jsonl"))
    if not matches:
        return SessionFiles(None, ())
    main = matches[0]
    subdir = main.with_suffix("") / "subagents"
    subagents = tuple(sorted(subdir.glob("*.jsonl"))) if subdir.is_dir() else ()
    return SessionFiles(main, subagents)
```

- [ ] **Step 4: Реализовать запуск процесса**

Добавить в `benchmark/bench_run.py` после `collect_diff`:

```python
@dataclass
class ClaudeRun:
    exit_code: int | None
    timed_out: bool
    duration_sec: float
    stream_path: Path
    stderr_path: Path
    stream: object
    session: object


def _signal_group(proc: subprocess.Popen, sig: int, wait_sec: float) -> bool:
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        pgid = None
    try:
        if pgid is not None:
            os.killpg(pgid, sig)
        else:
            proc.send_signal(sig)
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=wait_sec)
        return True
    except subprocess.TimeoutExpired:
        return False


def _kill_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if _signal_group(proc, signal.SIGINT, 10):
        return
    if _signal_group(proc, signal.SIGTERM, 5):
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        try:
            proc.kill()
        except OSError:
            pass


def run_claude(*, cmd: str, prompt: str, cwd: Path, timeout_sec: float,
               stream_path: Path, stderr_path: Path,
               extra_args: tuple[str, ...] = ()) -> ClaudeRun:
    """Запустить claude в отдельной сессии и вернуть результат; таймаут убивает группу."""
    from bench_metrics import find_session_files, parse_stream

    argv = [cmd, "-p", prompt, "--output-format", "stream-json",
            "--verbose", *extra_args]
    stream_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with stream_path.open("wb") as out, stderr_path.open("wb") as err:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            start_new_session=True)
        try:
            exit_code = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc)
            exit_code = proc.wait()
        except BaseException:
            _kill_group(proc)
            raise
    duration = time.monotonic() - started
    stream = parse_stream(stream_path)
    session = find_session_files(stream.session_id)
    return ClaudeRun(exit_code=exit_code, timed_out=timed_out,
                     duration_sec=duration, stream_path=stream_path,
                     stderr_path=stderr_path, stream=stream, session=session)
```

- [ ] **Step 5: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_run.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add benchmark/bench_run.py benchmark/bench_metrics.py benchmark/tests/test_bench_run.py
git commit -m "feat(bench): запуск агента с таймаутом и поиск транскрипта" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Разбор транскриптов и дайджест

**Files:**
- Modify: `benchmark/bench_metrics.py`
- Create: `benchmark/tests/test_bench_metrics.py`

**Interfaces:**
- Produces: `ToolEvent`, `parse_tool_events(path) -> list[ToolEvent]`, `classify_bash(command: str) -> str`, `summarize_events(events, project_dir: Path) -> dict`, `summarize_transcripts(project_dir, session: SessionFiles, fallback_stream: Path | None) -> dict`, `aggregate_environment(task_metrics: list[dict]) -> dict`.

- [ ] **Step 1: Написать падающие тесты**

`benchmark/tests/test_bench_metrics.py`:

```python
import json
from pathlib import Path

from bench_metrics import (aggregate_environment, classify_bash,
                           parse_tool_events, summarize_events,
                           summarize_transcripts)
from bench_metrics import SessionFiles


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False)
                              for row in rows) + "\n", encoding="utf-8")
    return path


def tool_use(ts: str, tool_id: str, name: str, tool_input: dict) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {
        "content": [{"type": "tool_use", "id": tool_id, "name": name,
                     "input": tool_input}]}}


def tool_result(ts: str, tool_id: str, content: str = "ok",
                is_error: bool = False) -> dict:
    return {"type": "user", "timestamp": ts, "message": {
        "content": [{"type": "tool_result", "tool_use_id": tool_id,
                     "content": content, "is_error": is_error}]}}


def test_parse_tool_events_pairs_duration(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "python .claude/tools/run-tests.py cfg.json"}),
        tool_result("2026-01-01T00:01:30+00:00", "t1"),
        tool_use("2026-01-01T00:02:00+00:00", "t2", "Edit",
                 {"file_path": "/p/src/cfe/ЮнитТесты/Module.bsl"}),
        tool_result("2026-01-01T00:02:01+00:00", "t2", "boom", True),
    ])
    events = parse_tool_events(path)
    assert events[0].duration_sec == 90.0
    assert events[1].is_error is True
    assert events[1].name == "Edit"


def test_classify_bash():
    assert classify_bash("python .claude/tools/run-tests.py x") == "test-run"
    assert classify_bash("python .claude/tools/run-tests.py --test A > smoke.log") == "test-run"
    assert classify_bash("python x load-extension src/cfe/ЮнитТесты") == "extension-load"
    assert classify_bash("python .claude/tools/load-config-optimized.py") == "config-load"
    assert classify_bash("python analyze_code.py x.bsl") == "static-check"
    assert classify_bash("git status") == "git"
    assert classify_bash("echo hi") == "other"


def test_summarize_events(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "python .claude/tools/run-tests.py a"}),
        tool_result("2026-01-01T00:01:00+00:00", "t1"),
        tool_use("2026-01-01T00:02:00+00:00", "t2", "Bash",
                 {"command": "python .claude/tools/run-tests.py b"}),
        tool_result("2026-01-01T00:02:30+00:00", "t2", "command not found", True),
        tool_use("2026-01-01T00:03:00+00:00", "t3", "Edit",
                 {"file_path": str(tmp_path / "src" / "cfe" / "ЮнитТесты" / "M.bsl")}),
        tool_result("2026-01-01T00:03:01+00:00", "t3"),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["test_runs"] == 2
    assert summary["tool_errors"] == 1
    assert summary["edits"]["src/cfe/ЮнитТесты/M.bsl"] == 1
    assert summary["error_signatures"][0]["signature"].startswith("command not found")
    assert summary["slow_ops"][0]["duration_sec"] == 60.0


def test_summarize_transcripts_and_subagent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    main = write_jsonl(tmp_path / "main.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Agent",
                 {"description": "ревью", "prompt": "..."}),
        tool_result("2026-01-01T00:05:00+00:00", "t1"),
    ])
    subdir = tmp_path / "sid" / "subagents"
    subdir.mkdir(parents=True)
    sub = write_jsonl(subdir / "agent-a.jsonl", [
        tool_use("2026-01-01T00:00:10+00:00", "s1", "Read",
                 {"file_path": "/p/a.bsl"}),
        tool_result("2026-01-01T00:00:11+00:00", "s1"),
    ])
    (subdir / "agent-a.meta.json").write_text(json.dumps({
        "agentType": "reviewer", "description": "Ревью"}), encoding="utf-8")
    summary = summarize_transcripts(project, SessionFiles(main, (sub,)), None)
    assert summary["source"] == "session"
    assert summary["main"]["agent_calls"] == 1
    assert summary["subagents"][0]["agent"] == "reviewer"
    assert summary["subagents"][0]["tools"] == {"Read": 1}


def test_summarize_transcripts_falls_back_to_stream(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    fallback = write_jsonl(tmp_path / "stream.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "echo hi"}),
    ])
    summary = summarize_transcripts(project, SessionFiles(None, ()), fallback)
    assert summary["source"] == "stream"
    assert summary["main"]["tools"] == {"Bash": 1}


def test_aggregate_environment():
    tasks = [{"transcript": {"main": {"tool_errors": 2, "error_signatures": [
        {"signature": "command not found", "count": 1},
        {"signature": "timeout", "count": 1}]}}}]
    env = aggregate_environment(tasks)
    assert env["tool_errors"] == 2
    assert env["command_not_found"] == 1
    assert env["timeouts"] == 1
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: FAIL с `ImportError` на новые имена.

- [ ] **Step 3: Реализовать разбор и сводку**

Добавить в `benchmark/bench_metrics.py`:

```python
from collections import Counter, defaultdict
from datetime import datetime


@dataclass
class ToolEvent:
    tool_use_id: str
    name: str
    input: dict
    started_at: datetime | None
    finished_at: datetime | None = None
    is_error: bool = False
    result_text: str = ""

    @property
    def duration_sec(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


def _parse_timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return ""


def parse_tool_events(path: Path | None) -> list[ToolEvent]:
    events: list[ToolEvent] = []
    by_id: dict[str, ToolEvent] = {}
    if path is None or not path.is_file():
        return events
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            message = event.get("message") or {}
            blocks = message.get("content") or []
            if not isinstance(blocks, list):
                continue
            if event.get("type") == "assistant":
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool = ToolEvent(
                        tool_use_id=str(block.get("id") or ""),
                        name=str(block.get("name") or ""),
                        input=block.get("input") if isinstance(block.get("input"), dict) else {},
                        started_at=_parse_timestamp(event.get("timestamp")),
                    )
                    events.append(tool)
                    by_id[tool.tool_use_id] = tool
            elif event.get("type") == "user":
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool = by_id.get(str(block.get("tool_use_id") or ""))
                    if tool is None:
                        continue
                    tool.finished_at = _parse_timestamp(event.get("timestamp"))
                    tool.is_error = bool(block.get("is_error"))
                    tool.result_text = _content_text(block.get("content"))
    return events


def classify_bash(command: str) -> str:
    low = (command or "").lower()
    if "run-tests-smoke" in low:
        return "smoke"
    if "run-tests.py" in low:
        return "test-run"
    if "load-extension" in low:
        return "extension-load"
    if "load-config-optimized.py" in low or ("1c-batch" in low and " load" in low):
        return "config-load"
    if any(marker in low for marker in
           ("analyze_code.py", "analyze_query.py", "bsl_ls", "check-modules")):
        return "static-check"
    if "git " in low:
        return "git"
    return "other"


def _relative(path: str, project_dir: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(project_dir.resolve()))
    except (ValueError, OSError):
        return str(path)


def _short_input(event: ToolEvent) -> str:
    for key in ("command", "file_path", "path", "description", "prompt", "skill"):
        value = event.input.get(key)
        if isinstance(value, str):
            return value[:200]
    return ""


def summarize_events(events: list[ToolEvent], project_dir: Path) -> dict:
    tools = Counter(event.name for event in events)
    errors = [event for event in events if event.is_error]
    signatures: Counter = Counter()
    for event in errors:
        line = next((part.strip() for part in event.result_text.splitlines()
                     if part.strip()), "ошибка без описания")
        signatures[f"{event.name}: {line[:160]}"] += 1
    edits: Counter = Counter()
    for event in events:
        if event.name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            path = event.input.get("file_path") or event.input.get("path")
            if isinstance(path, str):
                edits[_relative(path, project_dir)] += 1
    bash_classes = Counter()
    for event in events:
        if event.name == "Bash":
            bash_classes[classify_bash(str(event.input.get("command") or ""))] += 1
    slow = sorted(
        (event for event in events if event.duration_sec is not None),
        key=lambda event: event.duration_sec, reverse=True)[:10]
    timed = sorted((event for event in events if event.started_at is not None),
                   key=lambda event: event.started_at)
    gaps = []
    for previous, current in zip(timed, timed[1:]):
        gap = (current.started_at - previous.started_at).total_seconds()
        if gap > 300:
            gaps.append({
                "after": previous.name, "before": current.name,
                "gap_sec": round(gap, 1),
                "at": current.started_at.isoformat(),
            })
    mcp = Counter()
    for event in events:
        if event.name.startswith("mcp__"):
            parts = event.name.split("__")
            mcp[parts[1] if len(parts) > 1 else event.name] += 1
    return {
        "tools": dict(tools),
        "tool_errors": len(errors),
        "error_signatures": [
            {"signature": signature, "count": count}
            for signature, count in signatures.most_common(10)],
        "edits": dict(edits),
        "bash": dict(bash_classes),
        "test_runs": bash_classes.get("test-run", 0),
        "smoke_runs": bash_classes.get("smoke", 0),
        "extension_loads": bash_classes.get("extension-load", 0),
        "config_loads": bash_classes.get("config-load", 0),
        "static_checks": bash_classes.get("static-check", 0),
        "slow_ops": [{
            "tool": event.name,
            "input": _short_input(event),
            "duration_sec": round(event.duration_sec, 1),
        } for event in slow],
        "gaps": gaps[:10],
        "mcp_calls": dict(mcp),
        "agent_calls": tools.get("Agent", 0),
    }


def summarize_transcripts(project_dir: Path, session: SessionFiles,
                          fallback_stream: Path | None) -> dict:
    source = "session"
    main_path = session.main
    if main_path is None:
        source = "stream"
        main_path = fallback_stream
    main = summarize_events(parse_tool_events(main_path), project_dir)
    subagents = []
    for path in session.subagents:
        meta_path = path.with_suffix(".meta.json")
        meta = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        events = parse_tool_events(path)
        duration = None
        stamps = [event.started_at for event in events
                  if event.started_at is not None]
        if len(stamps) >= 2:
            duration = round((max(stamps) - min(stamps)).total_seconds(), 1)
        summary = summarize_events(events, project_dir)
        subagents.append({
            "agent": meta.get("agentType") or path.stem,
            "description": meta.get("description") or "",
            "duration_sec": duration,
            "tools": summary["tools"],
            "tool_errors": summary["tool_errors"],
            "test_runs": summary["test_runs"],
        })
    return {"source": source, "main": main, "subagents": subagents}


def aggregate_environment(task_metrics: list[dict]) -> dict:
    signatures: Counter = Counter()
    tool_errors = 0
    for task in task_metrics:
        main = (task.get("transcript") or {}).get("main") or {}
        tool_errors += int(main.get("tool_errors") or 0)
        for item in main.get("error_signatures") or []:
            signatures[str(item.get("signature"))] += int(item.get("count") or 0)
    lowered = "\n".join(signatures.elements()).lower()
    return {
        "tool_errors": tool_errors,
        "error_signatures": [
            {"signature": signature, "count": count}
            for signature, count in signatures.most_common(10)],
        "command_not_found": lowered.count("command not found"),
        "timeouts": lowered.count("timeout") + lowered.count("таймаут"),
        "mcp_errors": sum(count for signature, count in signatures.items()
                          if "mcp__" in signature),
    }
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_metrics.py benchmark/tests/test_bench_metrics.py
git commit -m "feat(bench): дайджест транскриптов и сабагентов" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Состояние задачи, циклы и статические анализаторы

**Files:**
- Modify: `benchmark/bench_metrics.py`
- Modify: `benchmark/tests/test_bench_metrics.py`

**Interfaces:**
- Produces: `collect_task_state(project_dir, task) -> dict`, `stage_table(task_json: dict) -> list[dict]`, `test_cycle_metrics(task_json: dict, state: dict, transcript: dict) -> dict`, `run_static_analyzers(project_dir, files, reference, out_dir) -> dict`, `write_json_atomic(path, data) -> None`.

- [ ] **Step 1: Дописать падающие тесты**

Добавить в `benchmark/tests/test_bench_metrics.py`:

```python
import subprocess

from bench_metrics import (collect_task_state, run_static_analyzers,
                           stage_table, test_cycle_metrics, write_json_atomic)
from bench_run import TaskInfo


def task_info(project: Path, folder: str) -> TaskInfo:
    path = project / "tasks" / folder
    data = json.loads((path / "task.json").read_text(encoding="utf-8"))
    return TaskInfo(folder, path, data["identifier"], data["max_minutes"],
                    data.get("status", ""), data)


def test_collect_task_state(tmp_path):
    project = tmp_path / "project"
    task_dir = project / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    (task_dir / "TASK.md").write_text("# TASK\n", encoding="utf-8")
    (task_dir / "DEVELOP.md").write_text("# dev\n", encoding="utf-8")
    (task_dir / "REVIEW.1.md").write_text("# old\n", encoding="utf-8")
    (task_dir / "REVIEW.md").write_text(
        "| Вердикт | ✓ ПРИНЯТО |\n", encoding="utf-8")
    logs = project / "logs" / "task#23"
    logs.mkdir(parents=True)
    (logs / "result.json").write_text(json.dumps({
        "Выполнено": True, "ОписаниеОшибки": None,
        "РезультатТестов": [{"Имя": "A", "Результат": True}]}),
        encoding="utf-8")
    task = task_info(project, "task##001")
    state = collect_task_state(project, task)
    assert "DEVELOP.md" in state["files"]
    assert state["verdicts"]["REVIEW.md"] == "✓ ПРИНЯТО"
    assert "REVIEW.1.md" in state["archives"]
    assert state["test_results"][0]["Выполнено"] is True


def test_stage_table_and_cycle_metrics():
    task_json = {"stages": [
        {"name": "tests", "enabled": True, "status": "done", "iteration": 3,
         "started_at": "2026-01-01T00:00:00+00:00",
         "finished_at": "2026-01-01T00:01:00+00:00", "changed_files": []},
        {"name": "review", "enabled": True, "status": "done", "iteration": 2,
         "started_at": "2026-01-01T00:01:00+00:00",
         "finished_at": None, "changed_files": []},
    ]}
    stages = stage_table(task_json)
    assert stages[0]["duration_sec"] == 60.0
    assert stages[1]["duration_sec"] is None
    cycles = test_cycle_metrics(
        task_json,
        {"archives": ["REVIEW.1.md"], "verdicts": {"REVIEW.md": "✓ ПРИНЯТО"}},
        {"main": {"test_runs": 4, "smoke_runs": 1,
                  "edits": {"src/cfe/ЮнитТесты/M.bsl": 5}}})
    assert cycles == {"tests_iteration": 3, "review_iteration": 2,
                      "review_archives": 1, "test_runs": 4,
                      "smoke_runs": 1, "test_module_edits": 5,
                      "review_verdict": "✓ ПРИНЯТО"}


def test_run_static_analyzers(tmp_path):
    project = tmp_path / "project"
    scripts = project / ".claude" / "skills"
    (scripts / "code-analyze" / "scripts").mkdir(parents=True)
    (scripts / "query-analyze" / "scripts").mkdir(parents=True)
    (scripts / "code-analyze" / "scripts" / "analyze_code.py").write_text(
        "print('warning | rule-1 | 1 | msg')\nprint('info | rule-2 | 2 | msg')\n",
        encoding="utf-8")
    (scripts / "query-analyze" / "scripts" / "extract_queries.py").write_text(
        "print('ВЫБРАТЬ 1')", encoding="utf-8")
    (scripts / "query-analyze" / "scripts" / "analyze_query.py").write_text(
        "import sys\nprint('error | q-1 | 1 | bad')\n", encoding="utf-8")
    target = project / "Module.bsl"
    target.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    reference = project / "example.bsl"
    reference.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    result = run_static_analyzers(project, ["Module.bsl"], reference,
                                  tmp_path / "out")
    code = result["code_analyze"]["results"][str(target.resolve())]
    assert code["findings"] == {"warning": 1, "info": 1, "error": 0}
    assert str(reference.resolve()) in result["code_analyze"]["results"]
    query = result["query_analyze"]["results"][str(target.resolve())]
    assert query["findings"]["error"] == 1


def test_run_static_analyzers_missing_script(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    result = run_static_analyzers(project, [], None, tmp_path / "out")
    assert "не найден" in result["code_analyze"]["skipped"]


def test_write_json_atomic(tmp_path):
    path = tmp_path / "x.json"
    write_json_atomic(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: FAIL с `ImportError` на новые имена.

- [ ] **Step 3: Реализовать состояние, циклы и анализаторы**

Добавить в `benchmark/bench_metrics.py`:

```python
import hashlib
import os
import re
import subprocess
import sys


_VERDICT_RE = re.compile(r"\|\s*Вердикт\s*\|\s*([^|]+?)\s*\|")


def _parse_iso(value) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_timestamp(value)


def collect_task_state(project_dir: Path, task) -> dict:
    task_dir = project_dir / "tasks" / task.folder
    files = []
    if task_dir.is_dir():
        files = sorted(path.name for path in task_dir.iterdir()
                       if path.is_file() and path.name not in
                       ("task.json", "TASK.md") and not path.name.endswith(".lock"))
    verdicts = {}
    for name in ("TESTING.md", "REVIEW.md"):
        path = task_dir / name
        if path.is_file():
            match = _VERDICT_RE.search(path.read_text(encoding="utf-8"))
            if match:
                verdicts[name] = match.group(1).strip()
    archives = [name for name in files if re.fullmatch(r"(REVIEW|TESTING|TESTS|DEVELOP)\.\d+\.md", name)]
    test_results = []
    logs = project_dir / "logs"
    if logs.is_dir():
        for result_path in sorted(logs.glob("task#*/result.json")):
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                test_results.append(data)
    return {"files": files, "verdicts": verdicts, "archives": archives,
            "test_results": test_results}


def stage_table(task_json: dict) -> list[dict]:
    stages = []
    for stage in task_json.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        started = _parse_iso(stage.get("started_at"))
        finished = _parse_iso(stage.get("finished_at"))
        duration = (finished - started).total_seconds() if started and finished else None
        stages.append({
            "name": stage.get("name"),
            "enabled": bool(stage.get("enabled")),
            "status": stage.get("status"),
            "iteration": int(stage.get("iteration") or 1),
            "duration_sec": duration,
            "changed_files": list(stage.get("changed_files") or []),
        })
    return stages


def _stage(task_json: dict, name: str) -> dict:
    for stage in task_json.get("stages") or []:
        if isinstance(stage, dict) and stage.get("name") == name:
            return stage
    return {}


def test_cycle_metrics(task_json: dict, state: dict, transcript: dict) -> dict:
    main = (transcript.get("main") or {})
    edits = main.get("edits") or {}
    test_edits = sum(count for path, count in edits.items()
                     if "ЮнитТесты" in path and "/src/cfe/" in f"/{path}")
    return {
        "tests_iteration": int(_stage(task_json, "tests").get("iteration") or 1),
        "review_iteration": int(_stage(task_json, "review").get("iteration") or 1),
        "review_archives": len(state.get("archives") or []),
        "test_runs": int(main.get("test_runs") or 0),
        "smoke_runs": int(main.get("smoke_runs") or 0),
        "test_module_edits": test_edits,
        "review_verdict": (state.get("verdicts") or {}).get("REVIEW.md"),
    }


def _python(project_dir: Path) -> str:
    candidate = project_dir / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else sys.executable


def _safe_name(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"{digest}_{path.name}"


def _run_script(argv: list[str], cwd: Path, stdin_text: str | None = None) -> dict:
    try:
        proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                              encoding="utf-8", errors="replace",
                              input=stdin_text, timeout=180)
        return {"returncode": proc.returncode, "stdout": proc.stdout,
                "stderr": proc.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}


def _findings(output: str) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("|", 2)]
        if len(parts) >= 2 and parts[0] in counts:
            counts[parts[0]] += 1
    return counts


def run_static_analyzers(project_dir: Path, files: list[str],
                         reference: Path | None, out_dir: Path) -> dict:
    analyzers_dir = out_dir / "analyzers"
    analyzers_dir.mkdir(parents=True, exist_ok=True)
    targets = []
    for raw in files:
        path = (project_dir / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        if path.is_file() and path.suffix.lower() == ".bsl":
            targets.append(path)
    if reference is not None and reference.is_file():
        targets.append(reference.resolve())
    targets = sorted(set(targets))
    python = _python(project_dir)
    code_script = project_dir / ".claude" / "skills" / "code-analyze" / "scripts" / "analyze_code.py"
    extract_script = project_dir / ".claude" / "skills" / "query-analyze" / "scripts" / "extract_queries.py"
    query_script = project_dir / ".claude" / "skills" / "query-analyze" / "scripts" / "analyze_query.py"
    code_result = {"available": code_script.is_file(),
                   "skipped": None if code_script.is_file() else "analyze_code.py не найден",
                   "results": {}}
    query_result = {"available": extract_script.is_file() and query_script.is_file(),
                    "skipped": None if extract_script.is_file() and query_script.is_file()
                    else "analyze_query.py/extract_queries.py не найден",
                    "results": {}}
    for target in targets:
        key = str(target)
        if code_script.is_file():
            run = _run_script([python, str(code_script), str(target), "-NoFail"],
                              project_dir)
            output = run["stdout"] + run["stderr"]
            output_path = analyzers_dir / f"{_safe_name(target)}.code.txt"
            output_path.write_text(output, encoding="utf-8")
            code_result["results"][key] = {
                "returncode": run["returncode"],
                "findings": _findings(run["stdout"]),
                "output_path": str(output_path),
                "warnings": run["stderr"].strip()[:1000],
            }
        if extract_script.is_file() and query_script.is_file():
            extracted = _run_script([python, str(extract_script), "-Path", str(target)],
                                    project_dir)
            analyzed = _run_script([python, str(query_script), "-"], project_dir,
                                   stdin_text=extracted["stdout"])
            output = extracted["stdout"] + extracted["stderr"] + analyzed["stdout"] + analyzed["stderr"]
            output_path = analyzers_dir / f"{_safe_name(target)}.query.txt"
            output_path.write_text(output, encoding="utf-8")
            query_result["results"][key] = {
                "returncode": analyzed["returncode"],
                "findings": _findings(analyzed["stdout"]),
                "output_path": str(output_path),
                "extract_returncode": extracted["returncode"],
                "warnings": (extracted["stderr"] + analyzed["stderr"]).strip()[:1000],
            }
    return {"code_analyze": code_result, "query_analyze": query_result}


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_metrics.py benchmark/tests/test_bench_metrics.py
git commit -m "feat(bench): метрики этапов и статические анализаторы" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Рендер дайджеста

**Files:**
- Modify: `benchmark/bench_metrics.py`
- Modify: `benchmark/tests/test_bench_metrics.py`

**Interfaces:**
- Consumes: `aggregate_environment`, метрики задач из Task 5.
- Produces: `render_digest(metrics: dict) -> str`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `benchmark/tests/test_bench_metrics.py`:

```python
from bench_metrics import render_digest


def test_render_digest_contains_key_sections():
    metrics = {
        "run": {"run_id": "20260101-000000", "project_dir": "/p",
                "claude_cmd": "claude-ds", "force": False},
        "tasks": [{
            "folder": "task##001", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 120.0, "exit_code": 0,
            "stream": {"num_turns": 12, "cost_usd": 0.5},
            "stages": [{"name": "develop", "enabled": True, "status": "done",
                        "iteration": 2, "duration_sec": 60.0}],
            "cycles": {"tests_iteration": 2, "review_iteration": 1,
                       "test_runs": 3, "smoke_runs": 1,
                       "test_module_edits": 4, "review_archives": 0},
            "transcript": {"source": "session", "main": {
                "tool_errors": 1,
                "error_signatures": [{"signature": "Bash: command not found",
                                      "count": 1}],
                "slow_ops": [{"tool": "Bash", "input": "run-tests.py",
                              "duration_sec": 90.0}],
                "gaps": [{"after": "Bash", "before": "Read", "gap_sec": 400,
                          "at": "2026-01-01T00:00:00+00:00"}],
                "tools": {"Bash": 5}}},
        }],
        "environment": {"tool_errors": 1,
                        "error_signatures": [{"signature": "Bash: command not found",
                                              "count": 1}],
                        "command_not_found": 1, "timeouts": 0,
                        "mcp_errors": 0},
    }
    text = render_digest(metrics)
    assert "# Дайджест benchmark-прогона" in text
    assert "task##001" in text
    assert "command not found" in text
    assert "run-tests.py" in text
    assert "400" in text
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: FAIL с `ImportError` на `render_digest`.

- [ ] **Step 3: Реализовать рендер**

Добавить в `benchmark/bench_metrics.py`:

```python
def _seconds(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    if value >= 60:
        return f"{value / 60:.1f} мин"
    return f"{value:.0f} с"


def render_digest(metrics: dict) -> str:
    run = metrics.get("run") or {}
    lines = [
        "# Дайджест benchmark-прогона",
        "",
        f"- Прогон: `{run.get('run_id', '—')}`",
        f"- Проект: `{run.get('project_dir', '—')}`",
        f"- Команда агента: `{run.get('claude_cmd', '—')}`",
        f"- Режим --force: {'да' if run.get('force') else 'нет'}",
        "",
        "## Задачи",
        "",
        "| Задача | Лимит | Исход | Факт | Этапы (итерации) | Тесты | Ревью |",
        "|---|---|---|---|---|---|---|",
    ]
    for task in metrics.get("tasks") or []:
        stages = ", ".join(
            f"{stage.get('name')}×{stage.get('iteration')}"
            for stage in task.get("stages") or [] if stage.get("enabled"))
        cycles = task.get("cycles") or {}
        lines.append(
            f"| {task.get('folder')} | {task.get('limit_minutes')} мин | "
            f"{task.get('outcome')} | {_seconds(task.get('duration_sec'))} | "
            f"{stages or '—'} | "
            f"запусков {cycles.get('test_runs', 0)}, "
            f"смоуков {cycles.get('smoke_runs', 0)}, "
            f"правок тестов {cycles.get('test_module_edits', 0)} | "
            f"итераций {cycles.get('review_iteration', 0)}, "
            f"архивов {cycles.get('review_archives', 0)} |")
    for task in metrics.get("tasks") or []:
        lines += ["", f"## {task.get('folder')}", ""]
        lines.append(f"- Исход: `{task.get('outcome')}`, код выхода: "
                     f"`{task.get('exit_code')}`, время: "
                     f"{_seconds(task.get('duration_sec'))}")
        stream = task.get("stream") or {}
        lines.append(f"- Агент: turns={stream.get('num_turns')}, "
                     f"cost=${stream.get('cost_usd')}, "
                     f"session={stream.get('session_id')}")
        transcript = task.get("transcript") or {}
        main = transcript.get("main") or {}
        lines.append(f"- Источник транскрипта: {transcript.get('source', '—')}, "
                     f"ошибок инструментов: {main.get('tool_errors', 0)}")
        if main.get("tools"):
            lines.append("- Инструменты: " + ", ".join(
                f"{name}={count}" for name, count in
                sorted(main["tools"].items())))
        if main.get("slow_ops"):
            lines += ["", "### Долгие операции", "",
                      "| Инструмент | Вход | Длительность |", "|---|---|---|"]
            for op in main["slow_ops"]:
                lines.append(f"| {op.get('tool')} | `{op.get('input')}` | "
                             f"{_seconds(op.get('duration_sec'))} |")
        if main.get("gaps"):
            lines += ["", "### Простои > 5 мин", ""]
            for gap in main["gaps"]:
                lines.append(f"- {_seconds(gap.get('gap_sec'))} "
                             f"({gap.get('gap_sec')} с) после "
                             f"{gap.get('after')} перед {gap.get('before')} "
                             f"({gap.get('at')})")
        if main.get("error_signatures"):
            lines += ["", "### Ошибки", ""]
            for item in main["error_signatures"]:
                lines.append(f"- ×{item.get('count')}: {item.get('signature')}")
        subagents = transcript.get("subagents") or []
        if subagents:
            lines += ["", "### Сабагенты", ""]
            for agent in subagents:
                lines.append(f"- {agent.get('agent')}: "
                             f"{agent.get('description')} — "
                             f"{_seconds(agent.get('duration_sec'))}, "
                             f"ошибок {agent.get('tool_errors', 0)}, "
                             f"тестов {agent.get('test_runs', 0)}")
        analyzers = task.get("analyzers") or {}
        code = analyzers.get("code_analyze") or {}
        lines += ["", "### Анализаторы", ""]
        if code.get("skipped"):
            lines.append(f"- code-analyze: пропущен ({code['skipped']})")
        else:
            lines.append(f"- code-analyze: файлов {len(code.get('results') or {})}")
        for path, result in (code.get("results") or {}).items():
            findings = result.get("findings") or {}
            lines.append(f"  - `{Path(path).name}`: error={findings.get('error', 0)}, "
                         f"warning={findings.get('warning', 0)}, "
                         f"info={findings.get('info', 0)}")
        query = analyzers.get("query_analyze") or {}
        if query.get("skipped"):
            lines.append(f"- query-analyze: пропущен ({query['skipped']})")
        else:
            lines.append(f"- query-analyze: файлов {len(query.get('results') or {})}")
    env = metrics.get("environment") or {}
    lines += ["", "## Окружение", "",
              f"- Ошибок инструментов: {env.get('tool_errors', 0)}",
              f"- «command not found»: {env.get('command_not_found', 0)}",
              f"- Таймаутов: {env.get('timeouts', 0)}",
              f"- Ошибок MCP: {env.get('mcp_errors', 0)}"]
    for item in env.get("error_signatures") or []:
        lines.append(f"- ×{item.get('count')}: {item.get('signature')}")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_metrics.py benchmark/tests/test_bench_metrics.py
git commit -m "feat(bench): рендер дайджеста метрик" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Промпт аналитика и `RESULT.md`

**Files:**
- Create: `benchmark/bench_analysis.py`
- Create: `benchmark/tests/test_bench_analysis.py`

**Interfaces:**
- Consumes: `StreamSummary` из `bench_metrics`.
- Produces: `build_prompt(*, run_id, project_dir, repo_root, run_dir, metrics_path, digest_path, manifest_path, reference_path, contaminated, task_folders) -> str`, `extract_analyst_text(stream) -> str | None`, `deterministic_report(*, run_id, project_dir, run_dir, metrics, error=None, skipped=False) -> str`, `write_report(project_dir, text) -> Path`.

- [ ] **Step 1: Написать падающие тесты**

`benchmark/tests/test_bench_analysis.py`:

```python
from pathlib import Path

from bench_analysis import (build_prompt, deterministic_report,
                            extract_analyst_text, write_report)
from bench_metrics import StreamSummary


def test_build_prompt_has_constraints_and_no_orchestration_trigger(tmp_path):
    prompt = build_prompt(
        run_id="20260101-000000",
        project_dir=tmp_path / "project",
        repo_root=tmp_path / "repo",
        run_dir=tmp_path / "run",
        metrics_path=tmp_path / "run" / "metrics.json",
        digest_path=tmp_path / "run" / "digest.md",
        manifest_path=tmp_path / "run" / "analysis-inputs.md",
        reference_path=tmp_path / "repo" / "benchmark" / "example.bsl",
        contaminated=False,
        task_folders=["task##001", "task##002"],
    )
    assert "не затачивай" in prompt.lower()
    assert "example.bsl" in prompt
    assert "RESULT.md" not in prompt  # отчёт пишет скрипт, не аналитик
    assert "tasks/task#" not in prompt  # не триггерит route_to_orchestrator
    assert "Запрещено: Edit/Write/MultiEdit/NotebookEdit" in prompt
    assert "metrics.json" in prompt
    assert "analysis-inputs.md" in prompt
    for header in ("Время выполнения", "Итерации написания", "Итерации код-ревью",
                   "Качество кода", "Окружение template", "Рекомендации",
                   "Что уже работает хорошо"):
        assert header in prompt


def test_extract_analyst_text():
    stream = StreamSummary(result={"is_error": False, "result": "# Отчёт\n"})
    assert extract_analyst_text(stream) == "# Отчёт\n"
    assert extract_analyst_text(StreamSummary(result=None)) is None
    assert extract_analyst_text(
        StreamSummary(result={"is_error": True, "result": "boom"})) is None


def test_deterministic_report(tmp_path):
    metrics = {"run": {"run_id": "r1", "project_dir": "/p"},
               "tasks": [{"folder": "task##001", "outcome": "timeout",
                          "duration_sec": 1800, "limit_minutes": 30}],
               "analysis": {}}
    text = deterministic_report(run_id="r1", project_dir=tmp_path,
                                run_dir=tmp_path / "run", metrics=metrics,
                                error="аналитик упал")
    assert "аналитик упал" in text
    assert "task##001" in text
    skipped = deterministic_report(run_id="r1", project_dir=tmp_path,
                                   run_dir=tmp_path / "run", metrics=metrics,
                                   skipped=True)
    assert "пропущен" in skipped.lower()


def test_write_report_atomic(tmp_path):
    project = tmp_path / "project"
    path = write_report(project, "# hi\n")
    assert path == project / "tmp" / "RESULT.md"
    assert path.read_text(encoding="utf-8") == "# hi\n"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_analysis.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'bench_analysis'`.

- [ ] **Step 3: Реализовать модуль аналитика**

`benchmark/bench_analysis.py`:

```python
"""Промпт сессии-аналитика, извлечение ответа и детерминированный отчёт."""
from __future__ import annotations

import os
from pathlib import Path

from bench_metrics import StreamSummary


def build_prompt(*, run_id: str, project_dir: Path, repo_root: Path,
                 run_dir: Path, metrics_path: Path, digest_path: Path,
                 manifest_path: Path, reference_path: Path | None,
                 contaminated: bool, task_folders: list[str]) -> str:
    reference = str(reference_path) if reference_path else "недоступен"
    tasks = ", ".join(task_folders)
    return f"""Ты — старший аналитик benchmark-прогона Claude-агента на 1С.

Твоя задача — по собранным фактам объяснить, почему прогон занял столько времени,
сколько было лишних итераций тестов и ревью, и предложить улучшения template.
Ты НЕ выполняешь задачи, НЕ запускаешь тесты и загрузку ИБ, НЕ меняешь файлы проекта.

## Входы (читай только их)
- Метрики: {metrics_path}
- Дайджест: {digest_path}
- Манифест входов (каталоги задач и артефакты): {manifest_path}
- Диффы прогона: {run_dir / "diffs"}
- Транскрипты: {run_dir / "transcripts"}
- Проект: {project_dir}
- Корень репозитория (template и benchmark): {repo_root}
- Эталонная реализация: {reference}
- Задачи прогона: {tasks}
- Прогон: {run_id}
- Проект мог быть не свежим (--force): {'да' if contaminated else 'нет'}

Разрешено: Read, Grep, Glob, Bash только для чтения логов и запуска
`.claude/skills/*/scripts/*.py` (code-analyze/query-analyze), MCP `bsl_ls`.
Запрещено: Edit/Write/MultiEdit/NotebookEdit, запуск тестов, загрузка конфигурации,
изменение git-состояния, выполнение задач.

## Обязательные ограничения
- Рекомендации должны быть ОБЩИМИ для любых будущих задач. Не затачивай template
  под задачи #001/#002 и не предлагай код, специфичный только для них.
- Не хардкодь фрагменты кода из example.bsl в template.
- Не увеличивай число символов в описаниях задач benchmark/tasks. Если предлагаешь
  переформулировку — покажи длину «до/после» и оставь «после» не больше «до».
- Не выдавай пропущенные проверки за пройденные: если анализатор/слой недоступен,
  так и напиши.
- Отделяй факты (метрики, логи, файл:строка) от гипотез.
- Сравнивай итоговый модуль с эталоном семантически, а не по текстовому совпадению:
  что упущено, что реализовано иначе, что сделано лучше/хуже.

## Формат ответа
Верни ТОЛЬКО markdown-отчёт (без преамбул и комментариев о процессе), на русском,
со структурой:
1. `## Сводка прогона` — таблица «задача → лимит → факт → исход → этапы → итерации →
   тесты → вердикт ревью», стоимость/токены, пометка о --force.
2. `## Время выполнения` — где ушло время, долгие операции, простои.
3. `## Итерации написания и запуска тестов` — циклы, причины возвратов, лишние прогоны.
4. `## Итерации код-ревью` — раунды, находки, возвраты.
5. `## Качество кода` — сравнение с эталоном, находки анализаторов по коду и эталону.
6. `## Окружение template` — сбои MCP/хуков/платформы, повторяющиеся ошибки,
   отсутствующие инструменты, медленные места.
7. `## Рекомендации` — таблицы «быстрые победы (P1)» и «крупные изменения (P2)»:
   проблема + доказательство, конкретное изменение (файлы), ожидаемый эффект,
   риск/трудоёмкость. Отдельно — предложения по описаниям задач, `ЮнитТесты`, инструментам.
8. `## Что уже работает хорошо`.
9. `## Приложение` — пути к метрикам, дайджесту, диффам, транскриптам.

Отчёт должен быть конкретным: каждая рекомендация опирается на метрику, лог или
файл:строку. Если данных для вывода нет — напиши «недостаточно данных», не выдумывай.
"""


def extract_analyst_text(stream: StreamSummary) -> str | None:
    result = stream.result or {}
    text = result.get("result")
    if result.get("is_error") or not isinstance(text, str):
        return None
    text = text.strip()
    return text or None


def deterministic_report(*, run_id: str, project_dir: Path, run_dir: Path,
                         metrics: dict, error: str | None = None,
                         skipped: bool = False) -> str:
    lines = [f"# Результат benchmark-прогона {run_id}", ""]
    if error:
        lines += ["## ⚠ Аналитическая сессия не дала отчёт", "",
                  f"Ошибка: {error}", "",
                  "Ниже — только объективные метрики прогона.", ""]
    elif skipped:
        lines += ["## Качественный анализ пропущен (--skip-analysis)", ""]
    run = metrics.get("run") or {}
    lines += ["## Сводка прогона", "",
              f"- Проект: `{project_dir}`",
              f"- Каталог прогона: `{run_dir}`",
              f"- Команда агента: `{run.get('claude_cmd', '—')}`",
              f"- --force: {'да' if run.get('force') else 'нет'}", "",
              "| Задача | Лимит | Исход | Факт |", "|---|---|---|---|"]
    for task in metrics.get("tasks") or []:
        seconds = task.get("duration_sec")
        fact = f"{seconds / 60:.1f} мин" if isinstance(seconds, (int, float)) else "—"
        lines.append(f"| {task.get('folder')} | {task.get('limit_minutes')} мин | "
                     f"{task.get('outcome')} | {fact} |")
    lines += ["", "## Артефакты", "",
              f"- Метрики: `{run_dir / 'metrics.json'}`",
              f"- Дайджест: `{run_dir / 'digest.md'}`",
              f"- Диффы: `{run_dir / 'diffs'}`",
              f"- Транскрипты: `{run_dir / 'transcripts'}`", ""]
    return "\n".join(lines)


def write_report(project_dir: Path, text: str) -> Path:
    target = project_dir / "tmp" / "RESULT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text if text.endswith("\n") else text + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return target
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_analysis.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add benchmark/bench_analysis.py benchmark/tests/test_bench_analysis.py
git commit -m "feat(bench): промпт аналитика и отчёт RESULT.md" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Оркестрация, CLI и end-to-end

**Files:**
- Modify: `benchmark/bench_run.py`
- Create: `benchmark/run_benchmark.py`
- Create: `benchmark/tests/test_bench_e2e.py`

**Interfaces:**
- Consumes: всё из Tasks 1–7.
- Produces: `build_task_prompt(folder: str) -> str`, `execute(options: RunOptions) -> int`, `main(argv=None) -> int`.

- [ ] **Step 1: Написать падающие e2e-тесты**

`benchmark/tests/test_bench_e2e.py`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench_run import build_task_prompt


REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "benchmark" / "run_benchmark.py"


def git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True,
                   capture_output=True, text=True)


def make_project(root: Path) -> Path:
    project = root / "project"
    (project / ".gitignore").write_text("/tmp\n", encoding="utf-8")
    for folder, ident in (("task##001", "#001"), ("task##002", "#002")):
        task_dir = project / "tasks" / folder
        task_dir.mkdir(parents=True)
        (task_dir / "TASK.md").write_text(f"# Задача {ident}\n", encoding="utf-8")
        (task_dir / "task.json").write_text(json.dumps({
            "identifier": ident, "status": "planned", "max_minutes": 30,
            "stages": [{"name": "develop", "enabled": True, "status": "pending",
                        "iteration": 1}],
        }), encoding="utf-8")
    git(project, "init", "-q")
    git(project, "config", "user.email", "bench@example.ru")
    git(project, "config", "user.name", "Bench")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    git(project, "commit", "-q", "--allow-empty", "-m", "baseline before task#001")
    return project


FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path

args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
sid = "fake-session"
out = []

if prompt.startswith("Выполни задачу tasks/"):
    folder = re.search(r"Выполни задачу tasks/(\S+)", prompt).group(1).split("/")[-1]
    marker = Path(os.environ["FAKE_MARKER"])
    marker.write_text(marker.read_text() + "x" if marker.exists() else "x")
    if os.environ.get("FAKE_FAIL") == folder:
        out.append({"type": "result", "subtype": "error", "session_id": sid,
                    "is_error": True, "result": "boom", "duration_ms": 1})
        print("\n".join(json.dumps(x, ensure_ascii=False) for x in out))
        sys.exit(1)
    task_dir = Path.cwd() / "tasks" / folder
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    for stage in data.get("stages", []):
        if stage.get("enabled"):
            stage["status"] = "done"
            stage["iteration"] = 2
            stage["started_at"] = "2026-01-01T00:00:00+00:00"
            stage["finished_at"] = "2026-01-01T00:01:00+00:00"
    data["status"] = "done"
    (task_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "DEVELOP.md").write_text("# DEVELOP\n", encoding="utf-8")
    proj = Path.home() / ".claude" / "projects" / "fake"
    proj.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": [{"type": "tool_use", "id": "t1",
                                  "name": "Bash",
                                  "input": {"command": "python .claude/tools/run-tests.py c"}}]}},
        {"type": "user", "timestamp": "2026-01-01T00:00:30Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                  "content": "ok"}]}},
    ]
    (proj / f"{sid}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out.append({"type": "result", "subtype": "success", "session_id": sid,
                "is_error": False, "result": "done", "duration_ms": 1,
                "num_turns": 3, "total_cost_usd": 0.1})
else:
    out.append({"type": "result", "subtype": "success", "session_id": sid + "-a",
                "is_error": False, "duration_ms": 1,
                "result": "# Результат benchmark-прогона\n\n## Сводка прогона\n\nok"})
print("\n".join(json.dumps(x, ensure_ascii=False) for x in out))
'''


@pytest.fixture
def env(tmp_path):
    project = make_project(tmp_path)
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "marker"
    values = dict(os.environ)
    values.update({"HOME": str(home), "FAKE_MARKER": str(marker),
                   "PYTHONIOENCODING": "utf-8"})
    return project, fake, marker, values


def run_cli(project, fake, values, *extra):
    return subprocess.run(
        [sys.executable, str(CLI), "--project", str(project),
         "--claude-cmd", str(fake), *extra],
        cwd=REPO, env=values, capture_output=True, text=True, timeout=120)


def test_task_prompt_triggers_orchestrator():
    prompt = build_task_prompt("task##001")
    assert "tasks/task##001" in prompt
    assert "tasks/task#" in prompt
    assert "task-orchestration" in prompt


def test_e2e_success_with_analysis(env):
    project, fake, marker, values = env
    proc = run_cli(project, fake, values)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = (project / "tmp" / "RESULT.md").read_text(encoding="utf-8")
    assert report.startswith("# Результат benchmark-прогона")
    assert "## Сводка прогона" in report
    assert marker.read_text() == "xx"
    runs = sorted((project / "tmp" / "benchmark").iterdir())
    metrics = json.loads((runs[-1] / "metrics.json").read_text(encoding="utf-8"))
    assert [task["outcome"] for task in metrics["tasks"]] == ["success", "success"]
    assert (runs[-1] / "digest.md").is_file()
    assert (runs[-1] / "diffs" / "task##001.diff").is_file()


def test_e2e_stops_after_failure_but_analyzes(env):
    project, fake, marker, values = env
    values = dict(values)
    values["FAKE_FAIL"] = "task##001"
    proc = run_cli(project, fake, values)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert marker.read_text() == "x"
    data = json.loads((project / "tasks" / "task##002" / "task.json")
                      .read_text(encoding="utf-8"))
    assert data["status"] == "planned"
    assert (project / "tmp" / "RESULT.md").is_file()


def test_e2e_skip_analysis(env):
    project, fake, marker, values = env
    proc = run_cli(project, fake, values, "--skip-analysis")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = (project / "tmp" / "RESULT.md").read_text(encoding="utf-8")
    assert "Качественный анализ пропущен" in report


def test_e2e_refuses_dirty_project(env):
    project, fake, marker, values = env
    (project / "tasks" / "task##001" / "DEVELOP.md").write_text("x", encoding="utf-8")
    proc = run_cli(project, fake, values)
    assert proc.returncode == 1
    assert "не готов" in proc.stderr
    assert not marker.exists()


def test_e2e_rejects_missing_claude_cmd(env):
    project, fake, marker, values = env
    proc = run_cli(project, Path("/nonexistent/claude"), values)
    assert proc.returncode == 1
    assert "команда агента" in proc.stderr
    assert not marker.exists()
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_e2e.py -q`
Expected: FAIL с `ImportError` на `build_task_prompt` и отсутствием CLI.

- [ ] **Step 3: Реализовать оркестрацию**

В начале `benchmark/bench_run.py` заменить `from dataclasses import dataclass`
на `from dataclasses import dataclass, replace` и добавить `import shutil`.
Затем добавить в конец файла:

```python
from bench_analysis import (build_prompt, deterministic_report,
                            extract_analyst_text, write_report)
from bench_metrics import (aggregate_environment, collect_task_state,
                           render_digest, run_static_analyzers, stage_table,
                           summarize_transcripts, test_cycle_metrics,
                           write_json_atomic)


def ensure_claude_cmd(cmd: str) -> None:
    """Проверить, что команда агента существует и исполняема."""
    candidate = Path(cmd)
    if candidate.is_absolute() or os.sep in cmd:
        resolved = candidate
    else:
        found = shutil.which(cmd)
        resolved = Path(found) if found else candidate
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise BenchError(f"команда агента не найдена или не исполняема: {cmd}")


def build_task_prompt(folder: str) -> str:
    return (f"Выполни задачу tasks/{folder} по этапам из её task.json. "
            f"Следуй навыку task-orchestration.")


class RunLog:
    def __init__(self, path: Path):
        self._file = path.open("a", encoding="utf-8")

    def __call__(self, message: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {message}"
        print(line, flush=True)
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _outcome(run: ClaudeRun, task_json: dict) -> str:
    if run.timed_out:
        return "timeout"
    if run.exit_code != 0:
        return "failed"
    if not task_json:
        return "incomplete"
    enabled = [stage for stage in task_json.get("stages") or []
               if isinstance(stage, dict) and stage.get("enabled")]
    return "success" if all(stage.get("status") == "done"
                            for stage in enabled) else "incomplete"


def _write_run_json(run_dir: Path, run_metrics: dict) -> None:
    write_json_atomic(run_dir / "run.json", {
        "run": run_metrics.get("run") or {},
        "tasks": [{"folder": task.get("folder"),
                   "outcome": task.get("outcome"),
                   "duration_sec": task.get("duration_sec")}
                  for task in run_metrics.get("tasks") or []],
        "analysis": run_metrics.get("analysis") or {},
    })


def _stream_metrics(run: ClaudeRun) -> dict:
    result = run.stream.result or {}
    return {
        "session_id": run.stream.session_id,
        "parse_errors": run.stream.parse_errors,
        "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
        "is_error": result.get("is_error"),
        "usage": result.get("usage"),
    }


def _inputs_manifest(path: Path, project_dir: Path, repo_root: Path,
                     run_dir: Path, metrics_path: Path, digest_path: Path,
                     reference: Path | None, tasks) -> None:
    lines = ["# Входы анализа", "",
             f"- Проект: `{project_dir}`",
             f"- Метрики: `{metrics_path}`",
             f"- Дайджест: `{digest_path}`",
             f"- Диффы: `{run_dir / 'diffs'}`",
             f"- Транскрипты: `{run_dir / 'transcripts'}`",
             f"- Эталон: `{reference}`" if reference else "- Эталон: недоступен",
             f"- Template: `{repo_root / 'template'}`", "", "## Задачи", ""]
    for task in tasks:
        lines.append(f"- `{task.folder}`: `{task.path}`")
        for name in sorted(p.name for p in task.path.iterdir() if p.is_file()):
            if name not in ("task.json", "TASK.md"):
                lines.append(f"  - `{name}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def execute(options: RunOptions) -> int:
    ensure_claude_cmd(options.claude_cmd)
    ensure_fresh(options.project_dir, list(options.tasks), force=options.force)
    run_dir = prepare_run_dir(options.project_dir)
    options = replace(options, run_dir=run_dir)
    log = RunLog(run_dir / "run.log")
    reference = options.repo_root / "benchmark" / "example.bsl"
    reference = reference if reference.is_file() else None
    metrics_path = run_dir / "metrics.json"
    digest_path = run_dir / "digest.md"
    manifest_path = run_dir / "analysis-inputs.md"
    run_metrics = {
        "schema_version": 1,
        "run": {
            "run_id": run_dir.name,
            "started_at": _iso_now(),
            "finished_at": None,
            "project_dir": str(options.project_dir),
            "repo_root": str(options.repo_root),
            "claude_cmd": options.claude_cmd,
            "force": options.force,
            "skip_analysis": options.skip_analysis,
            "env_file": str(options.env_file),
            "tasks": [{"folder": task.folder,
                       "limit_minutes": options.limits[task.folder]}
                      for task in options.tasks],
        },
        "tasks": [],
        "environment": {},
        "analysis": {"performed": False},
    }
    write_json_atomic(metrics_path, run_metrics)
    _write_run_json(run_dir, run_metrics)
    log(f"прогон {run_dir.name}: проект {options.project_dir}")
    if options.force:
        log("⚠ --force: проект не проверялся на свежесть")
    stopped = False
    for task in options.tasks:
        log(f"▶ {task.folder}: старт (лимит {options.limits[task.folder]} мин)")
        task_started = _iso_now()
        before = git_state(options.project_dir)
        stream_path = run_dir / "transcripts" / f"{task.folder}.stream.jsonl"
        stderr_path = run_dir / "transcripts" / f"{task.folder}.stderr.log"
        run = run_claude(
            cmd=options.claude_cmd,
            prompt=build_task_prompt(task.folder),
            cwd=options.project_dir,
            timeout_sec=options.limits[task.folder] * 60,
            stream_path=stream_path,
            stderr_path=stderr_path,
        )
        after = git_state(options.project_dir)
        diff_path = run_dir / "diffs" / f"{task.folder}.diff"
        stat_path = run_dir / "diffs" / f"{task.folder}.stat.txt"
        changed = collect_diff(options.project_dir, before.head, diff_path, stat_path)
        try:
            task_json = json.loads((task.path / "task.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            task_json = {}
        state = collect_task_state(options.project_dir, task)
        transcript = summarize_transcripts(options.project_dir, run.session,
                                          run.stream_path)
        analyzers = run_static_analyzers(options.project_dir, changed, reference,
                                         run_dir / task.folder)
        outcome = _outcome(run, task_json)
        task_finished = _iso_now()
        task_metrics = {
            "folder": task.folder,
            "identifier": task.identifier,
            "limit_minutes": options.limits[task.folder],
            "outcome": outcome,
            "exit_code": run.exit_code,
            "timed_out": run.timed_out,
            "duration_sec": round(run.duration_sec, 1),
            "started_at": task_started,
            "finished_at": task_finished,
            "stream": _stream_metrics(run),
            "task_json": task_json,
            "stages": stage_table(task_json),
            "cycles": test_cycle_metrics(task_json, state, transcript),
            "artifacts": state,
            "git": {
                "head_before": before.head,
                "head_after": after.head,
                "dirty_after": bool(after.status.strip()),
                "changed_files": changed,
                "diff_path": str(diff_path),
                "stat_path": str(stat_path),
            },
            "transcript": transcript,
            "analyzers": analyzers,
        }
        run_metrics["tasks"].append(task_metrics)
        write_json_atomic(metrics_path, run_metrics)
        _write_run_json(run_dir, run_metrics)
        log(f"{'✓' if outcome == 'success' else '✗'} {task.folder}: {outcome}, "
            f"{run.duration_sec:.0f} с")
        if outcome != "success":
            stopped = True
            break
    run_metrics["environment"] = aggregate_environment(run_metrics["tasks"])
    write_json_atomic(metrics_path, run_metrics)
    _write_run_json(run_dir, run_metrics)
    digest_path.write_text(render_digest(run_metrics), encoding="utf-8")
    log(f"метрики: {metrics_path}")
    if options.skip_analysis:
        report = deterministic_report(
            run_id=run_dir.name, project_dir=options.project_dir,
            run_dir=run_dir, metrics=run_metrics, skipped=True)
        target = write_report(options.project_dir, report)
        run_metrics["run"]["finished_at"] = _iso_now()
        run_metrics["analysis"] = {"performed": False, "skipped": True,
                                   "result_path": str(target)}
        write_json_atomic(metrics_path, run_metrics)
        _write_run_json(run_dir, run_metrics)
        log(f"отчёт (без анализа): {target}")
        log.close()
        return 0 if not stopped else 2
    _inputs_manifest(manifest_path, options.project_dir, options.repo_root,
                     run_dir, metrics_path, digest_path, reference, options.tasks)
    prompt = build_prompt(
        run_id=run_dir.name,
        project_dir=options.project_dir,
        repo_root=options.repo_root,
        run_dir=run_dir,
        metrics_path=metrics_path,
        digest_path=digest_path,
        manifest_path=manifest_path,
        reference_path=reference,
        contaminated=options.force,
        task_folders=[task.folder for task in options.tasks],
    )
    (run_dir / "analysis-prompt.md").write_text(prompt, encoding="utf-8")
    analyst_before = git_state(options.project_dir)
    analyst = run_claude(
        cmd=options.claude_cmd,
        prompt=prompt,
        cwd=options.project_dir,
        timeout_sec=options.analysis_timeout_min * 60,
        stream_path=run_dir / "transcripts" / "analyst.stream.jsonl",
        stderr_path=run_dir / "transcripts" / "analyst.stderr.log",
        extra_args=("--add-dir", str(options.repo_root),
                    "--disallowedTools", "Edit", "MultiEdit", "NotebookEdit",
                    "Write", "Agent"),
    )
    analyst_after = git_state(options.project_dir)
    text = extract_analyst_text(analyst.stream)
    error = None
    if analyst.timed_out:
        error = "сессия-аналитик превысила лимит времени"
    elif analyst.exit_code != 0:
        error = f"сессия-аналитик завершилась с кодом {analyst.exit_code}"
    elif text is None:
        error = "сессия-аналитик не вернула markdown-отчёт"
    if error or text is None:
        text = deterministic_report(
            run_id=run_dir.name, project_dir=options.project_dir,
            run_dir=run_dir, metrics=run_metrics, error=error)
    else:
        (run_dir / "analyst-result.md").write_text(text, encoding="utf-8")
    mutated = (analyst_before.head != analyst_after.head
               or analyst_before.status != analyst_after.status)
    if mutated:
        text += ("\n\n## ⚠ Предупреждение\n\n"
                 "Во время сессии-аналитика изменилось git-состояние проекта. "
                 f"Проверьте `{analyst_before.head[:8]}` → `{analyst_after.head[:8]}` "
                 "и `git status`; отчёт мог быть построен на изменённых данных.\n")
        log("⚠ аналитик изменил git-состояние проекта")
    target = write_report(options.project_dir, text)
    run_metrics["run"]["finished_at"] = _iso_now()
    run_metrics["analysis"] = {
        "performed": True,
        "skipped": False,
        "session_id": analyst.stream.session_id,
        "duration_sec": round(analyst.duration_sec, 1),
        "timed_out": analyst.timed_out,
        "exit_code": analyst.exit_code,
        "error": error,
        "project_mutated": mutated,
        "result_path": str(target),
    }
    write_json_atomic(metrics_path, run_metrics)
    _write_run_json(run_dir, run_metrics)
    log(f"отчёт: {target}")
    log.close()
    if error:
        return 1
    return 0 if not stopped else 2


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        options = build_options(ns, repo_root)
        return execute(options)
    except BenchError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"✗ ошибка ввода-вывода: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("✗ прервано пользователем", file=sys.stderr)
        return 130
```

`benchmark/run_benchmark.py`:

```python
#!/usr/bin/env python3
"""CLI benchmark-прогона: задачи в claude-ds, метрики и анализ template."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_run import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Прогнать e2e-тесты**

Run: `.venv/bin/python -m pytest benchmark/tests/test_bench_e2e.py -q`
Expected: PASS. Если падает на `--add-dir`/`--disallowedTools`, проверить порядок аргументов: `--disallowedTools` должен идти последним.

- [ ] **Step 5: Прогнать все тесты**

Run: `.venv/bin/python -m pytest benchmark/tests -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add benchmark/bench_run.py benchmark/run_benchmark.py benchmark/tests/test_bench_e2e.py
git commit -m "feat(bench): оркестрация прогона, CLI и end-to-end тесты" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: README и финальная проверка

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:**
- Consumes: готовый CLI.

- [ ] **Step 1: Дописать README**

Добавить в `benchmark/README.md` раздел:

```markdown
## Прогон и анализ

После подготовки окружения выполните из корня репозитория:

```bash
.venv/bin/python benchmark/run_benchmark.py \
    --limit task##001=30 --limit task##002=120
```

Скрипт выполняет все задачи проекта `tasks/task##*` по очереди в `claude-ds`.
Лимит по умолчанию — `max_minutes` из `task.json`; `--limit` переопределяет его.
Первый `timeout`/`failed`/`incomplete` останавливает следующие задачи, но анализ
по собранным данным всё равно выполняется.

Результаты:

- `<проект>/tmp/RESULT.md` — отчёт и рекомендации по улучшению template;
- `<проект>/tmp/benchmark/<run-id>/` — `metrics.json`, `digest.md`, диффы,
  транскрипты, промпт аналитика и сырой ответ.

Полезные флаги:

- `--task task##001` — ограничить набор задач;
- `--skip-analysis` — только выполнить задачи и собрать метрики;
- `--force` — разрешить прогон на непустом проекте (результат помечается как
  потенциально загрязнённый);
- `--claude-cmd` — другая команда агента (по умолчанию `claude-ds`);
- `--analysis-timeout` — лимит сессии-аналитика в минутах (по умолчанию 30).

Качественный анализ выполняет отдельная сессия `claude-ds` с запретом на
`Edit`/`Write`; она возвращает markdown, который скрипт записывает в `RESULT.md`.
При сбое аналитика отчёт всё равно создаётся — с объективной сводкой и описанием
ошибки. Старый `RESULT.md` не сохраняется.

Тесты раннера (без 1С, сети и реального `claude`):

```bash
.venv/bin/python -m pytest benchmark/tests -q
```
```

- [ ] **Step 2: Прогнать все тесты**

Run: `.venv/bin/python -m pytest benchmark/tests -q`
Expected: PASS.

- [ ] **Step 3: Проверить CLI**

Run: `.venv/bin/python benchmark/run_benchmark.py --help`
Expected: код 0, справка со всеми флагами.

- [ ] **Step 4: Проверить, что тесты не задевают реальные каталоги**

Run: `git status --porcelain`
Expected: пусто (кроме изменённого `benchmark/README.md`).

- [ ] **Step 5: Коммит**

```bash
git add benchmark/README.md
git commit -m "docs(bench): прогон и анализ benchmark-задач" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Проверка плана против спецификации

- CLI, env, задачи, лимиты, `--force`, `--skip-analysis` — Task 1, 8.
- Preflight, baseline, артефакты, git-диффы — Task 2.
- Таймаут и process group, stream-json, поиск транскрипта — Task 3.
- Дайджест, сабагенты, ошибки, простои, классы команд — Task 4.
- Этапы, итерации тестов/ревью, анализаторы, пропуски слоёв — Task 5.
- Дайджест для аналитика — Task 6.
- Промпт аналитика, ограничения пользователя, fallback `RESULT.md` — Task 7.
- Остановка после сбоя, анализ по частичным данным, коды выхода, e2e — Task 8.
- README и проверка — Task 9.
