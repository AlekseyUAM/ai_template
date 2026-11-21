#!/usr/bin/env python
"""UserPromptSubmit-хук: задача tasks/task#<id> переводится в single-agent режим.

Хук читает task.json и перечисляет включённые этапы как чеклисты. Никакой
передачи управления субагентам: всё выполняет основной поток.
"""
import json
import os
import re
import sys
from pathlib import Path

# Разделитель в пути зависит от ОС: пользователь на Windows наберёт `tasks\task#`.
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
                  else "ведёт сам исполнитель")
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
            f"[ai1c] Stage-scoped режим: выполняется ТОЛЬКО этап «{stage_filter}».",
            f"Задача tasks/{folder}. Не начинай следующие этапы; после артефакта и "
            "статуса done остановись.",
            f"Работай по tasks/{folder}/TASK.md, изменения — в src/cf/**; артефакты — "
            "в каталоге задачи; `.claude/**` — только читай.",
            "Python — интерпретатор `.venv` проекта; создание объектов — навык "
            "`meta-compile` (подсистема — `subsystem-compile`, роль — `role-compile`), "
            "не `meta-add`/`subsystem-add`.",
        ]
        if lines:
            parts.append("Чеклист этапа:")
            parts.extend(lines)
        else:
            parts.append(
                f"Этап «{stage_filter}» не найден в task.json — проверь TASK_STAGE.")
        parts.append(
            "Правило: .claude/rules/single-agent-workflow.md, раздел stage-scoped.")
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(parts),
        }}

    parts = [
        "[ai1c] Single-agent режим: не вызывай Agent/Task; работай по правилу "
        "single-agent-workflow.",
        f"Задача tasks/{folder}: этапы-чеклисты выполняй сам, по порядку, в этом потоке.",
        f"Работай по tasks/{folder}/TASK.md, изменения — в src/cf/**; `.claude/**` — "
        "инструменты и чеклисты, только читай, не меняй.",
        "Python — интерпретатор `.venv` проекта; создание объектов — навык `meta-compile` "
        "(подсистема — `subsystem-compile`, роль — `role-compile`), не `meta-add`/"
        "`subsystem-add`.",
    ]
    if lines:
        parts.append("Чеклисты:")
        parts.extend(lines)
    else:
        parts.append(
            "Не удалось прочитать task.json — открой его и пройди enabled-этапы "
            "по правилу single-agent-workflow.")
    parts.append("Правило: .claude/rules/single-agent-workflow.md.")
    return {"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n".join(parts),
    }}


def main() -> None:
    # Хук не должен блокировать отправку промпта: любая ошибка разбора/вывода
    # трактуется как «нет дополнительного контекста», exit 0.
    try:
        event = json.load(sys.stdin)
        out = build_output(event) if isinstance(event, dict) else {}
        if out:
            # ensure_ascii=True: stdout хука на Windows может быть cp1251,
            # а в тексте есть символы вне неё (например, «→»).
            json.dump(out, sys.stdout, ensure_ascii=True)
    except Exception:
        return


if __name__ == "__main__":
    main()
