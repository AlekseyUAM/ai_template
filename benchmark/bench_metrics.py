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
