#!/usr/bin/env python
"""PostToolUse hook: runs the mandatory analyzers after edits and injects findings.

The hook is the enforcement point: after a `.bsl`/metadata XML edit (and after
`meta-*` Bash commands) it runs the required Python analyzers itself and returns
their output as `additionalContext`. The agent sees the findings immediately and
does not need a long checklist to remember the commands.

Layers:
- `.bsl` - `code-analyze` (`analyze_code.py` + `check_event_handlers.py`) and,
  when the module contains queries, `query-analyze` (`extract_queries.py` +
  `analyze_query.py`);
- metadata XML / `meta-*` commands - `check_metadata_names.py --changed`;
- `bsl_ls` is an MCP call and remains a separate mandatory step (reminder only).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CLAUDE_DIR = Path(__file__).resolve().parents[1]
CODE_SCRIPTS = CLAUDE_DIR / "skills" / "code-analyze" / "scripts"
QUERY_SCRIPTS = CLAUDE_DIR / "skills" / "query-analyze" / "scripts"
ANALYZE_CODE = CODE_SCRIPTS / "analyze_code.py"
CHECK_EVENTS = CODE_SCRIPTS / "check_event_handlers.py"
CHECK_METADATA = CODE_SCRIPTS / "check_metadata_names.py"
EXTRACT_QUERIES = QUERY_SCRIPTS / "extract_queries.py"
ANALYZE_QUERY = QUERY_SCRIPTS / "analyze_query.py"

ANALYZER_TIMEOUT = 60
MAX_CHARS = 6000
_META_COMMANDS = ("meta-compile", "meta-edit", "subsystem-compile", "role-compile")
_FINDING_RE = re.compile(r"^(error|warning|info)\s*\|", re.I)


def _paths(tool_input: dict) -> list:
    out = []
    for key in ("file_path", "path", "notebook_path"):
        val = tool_input.get(key)
        if isinstance(val, str):
            out.append(val)
    return out


def _norm(path: str) -> str:
    return path.replace("\\", "/").lower()


def _in_src(path: str) -> bool:
    low = "/" + _norm(path)
    return "/src/cf/" in low or "/src/cfe/" in low


def _is_form_or_template(path: str) -> bool:
    low = _norm(path)
    return "/forms/" in low or "/templates/" in low or "/commonforms/" in low


def _is_metadata_xml(path: str) -> bool:
    return (path.lower().endswith(".xml") and _in_src(path)
            and not _is_form_or_template(path))


def _run(cmd, **kwargs):
    """subprocess.run wrapper; tests monkeypatch it."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=ANALYZER_TIMEOUT, **kwargs)


def _run_tool(script: Path, args: list, stdin: str | None = None):
    """Run one analyzer; return (text, returncode)."""
    if not script.is_file():
        return f"[analyzer not found: {script.name}]", 127
    try:
        proc = _run([sys.executable, str(script), *args], input=stdin)
    except subprocess.TimeoutExpired:
        return f"[analyzer timeout: {script.name}]", 1
    except Exception as exc:  # noqa: BLE001 - hook must never break the edit
        return f"[analyzer failed: {script.name}: {exc}]", 1
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    text = out
    if err:
        text = (text + "\n" + err).strip() if text else err
    return text, getattr(proc, "returncode", 0)


def _has_findings(text: str) -> bool:
    """True if the layer output must be shown (findings or an analyzer error)."""
    if not text:
        return False
    if text.startswith("[analyzer") or "Traceback" in text or "Не удалось" in text:
        return True
    return any(_FINDING_RE.match(line.strip()) for line in text.splitlines())


def _analyze_bsl(path: str) -> list[tuple[str, str]]:
    sections = [("analyze_code.py", _run_tool(ANALYZE_CODE, [path])[0])]

    if _in_src(path) and not _is_form_or_template(path):
        text, _rc = _run_tool(CHECK_EVENTS, [path])
        sections.append(("check_event_handlers.py", text))
    else:
        sections.append(("check_event_handlers.py (skipped: form/template)",
                         ""))

    q_text, q_rc = _run_tool(EXTRACT_QUERIES, ["-Path", path])
    if q_text and q_rc == 0:
        sections.append(("query-analyze",
                         _run_tool(ANALYZE_QUERY, ["-"], stdin=q_text)[0]))
    elif q_rc == 2:
        sections.append(("query-analyze",
                         q_text or "extract_queries: query not extracted (exit 2)"))
    else:
        sections.append(("query-analyze (no queries)", ""))
    return sections


def _analyze_metadata() -> list[tuple[str, str]]:
    text, _rc = _run_tool(CHECK_METADATA, ["--changed"])
    return [("check_metadata_names.py --changed", text)]


def _finding_counts(text: str) -> dict:
    counts = {"error": 0, "warning": 0, "info": 0}
    for line in text.splitlines():
        match = _FINDING_RE.match(line.strip())
        if match:
            counts[match.group(1).lower()] += 1
    return counts


def _hook_output(title: str, sections: list[tuple[str, str]],
                 footer: str) -> dict:
    body = "\n".join(f"== {name} ==\n{text}" for name, text in sections
                     if _has_findings(text))
    counts = _finding_counts("\n".join(text for _name, text in sections))
    names = ", ".join(name for name, _text in sections)
    summary = (f"Layers run: {names}. Findings: error={counts['error']}, "
               f"warning={counts['warning']}, info={counts['info']}.")
    text = (f"[ai1c] {title}. Mandatory analyzers ran automatically.\n"
            f"{summary}\n{body or '(no findings)'}\n{footer}\n"
            "Fix all error/warning before continuing; a skipped layer is a "
            "process defect.")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n[output truncated]"
    return {"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": text,
    }}


BSL_FOOTER = (
    "bsl_ls static analysis is still mandatory separately: MCP bsl_ls, "
    "mcp__bsl_ls__check, pass code+sha256. "
    "BOM: no manual check - the server strips a leading UTF-8 BOM."
)
METADATA_FOOTER = (
    "check_metadata_names.py --changed is mandatory for every metadata change; "
    "rename reserved-system-name findings before the IB load."
)


def build_output(event: dict) -> dict:
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    paths = _paths(tool_input)

    bsl = next((p for p in paths if p.lower().endswith(".bsl")), None)
    if bsl:
        return _hook_output(f"BSL module changed: {bsl}",
                            _analyze_bsl(bsl), BSL_FOOTER)

    xml = next((p for p in paths if _is_metadata_xml(p)), None)
    if xml:
        return _hook_output(f"Metadata XML changed: {xml}",
                            _analyze_metadata(), METADATA_FOOTER)

    command = tool_input.get("command")
    if (event.get("tool_name") == "Bash" and isinstance(command, str)
            and any(name in command.lower() for name in _META_COMMANDS)):
        return _hook_output("Metadata command finished",
                            _analyze_metadata(), METADATA_FOOTER)
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
