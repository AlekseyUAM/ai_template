"""Чтение артефактов этапов задачи для показа в Telegram."""
import json
from pathlib import Path

from agentmon.env.task_schema import task_folder_name

TG_LIMIT = 4096


def chunk(text: str, limit: int = TG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:            # очень длинная строка — режем жёстко
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) > limit:
            parts.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        parts.append(buf)
    return parts


def _stages(task: dict) -> list[dict]:
    try:
        return json.loads(task.get("stages_json") or "[]")
    except (ValueError, TypeError):
        return []


def enabled_stages(task: dict) -> list[dict]:
    return [{"name": s["name"], "artifact": s.get("artifact")}
            for s in _stages(task) if s.get("enabled")]


def read_report(project_path: str, task: dict, stage_name: str) -> str | None:
    stage = next((s for s in _stages(task) if s.get("name") == stage_name), None)
    if not stage or not stage.get("artifact"):
        return None
    folder = task_folder_name(task["id"], task.get("identifier"))
    path = Path(project_path) / "tasks" / folder / stage["artifact"]
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
