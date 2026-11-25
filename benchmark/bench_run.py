"""Оркестрация benchmark-прогона: конфиг, preflight, запуск задач, git, процесс агента."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from bench_analysis import (build_prompt, deterministic_report,
                            extract_analyst_text, prepare_inputs, write_report)
from bench_metrics import (aggregate_environment, collect_task_state,
                           cycle_metrics, find_session_files, parse_stream,
                           render_digest, run_static_analyzers, stage_table,
                           summarize_transcripts, write_json_atomic)
from claude_proc import resolve_command, run_claude_process


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
    # "local" — агент на хосте; "docker" — в контейнере проекта.
    placement: str = "local"
    docker_image: str | None = None
    pre_snapshot: Path | None = None   # docker: снимок проекта до прогона


@dataclass(frozen=True)
class GitState:
    head: str
    status: str


_ARTIFACT_GLOBS = (
    "ANALYZE.md", "ARCHITECT.md", "TESTS*.md", "DEVELOP*.md", "TESTING*.md",
    "REVIEW*.md", "DOCS*.md", "task.diff", "USER_FEEDBACK.md",
)


def _git(project_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # safe.directory: после docker-размещения .git мог быть создан контейнером
    # от другого/хостового uid — иначе git откажется работать с репозиторием.
    proc = subprocess.run(["git", "-c", f"safe.directory={project_dir}", *args],
                          cwd=project_dir, text=True,
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


@dataclass(frozen=True)
class DockerContext:
    """Как обращаться к docker-проекту из раннера."""
    agent_prefix: list[str]      # docker exec -i ... <cmd>
    exec_prefix: list[str]       # docker exec -w ... (анализаторы)
    sessions_root: Path          # каталог сессий claude (в контейнере — host-каталог)
    host_cmd: list[str]          # argv команды агента на хосте
    project_dir: Path
    repo_root: Path
    docker_image: str


def resolve_placement(env_path: Path) -> tuple[str, str | None]:
    """(placement, docker_image) из env-файла — общая логика раннеров."""
    env_values = read_env_file(env_path)
    placement = (env_values.get("BENCH_PLACEMENT") or "local").strip().lower()
    if placement not in ("local", "docker"):
        raise BenchError(
            f"BENCH_PLACEMENT должен быть local или docker, получено {placement!r}")
    docker_image = None
    if placement == "docker":
        docker_image = (env_values.get("BENCH_DOCKER_IMAGE") or "").strip() or None
        if not docker_image:
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)",
                              env_values.get("BENCH_PLATFORM_PATH", ""))
            if not match:
                raise BenchError(
                    "BENCH_DOCKER_IMAGE не задан, и версию платформы не удалось "
                    "определить из BENCH_PLATFORM_PATH")
            docker_image = f"ai1c-agent:{match.group(1)}"
    return placement, docker_image


def docker_context(project_dir: Path, repo_root: Path, claude_cmd: str,
                   docker_image: str) -> DockerContext:
    """Поднять контейнер проекта и собрать префиксы docker exec."""
    import bench_docker

    try:
        host_cmd = bench_docker.host_argv(claude_cmd)
        bench_docker.ensure_container(project_dir, repo_root,
                                      docker_image, host_cmd)
    except (FileNotFoundError, RuntimeError) as exc:
        raise BenchError(str(exc)) from None
    return DockerContext(
        agent_prefix=bench_docker.agent_prefix(
            project_dir, repo_root, docker_image, host_cmd),
        exec_prefix=bench_docker.exec_prefix(project_dir),
        sessions_root=bench_docker.sessions_root(repo_root),
        host_cmd=host_cmd,
        project_dir=project_dir,
        repo_root=repo_root,
        docker_image=docker_image,
    )


def _docker_git_state(project_dir: Path) -> GitState:
    """git-состояние проекта в контейнере (без снапшота — только exec)."""
    import bench_docker
    head = bench_docker.git(project_dir, "rev-parse", "HEAD").stdout.strip()
    status = bench_docker.git(project_dir, "status", "--porcelain").stdout
    return GitState(head=head, status=status)


def _safe_git_state(path: Path) -> GitState | None:
    try:
        return git_state(path)
    except BenchError:
        return None


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


def _split_z(output: str) -> list[str]:
    """Разбить вывод git с -z по NUL; пустые элементы отбросить."""
    return [item for item in output.split("\0") if item]


def _untracked_files(project_dir: Path) -> list[str]:
    # Без core.quotepath=false git кодирует кириллицу в octal-escape, и пути
    # новых файлов не совпадают с реальными именами на диске.
    out = _git(project_dir, "-c", "core.quotepath=false", "ls-files", "-z",
               "--others", "--exclude-standard").stdout
    return _split_z(out)


def changed_files(project_dir: Path, before_head: str) -> list[str]:
    out = _git(project_dir, "-c", "core.quotepath=false", "diff",
               "--name-only", "-z", before_head).stdout
    files = set(_split_z(out))
    files.update(_untracked_files(project_dir))
    return sorted(files)


def collect_diff(project_dir: Path, before_head: str, out_path: Path,
                 stat_path: Path) -> list[str]:
    diff = _git(project_dir, "-c", "core.quotepath=false", "diff",
                before_head).stdout
    stat = _git(project_dir, "-c", "core.quotepath=false", "diff", "--stat",
                before_head).stdout
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


@dataclass
class ClaudeRun:
    exit_code: int | None
    timed_out: bool
    duration_sec: float
    stream_path: Path
    stderr_path: Path
    stream: object
    session: object


def run_claude(*, cmd: str, prompt: str, cwd: Path, timeout_sec: float,
               stream_path: Path, stderr_path: Path,
               extra_args: tuple[str, ...] = (),
               prefix_argv: list[str] | None = None,
               projects_root: Path | None = None) -> ClaudeRun:
    """Запустить claude в отдельной сессии и вернуть результат."""
    result = run_claude_process(
        cmd=cmd, prompt=prompt, cwd=cwd, timeout_sec=timeout_sec,
        stdout_path=stream_path, stderr_path=stderr_path,
        extra_args=extra_args, prefix_argv=prefix_argv)
    stream = parse_stream(stream_path)
    session = find_session_files(stream.session_id, projects_root)
    return ClaudeRun(exit_code=result.exit_code, timed_out=result.timed_out,
                     duration_sec=result.duration_sec, stream_path=stream_path,
                     stderr_path=stderr_path, stream=stream, session=session)


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
            inner = value[1:-1]
            # Снимаем кавычки, только если это обрамление всего значения:
            # у команды вида `"путь" --flag "аргумент"` кавычки внутри.
            if value[0] not in inner:
                value = inner
        values[key.strip()] = value
    return values


def resolve_project_dir(cli_project: str | None, env_path: Path,
                        repo_root: Path, placement: str = "local") -> Path:
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
    # docker: путь проекта — внутри контейнера (/workspace), на хосте его нет.
    if placement != "docker" and not path.is_dir():
        raise BenchError(f"каталог проекта не найден: {path}")
    return path


def _task_info(folder: str, path: Path, raw: str) -> TaskInfo:
    """Разобрать task.json в TaskInfo (общая логика local/docker)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BenchError(f"{folder}/task.json: {exc}") from exc
    data = data if isinstance(data, dict) else {}
    try:
        max_minutes = int(data.get("max_minutes"))
    except (TypeError, ValueError) as exc:
        raise BenchError(
            f"{folder}/task.json: max_minutes должен быть целым числом") from exc
    if max_minutes < 1:
        raise BenchError(f"{folder}/task.json: max_minutes должен быть ≥ 1")
    identifier = str(data.get("identifier") or folder.removeprefix("task#"))
    return TaskInfo(
        folder=folder,
        path=path,
        identifier=identifier,
        max_minutes=max_minutes,
        status=str(data.get("status") or ""),
        raw=data,
    )


