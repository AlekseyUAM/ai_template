import json
import os
from pathlib import Path
from types import SimpleNamespace

from bench_index import index_db_path, index_is_stale, refresh_index


def make_project(tmp_path, *, db_after_sources=True):
    import os
    project = tmp_path / "project"
    root = project / "src" / "cf"
    root.mkdir(parents=True)
    (root / "Documents").mkdir()
    src = root / "Documents" / "Анкета.xml"
    src.write_text("<xml/>", encoding="utf-8")
    db_dir = root / ".code-index"
    db_dir.mkdir()
    db = db_dir / "index.db"
    db.write_text("db", encoding="utf-8")
    # Явный разброс mtime: порядок создания файлов разрешением ФС не гарантирует.
    offset = 10 if db_after_sources else -10
    stat = src.stat()
    os.utime(db, (stat.st_atime + offset, stat.st_mtime + offset))
    return project


def test_index_is_stale_detects_newer_sources(tmp_path):
    assert index_is_stale(make_project(tmp_path)) is False
    project = make_project(tmp_path / "stale", db_after_sources=False)
    assert index_is_stale(project) is True


def test_index_is_stale_on_deleted_source_in_subdirectory(tmp_path):
    """Удаление файла меняет mtime каталога, а не оставшихся файлов."""
    project = make_project(tmp_path)
    assert index_is_stale(project) is False
    subdir = project / "src" / "cf" / "Documents"
    (subdir / "Анкета.xml").unlink()
    db_mtime = index_db_path(project).stat().st_mtime
    os.utime(subdir, (db_mtime + 10, db_mtime + 10))
    assert index_is_stale(project) is True


def test_index_compare_is_strict_on_equal_mtime(tmp_path):
    """Равенство mtime источника и индекса — индекс ещё свежий (строгое `>`)."""
    project = make_project(tmp_path)
    root = project / "src" / "cf"
    db_mtime = index_db_path(project).stat().st_mtime
    for path in (root, root / "Documents", root / "Documents" / "Анкета.xml"):
        os.utime(path, (db_mtime, db_mtime))
    assert index_is_stale(project) is False


def test_refresh_index_skips_fresh_index(tmp_path):
    project = make_project(tmp_path)
    calls = []
    status = refresh_index(project, run=lambda *a, **k: calls.append(a),
                           sleep=lambda _s: None, clock=lambda: 0.0)
    assert status == "fresh"
    assert calls == []


def test_refresh_index_restarts_and_waits_ready(tmp_path, monkeypatch):
    project = make_project(tmp_path / "stale", db_after_sources=False)
    monkeypatch.setattr("bench_index.shutil.which", lambda name: "docker")
    statuses = [
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="starting"),
        SimpleNamespace(returncode=0, stdout=json.dumps(
            {"paths": [{"path": "/repos/src", "status": "ready"}]}), stderr=""),
    ]
    def fake_run(argv, **kwargs):
        return statuses.pop(0)
    ticks = iter([0.0, 0.0, 0.0, 1.0])
    status = refresh_index(
        project, run=fake_run, sleep=lambda _s: None,
        clock=lambda: next(ticks, 2.0), timeout_sec=30, log=lambda _m: None)
    assert status == "ready"
