#!/usr/bin/env python3
"""PostToolUse-хук: напоминает прогнать статанализ после правки *.bsl."""
import json
import sys


def _paths(tool_input: dict) -> list:
    out = []
    for key in ("file_path", "path", "notebook_path"):
        val = tool_input.get(key)
        if isinstance(val, str):
            out.append(val)
    return out


def build_output(event: dict) -> dict:
    tool_input = event.get("tool_input") or {}
    if any(p.lower().endswith(".bsl") for p in _paths(tool_input)):
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "[ai1c] Изменён BSL-модуль — прогони статический анализ "
                "(навык mcp-usage, MCP bsl_ls, инструмент mcp__bsl_ls__check)."),
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
