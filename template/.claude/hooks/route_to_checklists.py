#!/usr/bin/env python
"""UserPromptSubmit hook: task tasks/task#<id> is switched to single-agent mode.

The hook reads task.json and lists the enabled stages as checklists. No
handoff to subagents: everything is done by the main thread.
"""
import json
import os
import re
import sys
from pathlib import Path

# The path separator depends on the OS: a Windows user types `tasks\task#`.
_TASK_PROMPT_RE = re.compile(r"tasks[\\/](task#\d+)", re.IGNORECASE)


def _checklist_lines(task_dir: Path, only_stage: str | None = None) -> list[str]:
    try:
        data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    lines = []
    for stage in data.get("stages") or []:
        if not isinstance(stage, dict) or not stage.get("enabled"):
            continue
        name = stage.get("name") or "?"
        if only_stage and name != only_stage:
            continue
        subagent = stage.get("subagent") or ""
        artifact = stage.get("artifact") or ""
        target = (f".claude/checklists/{subagent}.md" if subagent
                  else "handled by the executor itself")
        suffix = f" → {artifact}" if artifact else ""
        lines.append(f"- {name}: {target}{suffix}")
    return lines


def build_output(event: dict) -> dict:
    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return {}
    match = _TASK_PROMPT_RE.search(prompt)
    if not match:
        return {}
    folder = match.group(1)
    raw_cwd = event.get("cwd")
    root = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    stage_filter = (os.environ.get("TASK_STAGE") or "").strip()
    lines = _checklist_lines(root / "tasks" / folder,
                             only_stage=stage_filter or None)
    if stage_filter:
        parts = [
            "[ai1c] First action before any tool call: invoke Skill mcp-usage.",
            f"[ai1c] Stage-scoped mode: ONLY stage '{stage_filter}' is executed.",
            f"Task tasks/{folder}. Do not start the following stages; after the artifact and "
            "status done, stop.",
            f"Work per tasks/{folder}/TASK.md, changes - in src/cf/**; artifacts - "
            "in the task directory; `.claude/**` - read only.",
            "Python - the project `.venv` interpreter; object creation - skill "
            "`meta-compile` (subsystem - `subsystem-compile`, role - `role-compile`), "
            "not `meta-add`/`subsystem-add`.",
        ]
        if lines:
            parts.append("Stage checklist:")
            parts.extend(lines)
        else:
            parts.append(
                f"Stage '{stage_filter}' not found in task.json - check TASK_STAGE.")
        parts.append(
            "Rule: .claude/rules/single-agent-workflow.md, stage-scoped section.")
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(parts),
        }}

    parts = [
        "[ai1c] First action before any tool call: invoke Skill mcp-usage.",
        "[ai1c] Single-agent mode: do not call Agent/Task; work per rule "
        "single-agent-workflow.",
        f"Task tasks/{folder}: execute the checklist stages yourself, in order, in this thread.",
        f"Work per tasks/{folder}/TASK.md, changes - in src/cf/**; `.claude/**` - "
        "tools and checklists, read only, do not modify.",
        "Python - the project `.venv` interpreter; object creation - skill `meta-compile` "
        "(subsystem - `subsystem-compile`, role - `role-compile`), not `meta-add`/"
        "`subsystem-add`.",
    ]
    if lines:
        parts.append("Checklists:")
        parts.extend(lines)
    else:
        parts.append(
            "Failed to read task.json - open it and go through the enabled stages "
            "per rule single-agent-workflow.")
    parts.append("Rule: .claude/rules/single-agent-workflow.md.")
    return {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n".join(parts),
    }}


def main() -> None:
    # The hook must not block prompt submission: any parse/output error is
    # treated as "no additional context", exit 0.
    try:
        event = json.load(sys.stdin)
        out = build_output(event) if isinstance(event, dict) else {}
        if out:
            # ensure_ascii=True: hook stdout on Windows may be cp1251,
            # and the text has characters outside it (e.g. «→»).
            json.dump(out, sys.stdout, ensure_ascii=True)
    except Exception:
        return


if __name__ == "__main__":
    main()
