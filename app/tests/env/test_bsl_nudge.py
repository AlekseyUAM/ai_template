import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks" / "bsl_nudge.py"


def _load():
    spec = importlib.util.spec_from_file_location("bsl_nudge", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bsl_edit_nudges():
    mod = _load()
    out = mod.build_output({"tool_name": "Edit",
                            "tool_input": {"file_path": "/p/Module.bsl"}})
    assert "mcp__bsl_ls__check" in out["hookSpecificOutput"]["additionalContext"]


def test_non_bsl_is_silent():
    mod = _load()
    assert mod.build_output({"tool_input": {"file_path": "/p/readme.md"}}) == {}


def test_missing_input_is_silent():
    mod = _load()
    assert mod.build_output({}) == {}
