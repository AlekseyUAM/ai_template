"""CLI-контракт хука: чистые run/render и fail-safe main."""
import json
import sys

from .context import GuardContext


def build_context() -> GuardContext:
    from .config import indexed_paths, load_guard_config
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


def run(payload, ctx, prefix=None):
    from . import bash, decisions, powershell, shell, tools
    tools.set_prefix(prefix or ctx.config.mcp_prefix)
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    if tool == "Read":
        return decisions.decide_read(ti, ctx)
    if tool == "Grep":
        return decisions.decide_grep(ti, cwd, ctx)
    if tool == "Glob":
        return decisions.decide_glob(ti, cwd, ctx)
    if tool == "PowerShell":
        return powershell.decide_powershell(ti, cwd, ctx)
    if tool == "Bash":
        d = bash.decide_bash(ti, cwd, ctx)
        if d is None:
            # Команда без решения в Bash-грамматике: на Windows харнесс
            # передаёт в Bash то, что на деле PowerShell — разбираем повторно
            # как PowerShell, выкинув тела heredoc'ов (это ДАННЫЕ).
            cmd = ti.get("command") or ""
            d = powershell.decide_powershell(
                {"command": shell.strip_heredocs(cmd)}, cwd, ctx)
        return d
    return None


def render(decision):
    if decision is None:
        return None
    hs = {"hookEventName": "PreToolUse",
          "permissionDecision": "allow" if decision.allow else "deny"}
    if decision.reason:
        hs["permissionDecisionReason"] = decision.reason
    return json.dumps({"hookSpecificOutput": hs}, ensure_ascii=False)


def main(argv=None):
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        list_roots, prefix = parse_args(args)
        ctx = build_context()
        if list_roots:
            return  # режим v1 не реализован: пустой stdout
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        out = render(run(payload, ctx, prefix))
        if out:
            print(out)
    except Exception:
        return
