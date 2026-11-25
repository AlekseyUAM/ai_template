#!/usr/bin/env python3
"""Stage-scoped benchmark runner: один свежий процесс claude на каждый этап.

Зачем: на локальной модели один процесс на всю задачу раздувает контекст.
Здесь этапы идут последовательно, но каждый — в отдельном `claude -p` с чистым
контекстом. Состояние передаётся через task.json и артефакты задачи.

    python benchmark/stage_run.py --task task#004 \
        --claude-cmd D:/projects/test/claude-strata.bat --stages analyze

Остановка: если этап не дошёл до статуса done, не создал артефакт или упал по
таймауту, раннер останавливается и печатает диагностику; следующие этапы не
запускаются.

Бюджет: `max_minutes` задачи — общий на все этапы. Каждый этап получает
остаток бюджета (или явный `--limit-stage`, если он меньше), а после этапа
остаток уменьшается на фактическую длительность; неизрасходованные минуты
переходят следующим. `DEFAULT_STAGE_LIMITS` действуют только без `max_minutes`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_run import (BenchError, ensure_claude_cmd,  # noqa: E402
                       read_env_file, resolve_claude_cmd, resolve_placement,
                       resolve_project_dir)
from bench_metrics import parse_stream  # noqa: E402
from claude_proc import run_claude_process  # noqa: E402

DEFAULT_STAGE_LIMITS = {
    "analyze": 20,
    "plan": 15,
    "tests": 30,
    "develop": 40,
    "testing": 10,
    "review": 25,
    "docs": 15,
}

STAGE_HINTS = {
    "analyze": "Составь спецификацию задачи в ANALYZE.md.",
    "plan": "Составь технический дизайн в ARCHITECT.md.",
    "tests": "Напиши тесты и красный смоук: TESTS.md + тестовый модуль/config.",
    "develop": "Реализуй код по ТД и тестам, выполни проверки и загрузку в ИБ; "
               "результат — DEVELOP.md.",
    "testing": "Прогони тесты и запиши вердикт TESTING.md "
               "(виновник: код или тест); код и тесты оставь без изменений.",
    "review": "Проведи независимое ревью и запиши REVIEW.md. Код не правь.",
    "docs": "Напиши документацию; результат — DOCS.md.",
}


def venv_python(project: Path) -> str:
    suffix = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return str(project / ".venv" / suffix)


def task_folder(raw: str) -> str:
    value = raw.strip()
    if value.startswith("task#"):
        return value
    if value.startswith("#"):
        return "task" + value
    if value.isdigit():
        return f"task#{int(value):03d}"
    return value


def read_task(task_dir: Path) -> dict:
    path = task_dir / "task.json"
    if not path.is_file():
        raise BenchError(f"нет task.json: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchError(f"не читается {path}: {exc}") from exc


def stages_of(data: dict) -> list[dict]:
    stages = [s for s in data.get("stages") or []
              if isinstance(s, dict) and s.get("enabled")]
    return stages


def select_stages(stages: list[dict], raw: str | None) -> list[dict]:
    if not raw:
        return stages
    wanted = [item.strip() for item in raw.split(",") if item.strip()]
    known = {s.get("name") for s in stages}
    unknown = [item for item in wanted if item not in known]
    if unknown:
        raise BenchError(
            f"неизвестные/выключенные этапы: {', '.join(unknown)}; "
            f"доступны: {', '.join(sorted(str(x) for x in known))}")
    return [s for s in stages if s.get("name") in wanted]


def parse_stage_overrides(raw_values: list[str]) -> dict[str, int]:
    """Explicit --limit-stage values (only the stages named by the user)."""
    overrides: dict[str, int] = {}
    for raw in raw_values:
        if "=" not in raw:
            raise BenchError(f"--limit-stage: ожидается этап=минуты, получено {raw!r}")
        name, value = raw.split("=", 1)
        name = name.strip()
        if not name:
            raise BenchError(f"--limit-stage: пустое имя этапа в {raw!r}")
        try:
            minutes = int(value.strip())
        except ValueError:
            raise BenchError(f"--limit-stage: не число минут в {raw!r}") from None
        if minutes <= 0:
            raise BenchError(f"--limit-stage: минуты должны быть > 0: {raw!r}")
        overrides[name] = minutes
    return overrides


def parse_stage_limits(raw_values: list[str]) -> dict[str, int]:
    limits = dict(DEFAULT_STAGE_LIMITS)
    limits.update(parse_stage_overrides(raw_values))
    return limits


def task_budget_minutes(task_data: dict) -> int | None:
    """`max_minutes` задачи or None when it is absent/invalid."""
    try:
        value = int(task_data.get("max_minutes"))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def stage_limit_minutes(name: str, remaining_min: float | None,
                        overrides: dict[str, int] | None = None) -> int:
    """Per-stage hard limit from the shared task budget.

    With `max_minutes`, the whole remaining budget belongs to the current
    stage; default per-stage limits are not applied (a stage may take as much
    as it needs, at the expense of the following stages). `--limit-stage`
    remains an optional explicit cap. Without `max_minutes` the stage falls
    back to its default limit. Returns 0 when the budget is spent.
    """
    explicit = (overrides or {}).get(name)
    if remaining_min is None:
        return explicit if explicit is not None else DEFAULT_STAGE_LIMITS.get(name, 30)
    if remaining_min < 1:
        return 0
    limit = int(remaining_min)
    if explicit is not None:
        limit = min(explicit, limit)
    return limit


def set_status(project: Path, folder: str, stage: str, status: str) -> None:
    script = project / ".claude" / "tools" / "task_status.py"
    if not script.is_file():
        print(f"[stage] нет task_status.py: {script}", file=sys.stderr)
        return
    cmd = [venv_python(project), str(script), f"tasks/{folder}", stage, status]
    result = subprocess.run(cmd, cwd=project, text=True, capture_output=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = ((result.stdout or "") + (result.stderr or "")).strip()[-800:]
        print(f"[stage] task_status {stage} {status}: код {result.returncode}: {tail}",
              file=sys.stderr)


def stage_prompt(project: Path, folder: str, stage: dict, limit_min: int,
                 brief: str | None = None) -> str:
    name = str(stage.get("name") or "?")
    subagent = str(stage.get("subagent") or "")
    artifact = str(stage.get("artifact") or "")
    checklist = (f".claude/checklists/{subagent}.md" if subagent
                 else ".claude/rules/single-agent-workflow.md")
    hint = STAGE_HINTS.get(name, "")
    python = venv_python(project)
    lines = [
        f"Ты выполняешь ТОЛЬКО этап «{name}» задачи tasks/{folder}.",
        f"Вход: tasks/{folder}/TASK.md, tasks/{folder}/task.json и артефакты "
        "предыдущих этапов. Не перечитывай всю задачу, если нужного нет в артефактах.",
        f"Чеклист этапа: {checklist} — пройди его.",
        "Первое действие до вызова инструментов — Skill mcp-usage.",
    ]
    if hint:
        lines.append(hint)
    if artifact:
        lines.append(f"Артефакт этапа: tasks/{folder}/{artifact}. Запиши его.")
    lines += [
        "Не начинай другие этапы. После завершения:",
        f"  {python} .claude/tools/task_status.py tasks/{folder} {name} done --files <файлы>",
        "и заверши процесс.",
        f"Жёсткий лимит этапа: {limit_min} мин. "
        "При нехватке времени приоритет — обязательным пунктам чеклиста.",
        "Работай в главном потоке; Agent/Task/SendMessage не вызывай; "
        "`.claude/**` не меняй.",
    ]
    stage_brief_path = project / "tmp" / "stage-briefs" / f"{name}.md"
    if stage_brief_path.is_file():
        try:
            stage_brief = stage_brief_path.read_text(encoding="utf-8").strip()
        except OSError:
            stage_brief = ""
        if stage_brief:
            lines += ["", "=== Re-brief этапа (обязателен) ===",
                      stage_brief]
    if brief and brief.strip():
        lines += ["", "=== Re-brief оркестратора (обязателен) ===",
                  brief.strip()]
    return "\n".join(lines)


def stream_metrics(path: Path) -> dict:
    max_input = 0
    compactions = 0
    tool_errors = 0
    assistant_events = 0
    tools: Counter[str] = Counter()
    if path.is_file():
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "assistant":
                    assistant_events += 1
                    message = event.get("message") or {}
                    usage = message.get("usage") or {}
                    tokens = ((usage.get("input_tokens") or 0)
                              + (usage.get("cache_read_input_tokens") or 0)
                              + (usage.get("cache_creation_input_tokens") or 0))
                    max_input = max(max_input, tokens)
                    for block in message.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tools[str(block.get("name"))] += 1
                elif (event.get("type") == "system"
                      and event.get("subtype") == "compact_boundary"):
                    compactions += 1
                elif event.get("type") == "user":
                    content = (event.get("message") or {}).get("content")
                    if isinstance(content, list):
                        tool_errors += sum(
                            1 for block in content
                            if isinstance(block, dict)
                            and block.get("type") == "tool_result"
                            and block.get("is_error"))
    summary = parse_stream(path)
    return {
        "assistant_events": assistant_events,
        "max_input_tokens": max_input,
        "compactions": compactions,
        "tool_errors": tool_errors,
        "tools": dict(tools.most_common()),
        "session_id": summary.session_id,
        "parse_errors": summary.parse_errors,
    }


def project_slug(project: Path) -> str:
    return (str(project.resolve())
            .replace(":", "-").replace("\\", "-").replace("/", "-"))


def find_session_file(project: Path, started_epoch: float,
                      projects_root: Path | None = None) -> Path | None:
    """Сессии claude; для docker-размещения — в HOME контейнера на хосте."""
    base = (Path(projects_root) if projects_root
            else Path.home() / ".claude" / "projects")
    root = base / project_slug(project)
    if not root.is_dir():
        return None
    candidates = [p for p in root.glob("*.jsonl")
                  if p.stat().st_mtime >= started_epoch - 2]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def session_metrics(path: Path) -> dict:
    """Метрики из session-файла Claude Code (если stream не stream-json)."""
    max_input = 0
    compactions = 0
    tool_errors = 0
    assistant_events = 0
    tools: Counter[str] = Counter()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "assistant":
                assistant_events += 1
                message = event.get("message") or {}
                usage = message.get("usage") or {}
                tokens = ((usage.get("input_tokens") or 0)
                          + (usage.get("cache_read_input_tokens") or 0)
                          + (usage.get("cache_creation_input_tokens") or 0))
                max_input = max(max_input, tokens)
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tools[str(block.get("name"))] += 1
            elif (event.get("type") == "system"
                  and event.get("subtype") == "compact_boundary"):
                compactions += 1
            elif event.get("type") == "user":
                content = (event.get("message") or {}).get("content")
                if isinstance(content, list):
                    tool_errors += sum(
                        1 for block in content
                        if isinstance(block, dict)
                        and block.get("type") == "tool_result"
                        and block.get("is_error"))
    return {
        "assistant_events": assistant_events,
        "max_input_tokens": max_input,
        "compactions": compactions,
        "tool_errors": tool_errors,
        "tools": dict(tools.most_common()),
        "session_id": path.stem,
        "parse_errors": 0,
        "metrics_source": "session",
        "session_file": str(path),
    }


def stage_status(task_dir: Path, name: str) -> str | None:
    try:
        data = read_task(task_dir)
    except BenchError:
        return None
    for stage in data.get("stages") or []:
        if isinstance(stage, dict) and stage.get("name") == name:
            return stage.get("status")
    return None


def artifact_exists(task_dir: Path, artifact: str) -> bool:
    if not artifact:
        return True
    path = task_dir / artifact
    if path.is_file():
        return True
    # Вердикт мог быть заархивирован самим этапом (TESTING.<n>.md) — артефакт есть.
    if artifact in ("TESTING.md", "REVIEW.md"):
        return any(task_dir.glob(f"{path.stem}.*.md"))
    return False


def run_stage(*, project: Path, folder: str, stage: dict, claude_cmd: str,
              limit_min: int, run_dir: Path, brief: str | None = None,
              prefix_argv: list[str] | None = None,
              sessions_root: Path | None = None,
              kill_agent=None) -> dict:
    name = str(stage.get("name") or "?")
    artifact = str(stage.get("artifact") or "")
    task_dir = project / "tasks" / folder
    prompt = stage_prompt(project, folder, stage, limit_min, brief)
    stream_path = run_dir / f"{name}.stream.jsonl"
    stderr_path = run_dir / f"{name}.stderr.log"
    prompt_path = run_dir / f"{name}.prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")

    set_status(project, folder, name, "running")
    env = os.environ.copy()
    env["TASK_STAGE"] = name
    started_epoch = time.time()
    process = run_claude_process(
        cmd=claude_cmd, prompt=prompt, cwd=project,
        timeout_sec=limit_min * 60, stdout_path=stream_path,
        stderr_path=stderr_path, env=env, prefix_argv=prefix_argv)
    exit_code = process.exit_code
    timed_out = process.timed_out
    duration = process.duration_sec
    if timed_out and kill_agent is not None:
        kill_agent()
    metrics = stream_metrics(stream_path)
    if metrics.get("assistant_events", 0) == 0:
        session_file = find_session_file(project, started_epoch,
                                         projects_root=sessions_root)
        if session_file:
            metrics = session_metrics(session_file)
    else:
        metrics["metrics_source"] = "stream"
    status_after = stage_status(task_dir, name)
    result = {
        "name": name,
        "artifact": artifact,
        "artifact_exists": artifact_exists(task_dir, artifact),
        "status_before_run": stage.get("status"),
        "status_after": status_after,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_sec": round(duration, 1),
        "limit_min": limit_min,
        "stream": str(stream_path),
        "stderr": str(stderr_path),
        "prompt": str(prompt_path),
        "metrics": metrics,
    }
    return result


def write_summary(run_dir: Path, run: dict) -> None:
    with (run_dir / "run.json").open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(run, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    lines = [
        f"# Stage run {run['run_id']}",
        "",
        f"- Проект: `{run['project']}`",
        f"- Задача: `{run['task']}`",
        f"- Агент: `{run['claude_cmd']}`",
        "",
        "| Этап | Статус | Артефакт | Время | turns | max input | компакты | ошибки |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in run["stages"]:
        metrics = item.get("metrics") or {}
        lines.append(
            f"| {item['name']} | {item.get('status_after')} | "
            f"{'ok' if item.get('artifact_exists') else 'нет'} | "
            f"{item.get('duration_sec')} с | {metrics.get('assistant_events')} | "
            f"{metrics.get('max_input_tokens')} | {metrics.get('compactions')} | "
            f"{metrics.get('tool_errors')} |")
    if run.get("stopped"):
        lines += ["", f"Остановлено: {run['stopped']}"]
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="task#004, #004 или 004")
    parser.add_argument("--project", help="каталог проекта")
    parser.add_argument("--env", help="env-файл; по умолчанию benchmark/test.env")
    parser.add_argument("--claude-cmd", default=None,
                        help="команда агента (по умолчанию — "
                             "AGENTMON_CLAUDE_CMD из test.env)")
    parser.add_argument("--stages", help="подмножество этапов через запятую")
    parser.add_argument("--limit-stage", action="append", default=[],
                        metavar="ЭТАП=МИНУТЫ", help="лимит этапа (повторяемый)")
    parser.add_argument("--run-id", help="id прогона (по умолчанию timestamp)")
    parser.add_argument("--brief", help="re-brief оркестратора: текст, "
                                        "дописываемый в конец промпта этапа")
    parser.add_argument("--brief-file", help="файл с re-brief (UTF-8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать этапы и промпты, ничего не запускать")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    env_path = (Path(args.env).expanduser() if args.env
                else repo_root / "benchmark" / "test.env")
    if not env_path.is_absolute():
        env_path = (repo_root / env_path).resolve()
    try:
        project = resolve_project_dir(args.project, env_path, repo_root)
        cmd = resolve_claude_cmd(args.claude_cmd, env_path)
        ensure_claude_cmd(cmd)
        placement, docker_image = resolve_placement(env_path)
        folder = task_folder(args.task)
        task_dir = project / "tasks" / folder
        data = read_task(task_dir)
        all_stages = stages_of(data)
        stages = select_stages(all_stages, args.stages)
        if not stages:
            raise BenchError("нет выбранных enabled-этапов")
        overrides = parse_stage_overrides(args.limit_stage)
        budget = task_budget_minutes(data)
        remaining = float(budget) if budget is not None else None
        brief = args.brief
        if args.brief_file:
            brief_path = Path(args.brief_file).expanduser()
            if not brief_path.is_absolute():
                brief_path = (repo_root / brief_path).resolve()
            try:
                brief = brief_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise BenchError(f"не читается --brief-file {brief_path}: {exc}") from exc
        # Перед выбранным этапом все более ранние enabled-этапы должны быть done/skipped.
        order = [s.get("name") for s in all_stages]
        first = order.index(stages[0].get("name"))
        for prior in all_stages[:first]:
            if prior.get("status") not in ("done", "skipped"):
                raise BenchError(
                    f"предыдущий этап «{prior.get('name')}» не done "
                    f"(статус {prior.get('status')!r}); сначала заверши его")
        if args.dry_run:
            if budget is not None:
                print(f"Бюджет задачи: {budget} мин на все этапы; "
                      f"ниже — верхние границы этапов.")
            for stage in stages:
                name = str(stage.get("name") or "?")
                limit_min = stage_limit_minutes(name, remaining, overrides)
                if limit_min <= 0:
                    print(f"=== {name} (бюджет задачи исчерпан) ===")
                    break
                suffix = (f"лимит до {limit_min} мин"
                          if budget is not None else f"лимит {limit_min} мин")
                print(f"=== {name} ({suffix}) ===")
                print(stage_prompt(project, folder, stage, limit_min, brief))
                print()
            if budget is not None:
                print("Фактический лимит этапа = остаток бюджета на старте "
                      "этапа (или явный --limit-stage, если он меньше).")
            return 0
        # Поэтапный режим работает только с хостовым каталогом проекта:
        # при BENCH_PLACEMENT=docker проект живёт в томе контейнера.
        if placement == "docker":
            raise BenchError(
                "stage_run.py не поддерживает BENCH_PLACEMENT=docker — "
                "используйте run_benchmark.py (он умеет docker)")
        bench_docker = None
        docker_ctx = None
        run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = project / "tmp" / "stage-runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "project": str(project),
            "task": folder,
            "claude_cmd": cmd,
            "placement": placement,
            "task_budget_minutes": budget,
            "stages": [],
            "stopped": None,
        }
        print(f"[{datetime.now():%H:%M:%S}] stage-run {run_id}: {folder}, "
              f"этапы: {', '.join(str(s.get('name')) for s in stages)}")
        for stage in stages:
            name = str(stage.get("name") or "?")
            limit_min = stage_limit_minutes(name, remaining, overrides)
            if limit_min <= 0:
                run["stopped"] = "бюджет задачи исчерпан"
                break
            left = (f", остаток {remaining:.1f} мин"
                    if remaining is not None else "")
            print(f"[{datetime.now():%H:%M:%S}] ▶ {name} "
                  f"(лимит {limit_min} мин{left})")
            prefix = None
            kill_agent = None
            if docker_ctx is not None:
                prefix = bench_docker.agent_prefix(
                    project, repo_root, docker_image, docker_ctx.host_cmd,
                    {"TASK_STAGE": name})
                kill_agent = lambda: bench_docker.kill_agent(project)  # noqa: E731
            result = run_stage(
                project=project, folder=folder, stage=stage,
                claude_cmd=cmd, limit_min=limit_min,
                run_dir=run_dir, brief=brief, prefix_argv=prefix,
                sessions_root=(docker_ctx.sessions_root
                               if docker_ctx is not None else None),
                kill_agent=kill_agent)
            if remaining is not None:
                remaining = max(0.0, remaining - result["duration_sec"] / 60)
                result["budget_remaining_after"] = round(remaining, 1)
            run["stages"].append(result)
            metrics = result["metrics"]
            print(f"[{datetime.now():%H:%M:%S}] {'■' if result['timed_out'] else '✓' if result['status_after'] == 'done' else '✗'} "
                  f"{name}: {result['duration_sec']} с, статус "
                  f"{result['status_after']!r}, артефакт "
                  f"{'ok' if result['artifact_exists'] else 'НЕТ'}, "
                  f"turns={metrics['assistant_events']}, "
                  f"max_input={metrics['max_input_tokens']}, "
                  f"компактов={metrics['compactions']}")
            if result["timed_out"]:
                run["stopped"] = f"таймаут этапа {name}"
                break
            if result["status_after"] != "done":
                run["stopped"] = (f"этап {name} не дошёл до done "
                                  f"(статус {result['status_after']!r})")
                break
            if not result["artifact_exists"]:
                run["stopped"] = f"этап {name} не создал артефакт {result['artifact']}"
                break
        run["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        write_summary(run_dir, run)
        print(f"[{datetime.now():%H:%M:%S}] итог: {run_dir / 'summary.md'}")
        if run["stopped"]:
            print(f"[{datetime.now():%H:%M:%S}] ОСТАНОВЛЕНО: {run['stopped']}")
            return 1
        return 0
    except BenchError as exc:
        print(f"stage-run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
