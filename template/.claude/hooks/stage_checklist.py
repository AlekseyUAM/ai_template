#!/usr/bin/env python
"""PostToolUse hook: inject the stage checklist when a task stage starts.

The model calls `task_status.py tasks/task#<id> <stage> running` at the
boundary between stages. That is the moment when the stage checklist must be
fresh in context. A copy read at the start of a long single-session task loses
salience; a path alone is easy to skip. The hook therefore injects the full
checklist text (capped) right after the status command.

In stage-scoped mode (`TASK_STAGE` is set) the stage prompt already names the
checklist and the process starts with a clean context, so the hook stays
silent to avoid a duplicate injection.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MAX_CHARS = 40000
_SINGLE_AGENT_RULE = Path(".claude") / "rules" / "single-agent-workflow.md"
_STAGE_STATUS_RE = re.compile(
    r"task_status\.py\s+\S+\s+(\w+)\s+running\b")
# task##001 — каталог задачи с identifier="#001": task_folder_name клеит
# "task#" + identifier, поэтому решёток может быть две.
_TASK_FOLDER_RE = re.compile(r"tasks[\\/](task#+\d+)", re.IGNORECASE)


def _project_root(event: dict, override: Path | None) -> Path | None:
    if override is not None:
        return override
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return Path(cwd)
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path.cwd()


def _load_task(task_dir: Path) -> dict | None:
    try:
        data = json.loads((task_dir / "task.json").read_text(
            encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _find_stage(data: dict, name: str) -> dict | None:
    for stage in data.get("stages") or []:
        if isinstance(stage, dict) and stage.get("name") == name:
            return stage
    return None


def _context(text: str) -> dict:
    return {"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": text,
    }}


def _warning(text: str) -> dict:
    return _context(f"[ai1c] {text}")


def _render(stage: str, artifact: str, checklist: str, content: str) -> dict:
    head = "\n".join([
        f'[ai1c] Stage "{stage}" started. The stage checklist is injected below.',
        "This is a deliberate re-read at the stage boundary: do not rely on the",
        "copy read at the start of the task. Work through every item before",
        "starting the next stage.",
        f"Artifact: {artifact or '-'}",
        f"Checklist: {checklist}",
        "---",
    ])
    text = head + "\n" + content
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + (
            f"\n[checklist truncated at {MAX_CHARS} chars; "
            f"read {checklist} for the rest]")
    return _context(text)


def build_output(event: dict, project_root: Path | None = None) -> dict:
    """Return the PostToolUse payload for a stage-start command, or {}."""
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return {}
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    command = tool_input.get("command")
    if not isinstance(command, str) or "task_status.py" not in command:
        return {}

    stages = _STAGE_STATUS_RE.findall(command)
    if not stages:
        return {}
    stage_name = stages[-1]

    folders = _TASK_FOLDER_RE.findall(command)
    if not folders:
        return {}
    folder = folders[-1]

    # In stage-scoped mode the stage prompt already contains the checklist.
    if os.environ.get("TASK_STAGE"):
        return {}

    root = _project_root(event, project_root)
    if root is None:
        return {}
    task_dir = root / "tasks" / folder
    data = _load_task(task_dir)
    if data is None:
        return _warning(
            f'Stage "{stage_name}" started, but {task_dir / "task.json"} '
            "was not found. Open the stage checklist before continuing.")

    stage = _find_stage(data, stage_name)
    if stage is None:
        return _warning(
            f'Stage "{stage_name}" started, but it is not found in '
            f'{task_dir / "task.json"}. Open the stage checklist before '
            "continuing.")

    subagent = str(stage.get("subagent") or "").strip()
    artifact = str(stage.get("artifact") or "").strip()
    rel = (Path(".claude") / "checklists" / f"{subagent}.md"
           if subagent else _SINGLE_AGENT_RULE)
    checklist = rel.as_posix()
    try:
        content = (root / rel).read_text(encoding="utf-8-sig")
    except OSError:
        return _warning(
            f'Stage "{stage_name}" started, but the checklist {checklist} '
            "was not found. Open the stage checklist before continuing.")
    return _render(stage_name, artifact, checklist, content)


def main() -> None:
    try:
        event = json.load(sys.stdin)
        out = build_output(event) if isinstance(event, dict) else {}
        if out:
            json.dump(out, sys.stdout, ensure_ascii=False)
    except Exception:
        return


if __name__ == "__main__":
    main()
