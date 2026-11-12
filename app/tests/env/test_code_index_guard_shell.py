import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import paths, shell  # noqa: E402


def test_split_chain_quotes_and_pipe_cutoff():
    assert shell.split_chain("cd /r && grep -n 'a|b' x") == ["cd /r ", " grep -n 'a|b' x"]
    assert shell.split_chain("a; b\nc") == ["a", " b", "c"]
    assert shell.split_chain("git log | grep x") == ["git log "]


def test_heredoc_body_is_data():
    cmd = "git commit -F - <<'MSG'\nfix\nls -la\nMSG\n"
    assert shell.strip_heredocs(cmd) == "git commit -F - <<'MSG'"
    assert shell.heredoc_tag("python - <<PY") == "PY"
    assert shell.heredoc_tag("a <<< b") is None


def test_here_string_body_is_data():
    cmd = "git commit -m @'\nSelect-String x\n'@"
    assert "Select-String" not in shell.strip_here_strings(cmd)


def test_parse_assignment():
    assert shell.parse_assignment('root="/c/tmp"') == ("root", "/c/tmp")
    assert shell.parse_assignment("$root = 'C:/tmp'", ps=True) == ("root", "C:/tmp")
    assert shell.parse_assignment("a b=c") is None
    assert shell.parse_assignment("root=$HOME") is None


def test_dir_change():
    assert shell.dir_change("cd src", "C:/r", None) == "C:/r/src"
    assert shell.dir_change("cd ..", "C:/r/a", None) == "C:/r"
    assert shell.dir_change("cd ../other", "C:/r/a", None) == "C:/r/other"
    assert shell.dir_change("cd ~/p", "C:/r", "C:/Users/u") == "C:/Users/u/p"
    # Каталог стал неизвестен — отдельный маркер, НЕ пустая строка: пустая база
    # матчится с любым индексированным префиксом и даёт ложный отказ.
    assert shell.dir_change("cd -", "C:/r", None) is shell._UNKNOWN_DIR
    assert shell.dir_change("popd", "C:/r", None) is shell._UNKNOWN_DIR
    assert shell.dir_change("cd x", None, None) is shell._UNKNOWN_DIR
    assert shell.dir_change("sl", "C:/r", None) == "C:/r"
    assert shell.dir_change("ls", "C:/r", None) is None


def test_expand_vars_longest_first():
    assert shell.expand_vars("ls $a $abc", {"a": "/x", "abc": "/y"}) == "ls /x /y"


def test_explicit_path_and_prefix_boundary():
    assert shell.has_explicit_path("ls ~/.claude")
    assert shell.has_explicit_path("ls /tmp")
    assert not shell.has_explicit_path("ls src")
    assert shell.cmd_contains_indexed_prefix(
        paths.normalize_msys_drives("cd /c/repo && ls"), "c:/repo")
    assert not shell.cmd_contains_indexed_prefix(
        paths.normalize_msys_drives("ls /c/repo2"), "c:/repo")


def test_ls_targets_are_files(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert shell.ls_targets_are_files(f"ls -la {f}", str(tmp_path))
    assert not shell.ls_targets_are_files(f"ls -la {tmp_path}", str(tmp_path))
