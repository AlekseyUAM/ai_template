import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import powershell, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


def _root(tmp_path, **kw):
    tools.set_prefix("mcp__code_index__")
    return build_repo(tmp_path, **kw)


def _decide(root, cmd):
    return powershell.decide_powershell({"command": cmd}, str(root), make_ctx(root))


def test_get_content_indexed_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Get-Content src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__read_file" in d.reason


def test_get_content_with_path_and_totalcount(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, f"Get-Content -Path {root}/Cargo.toml -TotalCount 5")
    assert d is not None and d.allow is False
    assert "line_end=5" in d.reason


def test_get_content_non_indexed_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "Get-Content Cargo.lock") is None


def test_select_string_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Select-String -Path src/main.rs -Pattern main")
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason


def test_get_childitem_directory_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Get-ChildItem src")
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason


def test_here_string_body_skipped(tmp_path):
    root = _root(tmp_path)
    cmd = "git commit -m @'\nGet-Content src/main.rs\n'@"
    assert _decide(root, cmd) is None


def test_git_command_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git log -S main -- src/") is None


def test_set_location_changes_base(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Set-Location src; Select-String -Pattern main")
    assert d is not None and d.allow is False


def test_alias_gc_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "gc src/main.rs")
    assert d is not None and d.allow is False
