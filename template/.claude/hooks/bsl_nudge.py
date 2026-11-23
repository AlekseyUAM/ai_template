#!/usr/bin/env python
"""PostToolUse hook: reminds to run static analysis after editing *.bsl."""
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
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    if any(p.lower().endswith(".bsl") for p in _paths(tool_input)):
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "[ai1c] BSL module changed - run static analysis "
                "(skill mcp-usage, MCP bsl_ls, mcp__bsl_ls__check): pass the module "
                "text as `code` together with `sha256` (`sha256sum <file>`); the "
                "trailing newline may be kept or dropped - both hashes are accepted. "
                "Use `file_path` only for paths mounted into the server container; "
                "in the standard Docker setup pass code+sha256. "
                "BOM: no manual check - the server strips a leading UTF-8 BOM."),
        }}
    return {}


def main() -> None:
    # A hook error must not break PostToolUse: exit silently with code 0.
    try:
        event = json.load(sys.stdin)
        out = build_output(event) if isinstance(event, dict) else {}
        if out:
            json.dump(out, sys.stdout, ensure_ascii=False)
    except Exception:
        return


if __name__ == "__main__":
    main()
