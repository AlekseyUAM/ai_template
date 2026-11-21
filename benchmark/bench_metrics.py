"""Метрики benchmark-прогона: stream-json, транскрипты, дайджест, анализаторы."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
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
    # Claude Code may store session files under a different letter case.
    candidates = {session_id}
    candidates.add(session_id.lower())
    matches = sorted({match for candidate in candidates
                      for match in root.glob(f"*/{candidate}.jsonl")})
    if not matches:
        return SessionFiles(None, ())
    main = matches[0]
    subdir = main.with_suffix("") / "subagents"
    subagents = tuple(sorted(subdir.glob("*.jsonl"))) if subdir.is_dir() else ()
    return SessionFiles(main, subagents)


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
    # Числовые epoch (старые task.json/транскрипты) — тоже время: без этого
    # отметка молча превращалась бы в None и длительность терялась.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
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
                    if tool.tool_use_id and tool.tool_use_id in by_id:
                        # Дубль id: первый tool_use уже связан с tool_result,
                        # повторный блок игнорируем, чтобы не осиротить события.
                        continue
                    events.append(tool)
                    if tool.tool_use_id:
                        by_id[tool.tool_use_id] = tool
            elif event.get("type") == "user":
                for block in blocks:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    result_id = str(block.get("tool_use_id") or "")
                    if not result_id:
                        continue
                    tool = by_id.get(result_id)
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
        return Path(path).resolve().relative_to(project_dir.resolve()).as_posix()
    except (ValueError, OSError):
        return str(path)


def _short_input(event: ToolEvent) -> str:
    for key in ("command", "file_path", "path", "description", "prompt", "skill"):
        value = event.input.get(key)
        if isinstance(value, str):
            return value[:200]
    return ""


def _is_hook_denial(event: ToolEvent) -> bool:
    return bool(event.is_error and "hook error" in (event.result_text or "").lower())


def summarize_events(events: list[ToolEvent], project_dir: Path) -> dict:
    tools = Counter(event.name for event in events)
    errors = [event for event in events if event.is_error]
    hook_denials = sum(1 for event in errors if _is_hook_denial(event))
    mcp_errors = sum(1 for event in errors
                     if event.name.startswith("mcp__")
                     and not _is_hook_denial(event))
    skill_calls = sum(
        1 for event in events
        if event.name == "Skill"
        and str(event.input.get("skill") or "") == "mcp-usage")
    seen_calls: Counter = Counter()
    for event in events:
        seen_calls[(event.name, json.dumps(event.input, ensure_ascii=False,
                                           sort_keys=True, default=str))] += 1
    duplicate_calls = sum(count - 1 for count in seen_calls.values()
                          if count > 1)
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
        "mcp_errors": mcp_errors,
        "hook_denials": hook_denials,
        "mcp_usage_skill_calls": skill_calls,
        "duplicate_calls": duplicate_calls,
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
            "mcp_errors": summary["mcp_errors"],
            "hook_denials": summary["hook_denials"],
            "error_signatures": summary["error_signatures"],
            "test_runs": summary["test_runs"],
            "edits": summary["edits"],
            "smoke_runs": summary["smoke_runs"],
        })
    return {"source": source, "main": main, "subagents": subagents}


def _count_timeouts(lowered: str) -> int:
    # "timed out" ("Command timed out after 2m") не содержит "таймаут",
    # поэтому по сигнатурам каждое совпадение считается не более одного раза.
    return lowered.count("timeout") + lowered.count("таймаут") + lowered.count("timed out")


def aggregate_environment(task_metrics: list[dict]) -> dict:
    signatures: Counter = Counter()
    tool_errors = 0
    mcp_errors = 0
    hook_denials = 0
    for task in task_metrics:
        transcript = task.get("transcript") if isinstance(task, dict) else None
        if not isinstance(transcript, dict):
            continue
        agents = []
        main = transcript.get("main")
        if isinstance(main, dict):
            agents.append(main)
        subagents = transcript.get("subagents")
        if isinstance(subagents, list):
            agents.extend(item for item in subagents if isinstance(item, dict))
        for agent in agents:
            tool_errors += int(agent.get("tool_errors") or 0)
            mcp_errors += int(agent.get("mcp_errors") or 0)
            hook_denials += int(agent.get("hook_denials") or 0)
            for item in agent.get("error_signatures") or []:
                if not isinstance(item, dict):
                    continue
                signatures[str(item.get("signature"))] += int(item.get("count") or 0)
    lowered = "\n".join(signatures.elements()).lower()
    return {
        "tool_errors": tool_errors,
        "error_signatures": [
            {"signature": signature, "count": count}
            for signature, count in signatures.most_common(10)],
        "command_not_found": lowered.count("command not found"),
        "timeouts": _count_timeouts(lowered),
        "mcp_errors": mcp_errors,
        "hook_denials": hook_denials,
    }


_VERDICT_RE = re.compile(r"\|\s*Вердикт\s*\|\s*([^|]+?)\s*\|")


def _parse_iso(value) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
    return _parse_timestamp(value)


# Виды архивных итераций — префиксы имён `REVIEW|TESTING|TESTS|DEVELOP.<N>.md`.
_ARCHIVE_KINDS = ("review", "testing", "tests", "develop")

# Статусы, при которых этап ещё не начинался: итерация не считается.
_NOT_STARTED = ("pending", "skipped")


def _span_sec(started_at, finished_at) -> float | None:
    """Секунды между отметками; нет последней или отметки битые — ``None``."""
    started = _parse_iso(started_at)
    finished = _parse_iso(finished_at)
    if started is None or finished is None:
        return None
    return (finished - started).total_seconds()


def _as_int(value, default: int = 1) -> int:
    """Толерантный int: ``"2"``/``2.0``/``"2.0"`` → 2, мусор → ``default``.

    Метрики не должны падать целиком из-за одного битого поля ``iteration``.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _stage_iteration(task_json: dict, name: str) -> int:
    """Текущая итерация этапа; 0, если этап не проводился.

    Не проводился — этапа нет, он выключен (``enabled=false``) или его статус
    ``pending``/``skipped``/пустой. Иначе — поле ``iteration`` (по умолчанию 1).
    """
    stage = _find_stage(task_json, name)
    if not stage or not stage.get("enabled"):
        return 0
    if stage.get("status") is None or stage.get("status") in _NOT_STARTED:
        return 0
    return _as_int(stage.get("iteration"))


