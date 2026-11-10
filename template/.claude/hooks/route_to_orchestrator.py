#!/usr/bin/env python
"""UserPromptSubmit-хук: задачи вида tasks/task# (на Windows — tasks\\task#)
маршрутизируются оркестратору."""
import json
import re
import sys

# Разделитель в пути зависит от ОС: пользователь на Windows наберёт `tasks\task#`.
_TASK_PROMPT_RE = re.compile(r"tasks[\\/]task#")


def build_output(event: dict) -> dict:
    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return {}
    if _TASK_PROMPT_RE.search(prompt):
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[ai1c] Это выполнение задачи. Действуй как оркестратор: следуй "
                "навыку task-orchestration, веди этапы из task.json и делегируй "
                "субагентам (analyst/architect/developer-tests/developer/"
                "reviewer/technical-writer). Этап testing оркестратор ведёт сам: "
                "прогоняет тесты и выносит вердикт в TESTING.md (субагента нет)."),
        }}
    return {}


def main() -> None:
    # Хук не должен блокировать отправку промпта: любая ошибка разбора/вывода
    # трактуется как «нет дополнительного контекста», exit 0.
    try:
        event = json.load(sys.stdin)
        out = build_output(event) if isinstance(event, dict) else {}
        if out:
            json.dump(out, sys.stdout, ensure_ascii=False)
    except Exception:
        return


if __name__ == "__main__":
    main()
