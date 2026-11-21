import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import cli, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_prefix():
    """cli.run выставляет процесс-глобальный tools._prefix — не протекаем."""
    saved = tools._prefix
    yield
    tools._prefix = saved


def test_read_deny_contract(tmp_path):
    root = build_repo(tmp_path)
    out = cli.render(cli.run(
        {"tool_name": "Read", "tool_input": {"file_path": str(root / "Cargo.toml")}},
        make_ctx(root)))
    data = json.loads(out)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert data["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_allow_has_no_reason(tmp_path):
    root = build_repo(tmp_path)
    out = cli.render(cli.run(
        {"tool_name": "Read",
         "tool_input": {"file_path": str(root / "Cargo.toml"),
                        "offset": 1, "limit": 1}},
        make_ctx(root)))
    hs = json.loads(out)["hookSpecificOutput"]
    assert hs["permissionDecision"] == "allow"
    assert "permissionDecisionReason" not in hs


def test_skip_renders_nothing(tmp_path):
    root = build_repo(tmp_path)
    assert cli.render(cli.run(
        {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "x")}},
        make_ctx(root))) is None


def test_unknown_tool_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert cli.run({"tool_name": "Edit", "tool_input": {}}, make_ctx(root)) is None


def test_broken_json_does_not_crash(monkeypatch, tmp_path):
    root = build_repo(tmp_path)
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.main([])
    assert out.getvalue() == ""


def test_config_less_hook_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"tool_name": "Grep", "tool_input": {"pattern": "x"}, "cwd": str(tmp_path)})))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.main([])
    assert out.getvalue() == ""


def test_mcp_prefix_cli_overrides(tmp_path):
    root = build_repo(tmp_path)
    ctx = make_ctx(root)
    d = cli.run({"tool_name": "Grep", "tool_input": {"pattern": "x"},
                 "cwd": str(root)}, ctx, prefix="mcp__ci__")
    assert "mcp__ci__grep_code" in cli.render(d)


def _guard_config(tmp_path, root, max_denies=2):
    path = tmp_path / "code-index-guard.toml"
    path.write_text(
        'mcp_prefix = "mcp__code_index__"\n'
        f"max_denies = {max_denies}\n"
        "[[local]]\n"
        f'path = "{root.as_posix()}"\n'
        'alias = "repo"\n',
        encoding="utf-8")
    return path


def _call_main(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.main([])
    return out.getvalue()


def test_deny_limit_breaks_loop(tmp_path, monkeypatch):
    root = build_repo(tmp_path)
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG",
                       str(_guard_config(tmp_path, root, max_denies=2)))
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(root / "Cargo.toml")},
        "session_id": "s1",
        "cwd": str(root),
    }
    decisions = []
    for _ in range(3):
        data = json.loads(_call_main(monkeypatch, payload))
        decisions.append(data["hookSpecificOutput"]["permissionDecision"])
    assert decisions == ["deny", "deny", "allow"]
    assert (tmp_path / "code-index-guard.state.json").is_file()


def test_deny_limit_resets_on_new_session(tmp_path, monkeypatch):
    root = build_repo(tmp_path)
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG",
                       str(_guard_config(tmp_path, root, max_denies=2)))
    tool_input = {"file_path": str(root / "Cargo.toml")}
    payload = {"tool_name": "Read", "tool_input": tool_input,
               "session_id": "old", "cwd": str(root)}
    assert json.loads(_call_main(monkeypatch, payload))[
        "hookSpecificOutput"]["permissionDecision"] == "deny"
    # Новая сессия — счётчик сбрасывается, снова deny.
    payload["session_id"] = "new"
    assert json.loads(_call_main(monkeypatch, payload))[
        "hookSpecificOutput"]["permissionDecision"] == "deny"


def test_deny_limit_zero_never_yields(tmp_path, monkeypatch):
    root = build_repo(tmp_path)
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG",
                       str(_guard_config(tmp_path, root, max_denies=0)))
    payload = {"tool_name": "Read",
               "tool_input": {"file_path": str(root / "Cargo.toml")},
               "session_id": "s1", "cwd": str(root)}
    for _ in range(3):
        assert json.loads(_call_main(monkeypatch, payload))[
            "hookSpecificOutput"]["permissionDecision"] == "deny"
