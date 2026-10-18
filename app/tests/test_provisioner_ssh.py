"""Tests for SshProvisioner — SFTP file operations + exec-channel commands."""
import io
import stat as _stat

import pytest

from agentmon.backends.ssh import SshProvisioner


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeExecChannel:
    def __init__(self, rc=0, out=b"", err=b""):
        self._rc, self._out, self._err = rc, out, err
        self.cmd = None

    def exec_command(self, cmd):
        self.cmd = cmd

    def makefile(self, *a):
        return io.BytesIO(self._out)

    def makefile_stderr(self, *a):
        return io.BytesIO(self._err)

    def recv_exit_status(self):
        return self._rc


class _WriteBuf:
    def __init__(self, sftp, path):
        self.sftp, self.path, self.data = sftp, path, b""

    def write(self, b):
        self.data += b if isinstance(b, bytes) else b.encode("utf-8")

    def read(self):
        return self.data

    def close(self):
        self.sftp.files[self.path] = self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeSftpRW:
    """In-memory SFTP: supports mkdir, stat, open(r/w), listdir."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()

    def mkdir(self, path):
        self.dirs.add(path)

    def stat(self, path):
        if path in self.files:
            # Return a fake stat object for a regular file
            class _St:
                st_mode = _stat.S_IFREG | 0o644
            return _St()
        if path in self.dirs:
            # Return a fake stat object for a directory
            class _St:
                st_mode = _stat.S_IFDIR | 0o755
            return _St()
        raise FileNotFoundError(path)

    def open(self, path, mode="r"):
        if "w" in mode:
            return _WriteBuf(self, path)
        if path not in self.files:
            raise FileNotFoundError(path)
        return io.BytesIO(self.files[path])

    def listdir(self, path):
        prefix = path.rstrip("/") + "/"
        return [k[len(prefix):].split("/")[0]
                for k in list(self.files) + list(self.dirs)
                if k.startswith(prefix) and k[len(prefix):]]


class FakeConn:
    def __init__(self, sftp, exec_rc=0, exec_out=b"", exec_err=b""):
        self._sftp = sftp
        self._exec = FakeExecChannel(exec_rc, exec_out, exec_err)
        self.exec_cmds: list[str] = []

    def sftp(self):
        return self._sftp

    def exec(self, cmd):
        """Thin helper — SshProvisioner calls this for exec operations."""
        self.exec_cmds.append(cmd)
        self._exec.exec_command(cmd)
        return self._exec


# ---------------------------------------------------------------------------
# Tests from the brief
# ---------------------------------------------------------------------------

def test_write_and_read_text():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    prov.write_text("/srv/demo/a.txt", "привет")
    assert prov.read_text("/srv/demo/a.txt") == "привет"


def test_mkdirs_creates_each_segment():
    sftp = FakeSftpRW()
    prov = SshProvisioner(FakeConn(sftp))
    prov.mkdirs(["/srv/demo/.claude/agents"])
    assert "/srv/demo/.claude/agents" in sftp.dirs


def test_run_returns_exit_status_and_output():
    prov = SshProvisioner(FakeConn(FakeSftpRW(), exec_rc=0, exec_out=b"ok\n"))
    res = prov.run(["echo", "ok"])
    assert res.returncode == 0 and "ok" in res.stdout


def test_python_cmd_and_venv_python_are_posix():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.python_cmd() == ["python3"]
    assert prov.venv_python("/srv/demo") == "/srv/demo/.venv/bin/python"


# ---------------------------------------------------------------------------
# Additional tests for is_file and tempdir (required by task instructions)
# ---------------------------------------------------------------------------

def test_is_file_returns_true_for_regular_file():
    sftp = FakeSftpRW()
    sftp.files["/srv/demo/foo.py"] = b"content"
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.is_file("/srv/demo/foo.py") is True


def test_is_file_returns_false_for_directory():
    sftp = FakeSftpRW()
    sftp.dirs.add("/srv/demo")
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.is_file("/srv/demo") is False


def test_is_file_returns_false_for_missing_path():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.is_file("/no/such/path") is False


def test_tempdir_returns_tmp():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.tempdir() == "/tmp"


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------

def test_exists_true_for_known_file():
    sftp = FakeSftpRW()
    sftp.files["/srv/x.txt"] = b"data"
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.exists("/srv/x.txt") is True


def test_exists_false_for_unknown_path():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.exists("/no/path") is False


def test_is_empty_dir_true_when_missing():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.is_empty_dir("/no/path") is True


def test_is_empty_dir_false_when_has_files():
    sftp = FakeSftpRW()
    sftp.dirs.add("/srv/project")
    sftp.files["/srv/project/a.txt"] = b"data"
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.is_empty_dir("/srv/project") is False


def test_is_empty_dir_true_for_empty_dir():
    sftp = FakeSftpRW()
    sftp.dirs.add("/srv/empty")
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.is_empty_dir("/srv/empty") is True


def test_is_empty_dir_false_for_regular_file():
    sftp = FakeSftpRW()
    sftp.files["/srv/a.txt"] = b"data"
    prov = SshProvisioner(FakeConn(sftp))
    assert prov.is_empty_dir("/srv/a.txt") is False


def test_write_bytes_and_read_back():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    prov.write_bytes("/srv/demo/data.bin", b"\x00\x01\x02")
    sftp = prov._c._sftp
    assert sftp.files["/srv/demo/data.bin"] == b"\x00\x01\x02"


def test_run_with_cwd_prefixes_cd():
    conn = FakeConn(FakeSftpRW(), exec_rc=0, exec_out=b"")
    prov = SshProvisioner(conn)
    prov.run(["ls"], cwd="/srv/demo")
    assert conn.exec_cmds[0].startswith("cd ")
    assert "/srv/demo" in conn.exec_cmds[0]


def test_which_returns_path_when_found():
    conn = FakeConn(FakeSftpRW(), exec_rc=0, exec_out=b"/usr/bin/git\n")
    prov = SshProvisioner(conn)
    result = prov.which("git")
    assert result == "/usr/bin/git"


def test_which_returns_none_when_not_found():
    conn = FakeConn(FakeSftpRW(), exec_rc=1, exec_out=b"")
    prov = SshProvisioner(conn)
    result = prov.which("nonexistent")
    assert result is None


def test_mkdirs_skips_existing_segments():
    sftp = FakeSftpRW()
    sftp.dirs.add("/srv")
    sftp.dirs.add("/srv/demo")
    prov = SshProvisioner(FakeConn(sftp))
    prov.mkdirs(["/srv/demo/new"])
    assert "/srv/demo/new" in sftp.dirs
    # existing dirs shouldn't cause errors
    assert "/srv" in sftp.dirs
    assert "/srv/demo" in sftp.dirs


def test_put_tree_ancestor_named_build_does_not_skip_root(tmp_path):
    """Абсолютный путь src содержит 'build' — содержимое НЕ должно скипаться."""
    src = tmp_path / "build" / "src"
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "keep.txt").write_text("keep")
    (src / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    sftp = FakeSftpRW()
    prov = SshProvisioner(FakeConn(sftp))
    prov.put_tree(str(src), "/remote/dst")
    written = set(sftp.files)
    assert "/remote/dst/keep.txt" in written
    assert all("__pycache__" not in p for p in written)
