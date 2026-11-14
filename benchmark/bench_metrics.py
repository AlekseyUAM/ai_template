"""Метрики benchmark-прогона: stream-json, транскрипты, дайджест, анализаторы."""
from __future__ import annotations

import json
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
    matches = sorted(root.glob(f"*/{session_id}.jsonl"))
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
        signatures[line[:160]] += 1
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
