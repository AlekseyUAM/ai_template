import os
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import bash, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


def _root(tmp_path, **kw):
    tools.set_prefix("mcp__code_index__")
    return build_repo(tmp_path, **kw)


def _decide(root, cmd, cwd=None):
    return bash.decide_bash({"command": cmd}, str(cwd or root), make_ctx(root))


def test_grep_on_indexed_file_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "grep -n main src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason


def test_cd_then_grep_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, f"cd {root} && grep -rn main src/")
    assert d is not None and d.allow is False


def test_grep_after_pipe_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "pytest -q 2>&1 | grep -E passed") is None


def test_git_grep_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git grep -n main -- src/") is None


def test_heredoc_with_commands_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git commit -F - <<'MSG'\nls src/\nMSG\n") is None


def test_grep_non_indexed_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -c name Cargo.lock") is None


def test_grep_excluded_dir_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -rn x target/release") is None


def test_cat_indexed_file_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "cat src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__read_file" in d.reason


def test_tail_non_indexed_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "tail -3 Cargo.lock") is None


def test_ls_existing_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, f"ls -la {root}/Cargo.toml") is None


def test_ls_directory_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "ls -R src")
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason
    assert ('First call: mcp__code_index__list_files(repo="repo", path_prefix="src")'
            in d.reason)


def test_ls_absolute_indexed_subdir_denied_with_path_prefix(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, f"ls {root}/src")
    assert d is not None and d.allow is False
    assert 'path_prefix="src"' in d.reason


def test_bare_ls_generic_listing_hint(tmp_path):
    # Root listing has no directory target -> the generic repo-root hint stays.
    root = _root(tmp_path)
    _fresh_index(root)
    d = _decide(root, "ls -la")
    assert d is not None and d.allow is False
    assert 'First call: mcp__code_index__list_files(repo="repo", pattern="*")' in d.reason


def test_binary_target_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -n x src/data.epf") is None


def test_variable_outside_repo_skipped(tmp_path):
    root = _root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert _decide(root, f'root="{outside}"; ls "$root"') is None


def test_bare_ls_from_indexed_cwd_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "ls -la")
    assert d is not None and d.allow is False


# --- Свежесть каталога: листинг изменившегося каталога не блокируем -------------

def _age_index(root, mtime=1700000000):
    """Индекс старше каталогов на диске — индекс «отстал»."""
    os.utime(root / ".code-index" / "index.db", (mtime, mtime))


def _fresh_index(root):
    """Свежий индекс: index.db новее всех каталогов репо (каталоги — в прошлом)."""
    past = (1699999000, 1699999000)
    for d in (root, root / "src", root / "target", root / ".code-index"):
        os.utime(d, past)


def test_ls_fresh_index_still_denied(tmp_path):
    # Свежий индекс: index.db новее каталога src → дед-энда нет, deny как раньше.
    root = _root(tmp_path)
    _fresh_index(root)
    assert _decide(root, "ls -R src") is not None
    assert _decide(root, "ls -la") is not None


def test_ls_new_directory_abstains(tmp_path):
    # Каталог появился после индексации: в MCP его нет, нативный ls — единственный путь.
    root = _root(tmp_path)
    _age_index(root)
    newdir = root / "newdir"
    newdir.mkdir()
    os.utime(newdir, (1700000100, 1700000100))
    assert _decide(root, "ls newdir") is None


def test_ls_new_directory_quoted_path_abstains(tmp_path):
    root = _root(tmp_path)
    _age_index(root)
    newdir = root / "newdir"
    newdir.mkdir()
    os.utime(newdir, (1700000100, 1700000100))
    assert _decide(root, f'ls "{root}/newdir"') is None


def test_bare_ls_changed_cwd_abstains(tmp_path):
    # Голый `ls` целится в base; base изменился после индекса → воздержаться.
    root = _root(tmp_path)
    _age_index(root)
    sub = root / "src"
    os.utime(sub, (1700000100, 1700000100))
    assert _decide(root, "ls -la", cwd=sub) is None


def test_cat_still_denied_when_index_behind(tmp_path):
    # Ослабление касается ТОЛЬКО листинга каталога: cat по-прежнему deny.
    root = _root(tmp_path)
    _age_index(root)
    d = _decide(root, "cat src/main.rs")
    assert d is not None and d.allow is False


def test_grep_still_denied_when_index_behind(tmp_path):
    root = _root(tmp_path)
    _age_index(root)
    d = _decide(root, "grep -rn main src")
    assert d is not None and d.allow is False