def _task_log_dirs(project_dir: Path, task) -> list[Path]:
    """Каталоги логов задачи: по id, identifier и фактической папке."""
    logs = project_dir / "logs"
    raw = task.raw if isinstance(getattr(task, "raw", None), dict) else {}
    task_id = raw.get("id")
    identifier = str(getattr(task, "identifier", "") or "").lstrip("#")
    folder = str(getattr(task, "folder", "") or "")
    candidates = []
    if identifier:
        candidates += [logs / f"task#{identifier}", logs / f"task##{identifier}"]
    if folder:
        candidates.append(logs / folder)
    if isinstance(task_id, int) and not isinstance(task_id, bool):
        candidates += [logs / f"task#{task_id}", logs / f"task##{task_id}"]
    seen = set()
    result = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def collect_task_state(project_dir: Path, task) -> dict:
    """Собрать состояние каталога задачи для метрик bench-отчёта.

    Возвращает словарь с ключами:
      - ``files`` — имена файлов каталога задачи (кроме ``task.json``,
        ``TASK.md`` и ``*.lock``);
      - ``verdicts`` — ``{"TESTING.md"|"REVIEW.md": вердикт}`` из таблицы;
      - ``archives`` — архивные итерации ``REVIEW|TESTING|TESTS|DEVELOP.<N>.md``;
      - ``archives_by_kind`` — те же архивы по видам (префикс до точки):
        ``review``, ``testing``, ``tests``, ``develop``;
      - ``test_results`` — payload-ы ``result.json`` текущей задачи
        (из каталогов по id, identifier и папке задачи без дублей;
        логи других задач не читаются).
    """
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
    archives_by_kind = {kind: [] for kind in _ARCHIVE_KINDS}
    for name in archives:
        archives_by_kind[name.split(".", 1)[0].lower()].append(name)
    test_results = []
    seen = set()
    for log_dir in _task_log_dirs(project_dir, task):
        result_path = log_dir / "result.json"
        if not result_path.is_file():
            continue
        resolved = result_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            # 1С пишет result.json с UTF-8 BOM (run-tests.py читает его так же).
            data = json.loads(result_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            test_results.append(data)
    return {"files": files, "verdicts": verdicts, "archives": archives,
            "archives_by_kind": archives_by_kind,
            "test_results": test_results}


def _runs(stage: dict) -> list[dict]:
    """Нормализованная история прогонов этапа (`runs[]` в task.json)."""
    runs = []
    for run in stage.get("runs") or []:
        if not isinstance(run, dict):
            continue
        runs.append({
            "iteration": _as_int(run.get("iteration")),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "duration_sec": _span_sec(run.get("started_at"),
                                      run.get("finished_at")),
        })
    return runs


def _runs_total_sec(runs: list[dict]) -> float | None:
    """Сумма длительностей завершённых прогонов; нет ни одного — ``None``."""
    completed = [run["duration_sec"] for run in runs
                 if run.get("duration_sec") is not None]
    return sum(completed) if completed else None


def stage_table(task_json: dict) -> list[dict]:
    stages = []
    for stage in task_json.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        duration = _span_sec(stage.get("started_at"), stage.get("finished_at"))
        runs = _runs(stage)
        total = _runs_total_sec(runs)
        stages.append({
            "name": stage.get("name"),
            "enabled": bool(stage.get("enabled")),
            "status": stage.get("status"),
            "iteration": _as_int(stage.get("iteration")),
            # Длительность последней итерации — для совместимости.
            "duration_sec": duration,
            # Сумма по runs[]; без runs — длительность этапа целиком.
            "duration_sec_total": total if total is not None else duration,
            "runs": runs,
            "changed_files": list(stage.get("changed_files") or []),
        })
    return stages


def _find_stage(task_json: dict, name: str) -> dict:
    for stage in task_json.get("stages") or []:
        if isinstance(stage, dict) and stage.get("name") == name:
            return stage
    return {}


def cycle_metrics(task_json: dict, state: dict, transcript: dict) -> dict:
    agents = [transcript.get("main") or {}]
    agents += [item for item in (transcript.get("subagents") or [])
               if isinstance(item, dict)]
    test_runs = sum(int(agent.get("test_runs") or 0) for agent in agents)
    smoke_runs = sum(int(agent.get("smoke_runs") or 0) for agent in agents)
    test_edits = 0
    for agent in agents:
        for path, count in (agent.get("edits") or {}).items():
            if "ЮнитТесты" in path and "/src/cfe/" in f"/{path}":
                test_edits += int(count)
    by_kind = state.get("archives_by_kind") or {}
    return {
        "tests_iteration": _stage_iteration(task_json, "tests"),
        "review_iteration": _stage_iteration(task_json, "review"),
        "review_archives": len(by_kind.get("review") or []),
        "develop_archives": len(by_kind.get("develop") or []),
        "testing_archives": len(by_kind.get("testing") or []),
        "tests_archives": len(by_kind.get("tests") or []),
        "test_runs": test_runs,
        "smoke_runs": smoke_runs,
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
    stdin_kwargs = ({"input": stdin_text} if stdin_text is not None
                    else {"stdin": subprocess.DEVNULL})
    try:
        proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=180, **stdin_kwargs)
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
    node_available = shutil.which("node") is not None
    query_result = {
        "available": extract_script.is_file() and query_script.is_file(),
        "skipped": None if extract_script.is_file() and query_script.is_file()
        else "analyze_query.py/extract_queries.py не найден",
        "ast": {"available": node_available,
                "reason": None if node_available else "node не найден в PATH"},
        "partial": False,
        "results": {},
    }
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
            ast_skipped = ("структурные (AST) проверки ПРОПУЩЕНЫ" in output
                           or "AST недоступен" in output)
            query_result["results"][key] = {
                "returncode": analyzed["returncode"],
                "findings": _findings(analyzed["stdout"]),
                "output_path": str(output_path),
                "extract_returncode": extracted["returncode"],
                "warnings": (extracted["stderr"] + analyzed["stderr"]).strip()[:1000],
                "ast_skipped": ast_skipped,
            }
            if ast_skipped:
                query_result["partial"] = True
    if not node_available and query_result["results"]:
        query_result["partial"] = True
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


def _seconds(value) -> str:
    if value is None:
        return "—"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if value >= 60:
        return f"{value / 60:.1f} мин"
    return f"{value:.0f} с"


def _opt(value) -> str:
    return "—" if value is None else str(value)


def _cell(value) -> str:
    """Ячейка markdown-таблицы: переводы строк в пробелы, `|` экранируется."""
    text = "—" if value is None else str(value)
    return text.replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")


def _review_cell(task: dict, cycles: dict) -> str:
    """Ячейка «Ревью»: ревью не начиналось — не показываем фиктивные числа."""
    stage = next((item for item in task.get("stages") or []
                  if item.get("name") == "review"), None)
    if not stage or not stage.get("enabled") or (
            stage.get("status") is None or stage.get("status") in _NOT_STARTED):
        return "ревью не проводилось"
    return (f"итераций {cycles.get('review_iteration', 0)}, "
            f"архивов {cycles.get('review_archives', 0)}")


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
        cells = [
            task.get("folder"),
            f"{task.get('limit_minutes')} мин",
            task.get("outcome"),
            _seconds(task.get("duration_sec")),
            stages or "—",
            (f"запусков {cycles.get('test_runs', 0)}, "
             f"смоуков {cycles.get('smoke_runs', 0)}, "
             f"правок тестов {cycles.get('test_module_edits', 0)}"),
            _review_cell(task, cycles),
        ]
        lines.append("| " + " | ".join(_cell(cell) for cell in cells) + " |")
    for task in metrics.get("tasks") or []:
        lines += ["", f"## {task.get('folder')}", ""]
        if task.get("outcome") != "success":
            lines.append(f"- ⚠ результаты задачи недостоверны: исход "
                         f"{task.get('outcome')} — артефакты и анализаторы "
                         f"могут быть неполными")
            lines.append("")
        exit_code = task.get("exit_code")
        lines.append(f"- Исход: `{task.get('outcome')}`, код выхода: "
                     f"`{'—' if exit_code is None else exit_code}`, время: "
                     f"{_seconds(task.get('duration_sec'))}")
        index_status = task.get("index_refresh")
        if index_status:
            lines.append(f"- Индекс code_index: `{index_status}`")
        stream = task.get("stream") or {}
        session = stream.get("session_id")
        lines.append(f"- Агент: turns={stream.get('num_turns')}, "
                     f"session={_opt(session)}")
        has_sendmessage = stream.get("has_sendmessage")
        lines.append("- SendMessage: " + (
            "—" if has_sendmessage is None
            else ("да" if has_sendmessage else "нет")))
        transcript = task.get("transcript") or {}
        main = transcript.get("main") or {}
        lines.append(f"- Источник транскрипта: {transcript.get('source', '—')}, "
                     f"ошибок инструментов: {main.get('tool_errors', 0)}")
        if main.get("tools"):
            lines.append("- Инструменты: " + ", ".join(
                f"{name}={count}" for name, count in
                sorted(main["tools"].items())))
        skill_calls = int(main.get("mcp_usage_skill_calls") or 0)
        lines.append(f"- Skill mcp-usage: {'да' if skill_calls else 'нет'} "
                     f"({skill_calls})")
        duplicates = int(main.get("duplicate_calls") or 0)
        if duplicates:
            lines.append(f"- Повторных вызовов инструментов: {duplicates}")
        if main.get("slow_ops"):
            lines += ["", "### Долгие операции", "",
                      "| Инструмент | Вход | Длительность |", "|---|---|---|"]
            for op in main["slow_ops"]:
                lines.append(f"| {_cell(op.get('tool'))} | "
                             f"`{_cell(op.get('input'))}` | "
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
        analyzers = task.get("analyzers")
        lines += ["", "### Анализаторы", ""]
        if not analyzers:
            lines.append("- анализаторы не запускались")
            continue
        code = analyzers.get("code_analyze") or {}
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
        if query.get("partial"):
            lines.append("- ⚠ query-analyze: структурные (AST) проверки "
                         "пропущены — результаты неполные "
                         "(установите Node.js)")
        for path, result in (query.get("results") or {}).items():
            findings = result.get("findings") or {}
            lines.append(f"  - `{Path(path).name}`: error={findings.get('error', 0)}, "
                         f"warning={findings.get('warning', 0)}, "
                         f"info={findings.get('info', 0)}")
            warnings = (result.get("warnings") or "").strip()
            if warnings:
                lines.append(f"  - warnings: `{_cell(warnings[:300])}`")
            extract_code = result.get("extract_returncode")
            if extract_code not in (0, None):
                lines.append(f"  - ⚠ extract_queries вернул код {extract_code} — "
                             f"запрос мог не проверяться "
                             f"(предупреждения выше)")
    env = metrics.get("environment") or {}
    lines += ["", "## Окружение", "",
              f"- Ошибок инструментов: {env.get('tool_errors', 0)} "
              f"(MCP: {env.get('mcp_errors', 0)}, "
              f"хуки: {env.get('hook_denials', 0)}, "
              f"прочие: {max(0, int(env.get('tool_errors', 0)) - int(env.get('mcp_errors', 0)) - int(env.get('hook_denials', 0)))})",
              f"- «command not found»: {env.get('command_not_found', 0)}",
              f"- Таймаутов: {env.get('timeouts', 0)}",
              f"- Ошибок MCP: {env.get('mcp_errors', 0)}",
              f"- Отказов хуков: {env.get('hook_denials', 0)}"]
    for item in env.get("error_signatures") or []:
        lines.append(f"- ×{item.get('count')}: {item.get('signature')}")
    return "\n".join(lines).rstrip() + "\n"
