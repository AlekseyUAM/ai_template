import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import decisions, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402

BIN = ("grep_code", "grep_text", "read_file", "list_files",
       "get_function", "get_file_summary", "stat_file", "get_stats")


def _ctx(root):
    tools.set_prefix("mcp__code_index__")
    return make_ctx(root)


def test_read_indexed_file_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_read({"file_path": str(root / "Cargo.toml")}, _ctx(root))
    assert d is not None and d.allow is False
    for name in ("read_file", "get_function", "get_file_summary"):
        assert f"mcp__code_index__{name}" in d.reason


def test_read_ritual_single_line_is_allowed(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_read(
        {"file_path": str(root / "Cargo.toml"), "offset": 1, "limit": 1}, _ctx(root))
    assert d is not None and d.allow is True


def test_read_non_indexed_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_read({"file_path": str(root / "Cargo.lock")}, _ctx(root)) is None


def test_read_oversize_is_skipped(tmp_path):
    root = build_repo(tmp_path, oversize=True)
    assert decisions.decide_read({"file_path": str(root / "src/main.rs")}, _ctx(root)) is None


def test_read_stale_index_is_skipped(tmp_path):
    root = build_repo(tmp_path, stale=True)
    assert decisions.decide_read({"file_path": str(root / "Cargo.toml")}, _ctx(root)) is None


def test_read_outside_root_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_read(
        {"file_path": str(tmp_path / "other.txt")}, _ctx(root)) is None


def test_grep_in_indexed_repo_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_grep({"pattern": "x"}, str(root), _ctx(root))
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason
    assert "mcp__code_index__grep_text" in d.reason


def test_grep_explicit_missing_path_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_grep(
        {"pattern": "x", "path": str(root / "nope")}, str(root), _ctx(root)) is None


def test_grep_excluded_glob_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_grep(
        {"pattern": "target", "glob": ".gitignore"}, str(root), _ctx(root)) is None


def test_glob_in_indexed_repo_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_glob({"pattern": "src/**/*.rs"}, str(root), _ctx(root))
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason


def test_glob_binary_pattern_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_glob({"pattern": "**/*.epf"}, str(root), _ctx(root)) is None


def test_glob_outside_root_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    assert decisions.decide_glob({"pattern": "**/*.rs"}, str(other), _ctx(root)) is None