def discover_tasks(project_dir: Path) -> list[TaskInfo]:
    tasks_root = project_dir / "tasks"
    if not tasks_root.is_dir():
        raise BenchError(f"нет каталога задач: {tasks_root}")
    tasks: list[TaskInfo] = []
    for path in sorted(tasks_root.iterdir(), key=lambda p: p.name):
        if not path.is_dir() or not path.name.startswith("task#"):
            continue
        task_json = path / "task.json"
        if not task_json.is_file():
            raise BenchError(f"{path.name}: нет task.json")
        try:
            raw = task_json.read_text(encoding="utf-8")
        except OSError as exc:
            raise BenchError(f"{path.name}/task.json: {exc}") from exc
        tasks.append(_task_info(path.name, path, raw))
    if not tasks:
        raise BenchError(f"в {tasks_root} нет задач task#*")
    return tasks


def discover_tasks_docker(project_dir: Path) -> list[TaskInfo]:
    """Задачи проекта в контейнере (через docker exec, без снапшота)."""
    import bench_docker
    tasks_root = f"{project_dir}/tasks"
    names = [name for name in bench_docker.list_dir(project_dir, tasks_root)
             if name.startswith("task#")]
    tasks: list[TaskInfo] = []
    for name in sorted(names):
        try:
            raw = bench_docker.read_text(project_dir, f"{tasks_root}/{name}/task.json")
        except OSError as exc:
            raise BenchError(f"{name}: нет task.json ({exc})") from None
        tasks.append(_task_info(name, Path(tasks_root) / name, raw))
    if not tasks:
        raise BenchError(f"в {tasks_root} нет задач task#*")
    return tasks


