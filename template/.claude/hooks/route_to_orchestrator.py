#!/usr/bin/env python3
"""UserPromptSubmit-хук: задачи вида tasks/task# маршрутизируются оркестратору."""
import json
import sys


def build_output(event: dict) -> dict:
    prompt = event.get("prompt") or ""
    if "tasks/task#" in prompt:
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "[ai1c] Это выполнение задачи. Действуй как оркестратор: следуй "
                "навыку task-orchestration, веди этапы из task.json и делегируй "
                "субагентам (analyst/architect/developer/tester/reviewer)."),
        }}
    return {}


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    out = build_output(event)
    if out:
        json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
