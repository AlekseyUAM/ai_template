import os
import shutil
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import index_db  # noqa: E402
from env.guard_fixtures import build_repo  # noqa: E402


def test_text_contents_v5_is_serveable(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.toml", case_insensitive=False) == (True, 1700000000)


def test_text_files_v4_is_serveable(tmp_path):
    root = build_repo(tmp_path, v4=True)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.toml", case_insensitive=False) == (True, 1700000000)


def test_oversize_is_not_serveable(tmp_path):
    root = build_repo(tmp_path, oversize=True)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "src/main.rs", case_insensitive=False) == (False, 1700000000)


def test_bare_row_is_not_serveable(tmp_path):
    # Строка в files без text_contents и file_contents — «голая»: MCP не отдаст,
    # но mtime у неё есть (upstream возвращает Some(mtime)).
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.lock", case_insensitive=False) == (False, 1700000000)


def test_unknown_file_is_not_serveable(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "missing.txt", case_insensitive=False) == (False, None)


def test_read_is_blockable_requires_db(tmp_path):
    root = build_repo(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert index_db.read_is_blockable(str(empty), "Cargo.toml", case_insensitive=False) is False


def test_read_is_blockable_true_for_indexed_file(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.read_is_blockable(str(root), "Cargo.toml", case_insensitive=False) is True


def test_read_is_blockable_false_when_disk_is_newer(tmp_path):
    root = build_repo(tmp_path, stale=True)
    assert index_db.read_is_blockable(str(root), "Cargo.toml", case_insensitive=False) is False


def test_excluded_builtin_segments(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.excluded_from_index(str(root), "target/release/x", case_insensitive=False)
    assert index_db.excluded_from_index(str(root), ".git/config", case_insensitive=False)
    assert not index_db.excluded_from_index(str(root), "src/main.rs", case_insensitive=False)


def test_excluded_project_config_and_unindexed_file(tmp_path):
    root = build_repo(tmp_path)
    cfg = root / ".code-index" / "config.json"
    cfg.write_text('{"exclude_dirs": ["out"], '
                   '"exclude_file_patterns": ["*_run_*.json"]}', encoding="utf-8")
    assert index_db.excluded_from_index(str(root), "out/x.bsl", case_insensitive=False)
    assert index_db.excluded_from_index(str(root), "tests/a_run_1.json", case_insensitive=False)
    # существующий, но отсутствующий в индексе файл — неиндексируемый
    assert index_db.excluded_from_index(str(root), "Cargo.lock", case_insensitive=False)


def test_dir_changed_since_index_true_for_newer_dir(tmp_path):
    root = build_repo(tmp_path)
    os.utime(root / ".code-index" / "index.db", (1700000000, 1700000000))
    d = root / "newdir"
    d.mkdir()
    os.utime(d, (1700000100, 1700000100))
    assert index_db.dir_changed_since_index(str(root), "newdir") is True


def test_dir_changed_since_index_false_for_older_dir(tmp_path):
    # Обратный порядок величин: старый каталог против нового index.db.
    root = build_repo(tmp_path)
    os.utime(root / ".code-index" / "index.db", (1700000100, 1700000100))
    d = root / "newdir"
    d.mkdir()
    os.utime(d, (1700000000, 1700000000))
    assert index_db.dir_changed_since_index(str(root), "newdir") is False


def test_dir_changed_since_index_true_for_new_dir_old_db(tmp_path):
    # Индекс сильно старше каталога (не каталог «в будущем»): большой отрыв
    # в другую сторону тоже должен давать True.
    root = build_repo(tmp_path)
    os.utime(root / ".code-index" / "index.db", (1000000000, 1000000000))
    d = root / "newdir"
    d.mkdir()
    os.utime(d, (1700000100, 1700000100))
    assert index_db.dir_changed_since_index(str(root), "newdir") is True


def test_dir_changed_since_index_true_above_unix_epoch_2gip(tmp_path):
    # mtime больше 2^31: старший разряд не должен менять знак сравнения.
    root = build_repo(tmp_path)
    os.utime(root / ".code-index" / "index.db", (2147483648, 2147483648))
    d = root / "newdir"
    d.mkdir()
    os.utime(d, (2147483649, 2147483649))
    assert index_db.dir_changed_since_index(str(root), "newdir") is True


def test_dir_changed_since_index_false_below_unix_epoch_2gip(tmp_path):
    root = build_repo(tmp_path)
    os.utime(root / ".code-index" / "index.db", (2147483649, 2147483649))
    d = root / "newdir"
    d.mkdir()
    os.utime(d, (2147483648, 2147483648))
    assert index_db.dir_changed_since_index(str(root), "newdir") is False


def test_dir_changed_since_index_false_without_db_or_dir(tmp_path):
    root = build_repo(tmp_path)
    # каталога нет
    assert index_db.dir_changed_since_index(str(root), "missing") is False
    # БД нет
    shutil.rmtree(root / ".code-index")
    (root / "newdir").mkdir()
    assert index_db.dir_changed_since_index(str(root), "newdir") is False