def _task_aliases(task: TaskInfo) -> set[str]:
    folder_number = task.folder.removeprefix("task#").lstrip("#")
    aliases = {
        task.folder,
        task.identifier,
        task.identifier.removeprefix("#"),
        folder_number,
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


def _write_report(options: RunOptions, run_dir: Path, text: str,
                  docker_ctx: "DockerContext | None") -> Path:
    """Записать RESULT.md: локально — в проект, docker — в прогон и в контейнер."""
    if docker_ctx is None:
        return write_report(options.project_dir, text)
    target = run_dir / "RESULT.md"
    target.write_text(text if text.endswith("\n") else text + "\n",
                      encoding="utf-8")
    import bench_docker
    bench_docker.write_text(options.project_dir,
                            f"{options.project_dir}/tmp/RESULT.md", text)
    return target


def prepare_run_dir(project_dir: Path, *, repo_root: Path | None = None,
                    placement: str = "local") -> Path:
    if placement == "docker":
        # docker: проект в томе, а прогон виден и хосту, и контейнеру —
        # каталог в репозитории (он смонтирован в контейнер по тому же пути).
        base = Path(repo_root) / "benchmark" / ".bench-runs"
    else:
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
                        help="задача: task#001, #001 или 001 (повторяемый)")
    parser.add_argument("--limit", action="append", default=[], dest="limit_args",
                        help="лимит в минутах: task#001=30, #002=120 (повторяемый)")
    parser.add_argument("--claude-cmd", default=None,
                        help="команда агента (по умолчанию — "
                             "AGENTMON_CLAUDE_CMD из test.env)")
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
    placement, docker_image = resolve_placement(env_path)
    project_dir = resolve_project_dir(ns.project, env_path, repo_root,
                                      placement=placement)
    pre_snapshot = None
    if placement == "docker":
        # Проект живёт в томе контейнера: для чтения задач снимаем снапшот.
        import bench_docker
        try:
            host_cmd = bench_docker.host_argv(
                resolve_claude_cmd(ns.claude_cmd, env_path))
            bench_docker.ensure_container(project_dir, repo_root,
                                          docker_image, host_cmd)
        except (FileNotFoundError, RuntimeError) as exc:
            raise BenchError(str(exc)) from None
        pre_snapshot = _new_snapshot_dir(repo_root)
        bench_docker.snapshot(project_dir, pre_snapshot)
        tasks = discover_tasks(pre_snapshot)
    else:
        tasks = discover_tasks(project_dir)
    selected = select_tasks(tasks, ns.task_selectors)
    limits = apply_limits(selected, ns.limit_args)
    if ns.analysis_timeout < 1:
        raise BenchError("--analysis-timeout должен быть ≥ 1")
    cmd = resolve_claude_cmd(ns.claude_cmd, env_path)
    return RunOptions(
        repo_root=repo_root,
        project_dir=project_dir,
        tasks=selected,
        limits=limits,
        claude_cmd=cmd,
        analysis_timeout_min=ns.analysis_timeout,
        skip_analysis=bool(ns.skip_analysis),
        force=bool(ns.force),
        run_dir=None,
        env_file=env_path,
        placement=placement,
        docker_image=docker_image,
        pre_snapshot=pre_snapshot,
    )


def _new_snapshot_dir(repo_root: Path) -> Path:
    """Временный каталог снапшота (в .gitignore: benchmark/.bench-snap)."""
    base = Path(repo_root) / "benchmark" / ".bench-snap"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    candidate = base / stamp
    candidate.mkdir(parents=True)
    return candidate


def resolve_claude_cmd(explicit: str | None, env_path: Path) -> str:
    """Команда агента: --claude-cmd → AGENTMON_CLAUDE_CMD из test.env → ошибка."""
    cmd = (explicit or "").strip()
    if not cmd:
        cmd = (read_env_file(env_path).get("AGENTMON_CLAUDE_CMD") or "").strip()
    if not cmd:
        raise BenchError(
            f"AGENTMON_CLAUDE_CMD не задан в {env_path}; укажите --claude-cmd")
    return cmd


