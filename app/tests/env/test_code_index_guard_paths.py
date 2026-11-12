import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import paths  # noqa: E402


def test_match_longest_prefix_wins():
    roots = [("c:/proj", "proj"), ("c:/proj/core", "core")]
    got = paths.match_indexed("C:/proj/core/src/a.bsl", roots,
                              case_insensitive=True)
    assert got == ("core", "src/a.bsl", "C:/proj/core")


def test_match_exact_root_has_empty_rel():
    got = paths.match_indexed("C:/proj", [("c:/proj", "p")],
                              case_insensitive=True)
    assert got == ("p", "", "C:/proj")


def test_match_requires_path_boundary():
    roots = [("c:/proj", "p")]
    assert paths.match_indexed("C:/projects/x", roots, case_insensitive=True) is None


def test_match_case_sensitive_on_linux():
    roots = [("c:/proj", "p")]
    assert paths.match_indexed("C:/Proj/x", roots, case_insensitive=False) is None
    assert paths.match_indexed("C:/Proj/x", roots, case_insensitive=True) is not None


def test_msys_drive_and_backslashes():
    roots = [("c:/proj", "p")]
    got = paths.match_indexed("/c/proj/src/a.bsl", roots, case_insensitive=True)
    assert got == ("p", "src/a.bsl", "c:/proj")
    got = paths.match_indexed("C:\\proj\\src\\a.bsl", roots, case_insensitive=True)
    assert got == ("p", "src/a.bsl", "C:/proj")


def test_normalize_dir_collapses_dotdot_without_escaping_root():
    assert paths.normalize_dir("C:/a/b/../c/./d/") == "C:/a/c/d"
    assert paths.normalize_dir("/a/../../b") == "/b"
    assert paths.normalize_dir("a/b/..") == "a"


def test_msys_conversion_only_at_boundary():
    assert paths.normalize_msys_drives("/c/tmp/x") == "c:/tmp/x"
    assert paths.normalize_msys_drives("x/c/tmp") == "x/c/tmp"


def test_glob_match_simple():
    assert paths.glob_match("*_run_*.json", "tests/abc_run_2026.json")
    assert paths.glob_match("*_run_*.json", "abc_run_x.json")
    assert not paths.glob_match("*_run_*.json", "abc.json")
    assert paths.glob_match("exact.txt", "exact.txt")
    assert not paths.glob_match("exact.txt", "exact.txt.bak")


def test_strip_prefix_ci():
    assert paths.strip_prefix_ci("-Path foo", "-path ") == "foo"
    assert paths.strip_prefix_ci("foo", "-path ") is None
