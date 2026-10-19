import subprocess
import sys
from pathlib import Path

from agentmon.backends.local import LocalProvisioner
from agentmon.backends import RunResult


def test_mkdirs_creates_nested(tmp_path):
    prov = LocalProvisioner()
    target = tmp_path / "a" / "b" / "c"
    prov.mkdirs([str(target)])
    assert target.is_dir()


def test_write_and_read_text_roundtrip(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "x.txt"
    prov.write_text(str(p), "привет\n")
    assert prov.read_text(str(p)) == "привет\n"
    assert prov.exists(str(p)) is True


def test_is_empty_dir_semantics(tmp_path):
    prov = LocalProvisioner()
    assert prov.is_empty_dir(str(tmp_path / "missing")) is True
    assert prov.is_empty_dir(str(tmp_path)) is True
    (tmp_path / "f").write_text("x")
    assert prov.is_empty_dir(str(tmp_path)) is False


def test_put_tree_copies_and_skips(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "keep.txt").write_text("k")
    (src / "sub" / "drop.txt").write_text("d")
    dst = tmp_path / "dst"
    prov = LocalProvisioner()
    prov.put_tree(str(src), str(dst), skip=lambda rel: rel.parts[:1] == ("sub",))
    assert (dst / "keep.txt").read_text() == "k"
    assert not (dst / "sub" / "drop.txt").exists()


def test_run_returns_result(tmp_path):
    prov = LocalProvisioner()
    res = prov.run([sys.executable, "-c", "print('hi')"])
    assert res.returncode == 0
    assert "hi" in res.stdout


def test_which_finds_python():
    prov = LocalProvisioner()
    assert prov.which(Path(sys.executable).name) is not None


def test_python_cmd_is_monitor_interpreter():
    prov = LocalProvisioner()
    assert prov.python_cmd() == [sys.executable]


def test_venv_python_matches_os(tmp_path):
    prov = LocalProvisioner()
    got = prov.venv_python(str(tmp_path))
    assert ".venv" in got and got.endswith(("python", "python.exe"))


def test_is_file_distinguishes_file_from_dir(tmp_path):
    prov = LocalProvisioner()
    f = tmp_path / "bin"
    f.write_text("x")
    assert prov.is_file(str(f)) is True
    assert prov.is_file(str(tmp_path)) is False
    assert prov.is_file(str(tmp_path / "missing")) is False


def test_tempdir_returns_string():
    prov = LocalProvisioner()
    td = prov.tempdir()
    assert isinstance(td, str) and len(td) > 0


def test_put_tree_ancestor_named_build_does_not_skip_root(tmp_path):
    """Абсолютный путь к src содержит 'build' — содержимое НЕ должно скипаться."""
    src = tmp_path / "build" / "src"
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "keep.txt").write_text("keep")
    (src / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    dst = tmp_path / "dst"
    prov = LocalProvisioner()
    prov.put_tree(str(src), str(dst))
    assert (dst / "keep.txt").read_text() == "keep"
    assert not (dst / "pkg" / "__pycache__" / "x.pyc").exists()


# ---------------------------------------------------------------------------
# run timeout
# ---------------------------------------------------------------------------

def test_run_timeout_returns_124_and_timeout_marker(monkeypatch):
    """subprocess.TimeoutExpired → RunResult(124, ...) с маркером в stderr."""
    cmd = ["sleep", "1"]

    def fake_run(args, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr("agentmon.backends.local.subprocess.run", fake_run)
    prov = LocalProvisioner()
    res = prov.run(cmd, timeout=1)
    assert res.returncode == 124
    assert "<timeout>" in res.stderr
    assert isinstance(res.stdout, str)
    assert isinstance(res.stderr, str)


def test_run_timeout_does_not_raise(monkeypatch):
    """TimeoutExpired не всплывает наружу — только RunResult(124)."""
    def fake_run(args, **kw):
        raise subprocess.TimeoutExpired(args, 0.1)

    monkeypatch.setattr("agentmon.backends.local.subprocess.run", fake_run)
    prov = LocalProvisioner()
    # Главное — не исключение
    res = prov.run(["true"], timeout=0.1)
    assert res.returncode == 124


def test_run_timeout_none_normal_result(monkeypatch):
    """timeout=None сохраняет нормальное поведение (регрессия)."""
    class FakeProc:
        returncode = 0
        stdout = "hello\n"
        stderr = ""

    def fake_run(args, **kw):
        assert kw.get("timeout") is None
        return FakeProc()

    monkeypatch.setattr("agentmon.backends.local.subprocess.run", fake_run)
    prov = LocalProvisioner()
    res = prov.run(["echo", "hello"])
    assert res.returncode == 0
    assert res.stdout == "hello\n"


def test_run_timeout_partial_stdout_captured(monkeypatch):
    """Если TimeoutExpired несёт частичный вывод, он попадает в RunResult."""
    def fake_run(args, **kw):
        e = subprocess.TimeoutExpired(args, 1)
        e.stdout = "partial"
        e.stderr = "partial_err"
        raise e

    monkeypatch.setattr("agentmon.backends.local.subprocess.run", fake_run)
    prov = LocalProvisioner()
    res = prov.run(["cmd"], timeout=1)
    assert res.returncode == 124
    assert res.stdout == "partial"
    assert "partial_err" in res.stderr
    assert "<timeout>" in res.stderr
