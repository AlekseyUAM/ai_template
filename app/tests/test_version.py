from agentmon import version


def test_fingerprint_is_stable(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = version.source_fingerprint(tmp_path)
    assert version.source_fingerprint(tmp_path) == first


def test_fingerprint_changes_when_source_changes(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    before = version.source_fingerprint(tmp_path)
    f.write_text("x = 2\n")
    assert version.source_fingerprint(tmp_path) != before


def test_fingerprint_changes_when_file_added(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    before = version.source_fingerprint(tmp_path)
    (tmp_path / "b.py").write_text("y = 1\n")
    assert version.source_fingerprint(tmp_path) != before


def test_fingerprint_changes_when_file_renamed(tmp_path):
    """Одно и то же содержимое под другим именем — другой отпечаток."""
    (tmp_path / "a.py").write_text("x = 1\n")
    before = version.source_fingerprint(tmp_path)
    (tmp_path / "a.py").rename(tmp_path / "b.py")
    assert version.source_fingerprint(tmp_path) != before


def test_fingerprint_ignores_pycache(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    before = version.source_fingerprint(tmp_path)
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "a.cpython-311.py").write_text("скомпилированный мусор\n")
    assert version.source_fingerprint(tmp_path) == before


def test_fingerprint_ignores_non_python(tmp_path):
    """Файлы web/ и прочие не-.py перезапуска не требуют и в отпечаток не входят."""
    (tmp_path / "a.py").write_text("x = 1\n")
    before = version.source_fingerprint(tmp_path)
    (tmp_path / "app.js").write_text("console.log(1)\n")
    (tmp_path / "readme.md").write_text("текст\n")
    assert version.source_fingerprint(tmp_path) == before


def test_status_not_stale_in_a_fresh_process():
    st = version.status()
    assert st["stale"] is False
    assert st["loaded"] == st["disk"]
    assert st["uptime_seconds"] >= 0


def test_status_reports_stale_when_loaded_differs(monkeypatch):
    """Именно этот случай и ловим: в памяти один код, на диске другой."""
    monkeypatch.setattr(version, "LOADED_FINGERPRINT", "отпечаток-старого-кода")
    st = version.status()
    assert st["stale"] is True
    assert st["loaded"] == "отпечаток-старого-кода"
    assert st["disk"] != "отпечаток-старого-кода"
