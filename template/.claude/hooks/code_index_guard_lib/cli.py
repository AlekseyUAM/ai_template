"""CLI-контракт хука. Полный контракт (run/render, журнал) — Task 8."""
import json
import sys

from . import bash, decisions, tools
from .config import indexed_paths, load_guard_config
from .context import GuardContext


def build_context() -> GuardContext:
    from .paths import default_case_insensitive
    ci = default_case_insensitive()
    cfg = load_guard_config()
    return GuardContext(cfg, indexed_paths(cfg, case_insensitive=ci), ci)


def parse_args(argv):
    list_roots = False
    prefix = None
    i = 0
    while i < len(argv):
        if argv[i] == "--list-roots":
            list_roots = True
        elif argv[i] == "--mcp-prefix" and i + 1 < len(argv):
            i += 1
            prefix = argv[i]
        i += 1
    return list_roots, prefix


def emit(decision) -> None:
    hs = {"hookEventName": "PreToolUse",
          "permissionDecision": "allow" if decision.allow else "deny"}
    if decision.reason:
        hs["permissionDecisionReason"] = decision.reason
    print(json.dumps({"hookSpecificOutput": hs}, ensure_ascii=False))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    list_roots, prefix = parse_args(args)
    try:
        ctx = build_context()
        tools.set_prefix(prefix or ctx.config.mcp_prefix)
        if list_roots:
            return  # режим v1 не реализован: пустой stdout
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        tool = payload.get("tool_name")
        ti = payload.get("tool_input") or {}
        cwd = payload.get("cwd")
        d = None
        if tool == "Read":
            d = decisions.decide_read(ti, ctx)
        elif tool == "Grep":
            d = decisions.decide_grep(ti, cwd, ctx)
        elif tool == "Glob":
            d = decisions.decide_glob(ti, cwd, ctx)
        elif tool == "Bash":
            d = bash.decide_bash(ti, cwd, ctx)
        if d is not None:
            emit(d)
    except Exception:
        return
