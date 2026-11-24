import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks" / "bsl_nudge.py"


def _load():
    spec = importlib.util.spec_from_file_location("bsl_nudge", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_tool(calls=None):
    def fake(script, args, stdin=None):
        if calls is not None:
            calls.append((script.name, list(args), stdin))
        if script.name == "analyze_code.py":
            return "warning | some-rule | строка 1 | нарушение", 0
        if script.name == "check_event_handlers.py":
            return ("error | event-handler-params | строка 2 | "
                    "правильная сигнатура: Процедура Тест(Отказ)"), 1
        if script.name == "extract_queries.py":
            return "ВЫБРАТЬ 1", 0
        if script.name == "analyze_query.py":
            return "info | query-rule | строка 1 | замечание", 0
        if script.name == "check_metadata_names.py":
            return "error | reserved-system-name | file:1 | имя занято", 1
        return "", 0
    return fake


BSL = "/p/src/cf/Documents/Заказ/Ext/ObjectModule.bsl"


def test_bsl_edit_runs_all_analyzers(monkeypatch):
    mod = _load()
    calls = []
    monkeypatch.setattr(mod, "_run_tool", _fake_tool(calls))
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": BSL}})
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "mcp__bsl_ls__check" in text
    assert "analyze_code.py" in text
    assert "check_event_handlers.py" in text
    assert "query-analyze" in text
    assert "Findings: error=1, warning=1, info=1." in text
    assert [c[0] for c in calls] == [
        "analyze_code.py", "check_event_handlers.py",
        "extract_queries.py", "analyze_query.py"]


def test_bsl_without_queries_skips_query_analyzer(monkeypatch):
    mod = _load()
    calls = []

    def no_queries(script, args, stdin=None):
        calls.append(script.name)
        return ("", 0) if script.name == "extract_queries.py" else ("", 0)

    monkeypatch.setattr(mod, "_run_tool", no_queries)
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": BSL}})
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "query-analyze" in text and "(no queries)" in text
    assert "analyze_query.py" not in calls


def test_xml_edit_nudges_metadata_names(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_run_tool", _fake_tool())
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": "/p/src/cf/Catalogs/X.xml"}})
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "check_metadata_names.py --changed" in text
    assert "Findings: error=1, warning=0, info=0." in text


def test_bash_meta_command_nudges_metadata_names(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_run_tool", _fake_tool())
    out = mod.build_output({
        "tool_name": "Bash",
        "tool_input": {"command": "python .claude/tools/meta-compile.py ..."},
    })
    text = out["hookSpecificOutput"]["additionalContext"]
    assert "check_metadata_names.py --changed" in text


def test_bom_hint_present(monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "_run_tool", _fake_tool())
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": BSL}})
    assert ("BOM: no manual check - the server strips a leading UTF-8 BOM."
            in out["hookSpecificOutput"]["additionalContext"])


def test_non_bsl_is_silent():
    mod = _load()
    assert mod.build_output({"tool_input": {"file_path": "/p/readme.md"}}) == {}


def test_missing_input_is_silent():
    mod = _load()
    assert mod.build_output({}) == {}


def test_bad_tool_input_does_not_crash(monkeypatch):
    import io
    mod = _load()
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO('{"tool_input": 42}'))
    monkeypatch.setattr(mod.sys, "stdout", io.StringIO())
    mod.main()
    assert mod.sys.stdout.getvalue() == ""


def test_broken_json_does_not_crash(monkeypatch):
    import io
    mod = _load()
    monkeypatch.setattr(mod.sys, "stdin", io.StringIO("{not json"))
    monkeypatch.setattr(mod.sys, "stdout", io.StringIO())
    mod.main()
    assert mod.sys.stdout.getvalue() == ""