def ensure_claude_cmd(cmd: str) -> None:
    """Проверить, что команда агента существует и исполняема."""
    try:
        resolve_command(cmd)
    except FileNotFoundError:
        raise BenchError(
            f"команда агента не найдена или не исполняема: {cmd}") from None


def build_task_prompt(folder: str, limit_minutes: int | None = None) -> str:
    prompt = (f"Выполни задачу tasks/{folder} по этапам из её task.json. "
              f"Первое действие до вызова инструментов — Skill mcp-usage. "
              f"Следуй правилу single-agent-workflow и чеклистам этапов. "
              f"Работай по TASK.md, изменения — в src/cf/**; `.claude/**` не меняй. "
              f"План TASK.md — контракт: каждый пункт реализуй как написано и отрази в DEVELOP.md.")
    if limit_minutes is not None:
        prompt += (f" Жёсткий лимит выполнения задачи: {limit_minutes} мин. "
                   f"При нехватке времени приоритет — обязательным пунктам плана.")
    return prompt


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
    init = getattr(run.stream, "init", {}) or {}
    tools = init.get("tools") or []
    return {
        "session_id": run.stream.session_id,
        "parse_errors": run.stream.parse_errors,
        "duration_ms": result.get("duration_ms"),
        "num_turns": result.get("num_turns"),
        "is_error": result.get("is_error"),
        "has_sendmessage": "SendMessage" in tools,
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
    try:
        return _execute(options)
    finally:
        if options.pre_snapshot is not None:
            shutil.rmtree(options.pre_snapshot, ignore_errors=True)


def _execute(options: RunOptions) -> int:
    ensure_claude_cmd(options.claude_cmd)
    # Для docker снимок проекта — рабочая копия на хосте: git, свежесть,
    # метрики и отчёты считаются по ней; агент работает в контейнере.
    work_project = (options.pre_snapshot if options.placement == "docker"
                    else options.project_dir)
    ensure_fresh(work_project, list(options.tasks), force=options.force)
    docker_ctx = None
    docker_mod = None
    if options.placement == "docker":
        import bench_docker as docker_mod  # noqa: F401
        docker_ctx = docker_context(options.project_dir, options.repo_root,
                                    options.claude_cmd, options.docker_image)
    run_dir = prepare_run_dir(options.project_dir, repo_root=options.repo_root,
                              placement=options.placement)
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
            "placement": options.placement,
            "force": options.force,
            "contaminated": bool(options.force),
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
    report_tasks: list[TaskInfo] = []
    for task in options.tasks:
        log(f"▶ {task.folder}: старт (лимит {options.limits[task.folder]} мин)")
        task_started = _iso_now()
        before = git_state(work_project)
        stream_path = run_dir / "transcripts" / f"{task.folder}.stream.jsonl"
        stderr_path = run_dir / "transcripts" / f"{task.folder}.stderr.log"
        run = run_claude(
            cmd=options.claude_cmd,
            prompt=build_task_prompt(task.folder, options.limits[task.folder]),
            # docker exec работает в контейнере; cwd клиента — валидный хостовый.
            cwd=(run_dir if docker_ctx else options.project_dir),
            timeout_sec=options.limits[task.folder] * 60,
            stream_path=stream_path,
            stderr_path=stderr_path,
            prefix_argv=docker_ctx.agent_prefix if docker_ctx else None,
            projects_root=docker_ctx.sessions_root if docker_ctx else None,
        )
        if docker_ctx and run.timed_out:
            # docker exec без TTY не убивает процесс при убийстве клиента.
            docker_mod.kill_agent(options.project_dir)
        if docker_ctx:
            # Снимаем состояние проекта из тома и работаем по нему на хосте.
            work_project = docker_mod.snapshot(
                options.project_dir, run_dir / "snapshots" / task.folder)
            post_tasks = {t.folder: t for t in discover_tasks(work_project)}
            post_task = post_tasks.get(task.folder, task)
            report_tasks.append(post_task)
        else:
            post_task = task
        after = git_state(work_project)
        diff_path = run_dir / "diffs" / f"{task.folder}.diff"
        stat_path = run_dir / "diffs" / f"{task.folder}.stat.txt"
        changed = collect_diff(work_project, before.head, diff_path, stat_path)
        try:
            task_json = json.loads((post_task.path / "task.json")
                                   .read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            task_json = {}
        state = collect_task_state(work_project, task)
        transcript = summarize_transcripts(
            Path(options.project_dir) if docker_ctx else options.project_dir,
            run.session, run.stream_path)
        analyzers = run_static_analyzers(
            Path(options.project_dir) if docker_ctx else options.project_dir,
            changed, reference, run_dir / task.folder,
            exec_prefix=docker_ctx.exec_prefix if docker_ctx else None)
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
            "cycles": cycle_metrics(task_json, state, transcript),
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
    run_metrics["run"]["finished_at"] = _iso_now()
    run_metrics["environment"] = aggregate_environment(run_metrics["tasks"])
    write_json_atomic(metrics_path, run_metrics)
    _write_run_json(run_dir, run_metrics)
    digest_path.write_text(render_digest(run_metrics), encoding="utf-8")
    log(f"метрики: {metrics_path}")
    if options.skip_analysis:
        report = deterministic_report(
            run_id=run_dir.name, project_dir=options.project_dir,
            run_dir=run_dir, metrics=run_metrics, skipped=True)
        target = _write_report(options, run_dir, report, docker_ctx)
        run_metrics["analysis"] = {"performed": False, "skipped": True,
                                   "result_path": str(target)}
        write_json_atomic(metrics_path, run_metrics)
        _write_run_json(run_dir, run_metrics)
        log(f"отчёт (без анализа): {target}")
        log.close()
        return 0 if not stopped else 2
    inputs = prepare_inputs(run_dir=run_dir, metrics=run_metrics,
                            digest_path=digest_path)
    _inputs_manifest(manifest_path, options.project_dir, options.repo_root,
                     run_dir, inputs["metrics_path"], inputs["digest_path"],
                     reference, report_tasks or options.tasks)
    prompt = build_prompt(
        run_id=run_dir.name,
        project_dir=options.project_dir,
        repo_root=options.repo_root,
        run_dir=run_dir,
        metrics_path=inputs["metrics_path"],
        digest_path=inputs["digest_path"],
        manifest_path=manifest_path,
        reference_path=reference,
        contaminated=options.force,
        task_folders=[task.folder for task in options.tasks],
    )
    (run_dir / "analysis-prompt.md").write_text(prompt, encoding="utf-8")
    # Проверка «аналитик не изменил проект» — по git в контейнере: снапшот
    # всего проекта на 300+ МБ тут не нужен.
    project_before = (_docker_git_state(options.project_dir) if docker_ctx
                      else git_state(work_project))
    repo_before = _safe_git_state(options.repo_root)
    analyst = run_claude(
        cmd=options.claude_cmd,
        prompt=prompt,
        cwd=(run_dir if docker_ctx else options.project_dir),
        timeout_sec=options.analysis_timeout_min * 60,
        stream_path=run_dir / "analysis-transcripts" / "analyst.stream.jsonl",
        stderr_path=run_dir / "analysis-transcripts" / "analyst.stderr.log",
        extra_args=("--add-dir", str(options.repo_root),
                    "--disallowedTools", "Edit", "MultiEdit", "NotebookEdit",
                    "Write", "Agent"),
        prefix_argv=docker_ctx.agent_prefix if docker_ctx else None,
        projects_root=docker_ctx.sessions_root if docker_ctx else None,
    )
    if docker_ctx and analyst.timed_out:
        docker_mod.kill_agent(options.project_dir)
    project_after = (_docker_git_state(options.project_dir) if docker_ctx
                     else git_state(options.project_dir))
    repo_after = _safe_git_state(options.repo_root)
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
    project_mutated = (project_before.head != project_after.head
                       or project_before.status != project_after.status)
    repo_mutated = bool(
        repo_before and repo_after
        and (repo_before.head != repo_after.head
             or repo_before.status != repo_after.status))
    mutated = project_mutated or repo_mutated
    if mutated:
        heads = [f"проект `{project_before.head[:8]}` → `{project_after.head[:8]}`"]
        if repo_mutated:
            heads.append(f"template `{repo_before.head[:8]}` → `{repo_after.head[:8]}`")
        text += ("\n\n## ⚠ Предупреждение\n\n"
                 "Во время сессии-аналитика изменилось git-состояние проекта "
                 "или репозитория template. Проверьте "
                 + ", ".join(heads)
                 + " и `git status`; отчёт мог быть построен на изменённых "
                 "данных.\n")
        log("⚠ аналитик изменил git-состояние проекта или репозитория template")
    target = _write_report(options, run_dir, text, docker_ctx)
    run_metrics["analysis"] = {
        "performed": True,
        "skipped": False,
        "finished_at": _iso_now(),
        "session_id": analyst.stream.session_id,
        "duration_sec": round(analyst.duration_sec, 1),
        "timed_out": analyst.timed_out,
        "exit_code": analyst.exit_code,
        "error": error,
        "project_mutated": project_mutated,
        "repo_mutated": repo_mutated,
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
