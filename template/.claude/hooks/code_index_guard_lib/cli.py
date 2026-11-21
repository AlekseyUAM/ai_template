"""Hook CLI contract: pure run/render and fail-safe main."""
import hashlib
import json
import sys
from pathlib import Path

from .context import GuardContext

_STATE_NAME = "code-index-guard.state.json"


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
            # Command without a decision in Bash grammar: on Windows the harness
            # passes to Bash what actually is PowerShell - parse it again
            # as PowerShell, dropping heredoc bodies (they are DATA).
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


def _state_path() -> Path:
    """Deny counter file next to the guard config (in the hooks directory)."""
    from .config import guard_config_path
    return guard_config_path().with_name(_STATE_NAME)


def _session_id(payload) -> str:
    value = payload.get("session_id")
    return value if isinstance(value, str) else ""


def _call_key(payload) -> str:
    """Call key: tool + hash of the significant part of tool_input.

    For Read the key is only `file_path` (repeated reads of different ranges
    of one file count as one call), for Grep/Glob - path/pattern,
    for commands - the command itself. So the deny limit cannot be bypassed by
    changing `offset`/`limit` or formatting.
    """
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    if tool == "Read":
        key_input = {"file_path": ti.get("file_path")}
    elif tool in ("Grep", "Glob"):
        key_input = {k: ti.get(k) for k in ("path", "pattern", "glob")
                     if k in ti}
    elif tool in ("Bash", "PowerShell"):
        key_input = {"command": ti.get("command")}
    else:
        key_input = ti
    raw = json.dumps(key_input, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()
    return f"{tool}:{digest}"


def _load_state(path: Path, session: str) -> dict:
    """Current session state; counters reset when the session changes."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict) or data.get("session_id") != session:
        return {"session_id": session, "entries": {}}
    entries = data.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    return {"session_id": session, "entries": entries}


def _save_state(path: Path, state: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(state, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _apply_deny_limit(payload, decision, max_denies):
    """Allows the native call after N consecutive denials - loop protection.

    A local model may stubbornly repeat Read/Grep on an indexed path.
    The counter lives in a file next to the config and resets when session_id changes;
    state errors do not change the decision (the guard keeps working as before).
    """
    if decision is None or decision.allow or max_denies <= 0:
        return decision
    try:
        from .decisions import Decision
        path = _state_path()
        session = _session_id(payload)
        state = _load_state(path, session)
        entries = state["entries"]
        key = _call_key(payload)
        count = int(entries.get(key) or 0) + 1
        entries[key] = count
        _save_state(path, state)
        if count > max_denies:
            return Decision(
                True,
                f"code-index-guard: this call already had {max_denies} "
                "denials - allowing the native tool to avoid a loop. "
                "Prefer code_index from now on; the repository alias is in the text "
                "of the previous deny messages.")
        return decision
    except Exception:
        return decision


def main(argv=None):
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        list_roots, prefix = parse_args(args)
        ctx = build_context()
        if list_roots:
            return  # v1 mode is not implemented: empty stdout
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        decision = _apply_deny_limit(
            payload, run(payload, ctx, prefix),
            getattr(ctx.config, "max_denies", 0))
        out = render(decision)
        if out:
            print(out)
    except Exception:
        return
