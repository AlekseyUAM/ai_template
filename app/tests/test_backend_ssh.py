import logging

import pytest

from agentmon.backends.ssh import SshBackend, SshUnavailable
from agentmon.models import Project


class FakeChannel:
    def __init__(self):
        self.sent = []
        self.cmd = None
        self.closed = False
        self.pending = b""
        self.exited = False
        self.pty = False

    def get_pty(self, **kw):
        self.pty = True

    def exec_command(self, cmd):
        self.cmd = cmd

    def send(self, data):
        self.sent.append(data)

    def recv_ready(self):
        return bool(self.pending)

    def recv(self, n):
        out, self.pending = self.pending[:n], self.pending[n:]
        return out

    def exit_status_ready(self):
        return self.exited

    def close(self):
        self.closed = True
        self.exited = True


class FakeAttrs:
    def __init__(self, filename, size, mtime, is_dir):
        self.filename, self.st_size, self.st_mtime = filename, size, mtime
        self.st_mode = 0o040755 if is_dir else 0o100644


class FakeSftpFile:
    def __init__(self, blob):
        self._blob, self._pos = blob, 0

    def seek(self, pos):
        self._pos = pos

    def read(self):
        out, self._pos = self._blob[self._pos:], len(self._blob)
        return out

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeSftp:
    def __init__(self, tree, blobs, home="/root"):
        self.tree, self.blobs = tree, blobs
        self.home = home
        self.normalize_error = None
        self.normalize_calls = 0

    def listdir_attr(self, path):
        if path not in self.tree:
            raise FileNotFoundError(path)
        return self.tree[path]

    def open(self, path, mode="rb"):
        if path not in self.blobs:
            raise FileNotFoundError(path)
        return FakeSftpFile(self.blobs[path])

    def normalize(self, path):
        self.normalize_calls += 1
        if self.normalize_error is not None:
            raise self.normalize_error
        return self.home


class FakeTransport:
    def __init__(self, client):
        self.client = client

    def open_session(self):
        ch = FakeChannel()
        self.client.channels.append(ch)
        return ch

    def is_active(self):
        return self.client.transport_active


class FakeClient:
    def __init__(self, tree=None, blobs=None, home="/root"):
        self.channels = []
        self.closed = False
        self.transport_active = True
        self.home = home
        self._sftp = FakeSftp(tree or {}, blobs or {}, home=home)

    def get_transport(self):
        return FakeTransport(self)

    def open_sftp(self):
        return self._sftp

    def close(self):
        self.closed = True


CONN = {"host": "srv", "port": 22, "user": "root", "key_path": None}


def make_backend(client=None, **kw):
    client = client or FakeClient()
    calls = []

    def connect_fn(conn):
        calls.append(conn)
        return client

    return SshBackend(CONN, claude_cmd="claude --go",
                      connect_fn=connect_fn, **kw), client, calls


def project(path="/srv/demo"):
    return Project(id=1, name="demo", path=path, backend="ssh", conn=CONN,
                   claude_cmd=None, created_at=0.0)


def test_key_identifies_host_and_user():
    backend, _, _ = make_backend()
    assert backend.key == "ssh|root@srv:22"


def test_start_requests_pty_and_runs_command_in_project_dir():
    backend, client, _ = make_backend()
    p = project()
    assert backend.runner.start(p) == p.key
    ch = client.channels[0]
    assert ch.pty is True
    assert ch.cmd == "cd /srv/demo && exec claude --go"


def test_connection_is_opened_once_for_several_agents():
    backend, _, calls = make_backend()
    backend.runner.start(project("/srv/a"))
    backend.runner.start(project("/srv/b"))
    assert len(calls) == 1


def test_send_input_appends_carriage_return():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    backend.runner.send_input(p.key, "сделай\nдело")
    assert client.channels[0].sent == ["сделай дело\r".encode()]


def test_stop_interrupt_sends_escape():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    backend.runner.stop(p.key, "interrupt")
    assert client.channels[0].sent == [b"\x1b"]


def test_stop_kill_closes_channel():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    backend.runner.stop(p.key, "kill")
    assert client.channels[0].closed is True
    assert backend.runner.is_alive(p.key) is False


def test_is_alive_follows_exit_status():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    assert backend.runner.is_alive(p.key) is True
    client.channels[0].exited = True
    assert backend.runner.is_alive(p.key) is False


def test_tail_output_collects_channel_data():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    client.channels[0].pending = "привет\n".encode()
    assert backend.runner.tail_output(p.key) == "привет\n"


def test_list_files_walks_sftp_tree():
    tree = {
        "/root/.claude/projects": [FakeAttrs("-srv-demo", 0, 0.0, True),
                                   FakeAttrs("readme", 10, 0.0, False)],
        "/root/.claude/projects/-srv-demo": [FakeAttrs("s1.jsonl", 42, 7.0, False),
                                             FakeAttrs("note.txt", 1, 1.0, False)],
    }
    backend, _, _ = make_backend(FakeClient(tree=tree))
    refs = backend.files.list_files("/root/.claude/projects")
    assert len(refs) == 1
    assert (refs[0].path, refs[0].dir_name, refs[0].session_id,
            refs[0].size, refs[0].mtime) == (
        "/root/.claude/projects/-srv-demo/s1.jsonl", "-srv-demo", "s1", 42, 7.0)


def test_read_from_seeks_and_returns_offset():
    blobs = {"/x/a.jsonl": b"0123456789"}
    backend, _, _ = make_backend(FakeClient(blobs=blobs))
    assert backend.files.read_from("/x/a.jsonl", 4) == (b"456789", 10)


def test_read_from_missing_file_returns_empty():
    backend, _, _ = make_backend()
    assert backend.files.read_from("/x/none.jsonl", 0) == (b"", 0)


def test_failed_connect_raises_ssh_unavailable():
    def bad_connect(conn):
        raise OSError("connection refused")

    backend = SshBackend(CONN, claude_cmd="c", connect_fn=bad_connect)
    with pytest.raises(SshUnavailable):
        backend.runner.start(project())


def test_broken_connection_is_not_retried_before_cooldown():
    calls = []

    def bad_connect(conn):
        calls.append(conn)
        raise OSError("down")

    now = {"t": 1000.0}
    backend = SshBackend(CONN, claude_cmd="c", connect_fn=bad_connect,
                         clock=lambda: now["t"], retry_seconds=10.0)
    for _ in range(3):
        with pytest.raises(SshUnavailable):
            backend.runner.start(project())
    assert len(calls) == 1
    now["t"] = 1011.0
    with pytest.raises(SshUnavailable):
        backend.runner.start(project())
    assert len(calls) == 2


def test_agents_are_dead_while_connection_is_broken():
    client = FakeClient()
    ok = {"v": True}

    def connect_fn(conn):
        if not ok["v"]:
            raise OSError("down")
        return client

    backend = SshBackend(CONN, claude_cmd="c", connect_fn=connect_fn)
    p = project()
    backend.runner.start(p)
    ok["v"] = False
    backend.mark_broken()
    assert backend.runner.is_alive(p.key) is False


def test_list_files_while_broken_returns_empty():
    backend, _, _ = make_backend()
    backend.mark_broken()
    assert backend.files.list_files("/root/.claude/projects") == []


def test_check_opens_connection():
    backend, client, calls = make_backend()
    backend.check()
    assert len(calls) == 1


def test_check_propagates_failure():
    def bad_connect(conn):
        raise OSError("no route")

    backend = SshBackend(CONN, claude_cmd="c", connect_fn=bad_connect)
    with pytest.raises(SshUnavailable):
        backend.check()


# --- Ревью Task 8: обрыв связи не должен держать бэкенд битым вечно ---


def test_mark_broken_is_idempotent_about_retry_window():
    calls = []

    def bad_connect(conn):
        calls.append(conn)
        raise OSError("down")

    now = {"t": 1000.0}
    backend = SshBackend(CONN, claude_cmd="c", connect_fn=bad_connect,
                         clock=lambda: now["t"], retry_seconds=10.0)

    backend.mark_broken()          # пометка в t=1000, ещё не пытались подключиться
    now["t"] = 1005.0
    backend.mark_broken()          # повторная пометка НЕ должна сдвинуть окно
    now["t"] = 1011.0              # 11 секунд от t=1000 — окно должно истечь

    with pytest.raises(SshUnavailable):
        backend.runner.start(project())
    # была настоящая попытка подключения (а не отказ по cooldown) —
    # значит окно отсчитывалось от первой пометки, а не от повторной.
    assert len(calls) == 1


def test_tail_output_on_broken_connection_does_not_touch_channel():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    ch = client.channels[0]
    ch.pending = "до обрыва\n".encode()
    assert backend.runner.tail_output(p.key) == "до обрыва\n"

    backend.mark_broken()
    ch.pending = "после обрыва\n".encode()
    assert backend.runner.tail_output(p.key) == "до обрыва\n"
    # recv ни разу не позвали — данные так и лежат непрочитанными
    assert ch.pending == "после обрыва\n".encode()


def test_dead_channel_is_forgotten_after_pump_failure():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    ch = client.channels[0]

    def boom():
        raise OSError("recv failed")

    ch.recv_ready = boom
    backend.runner.tail_output(p.key)  # триггерит _pump -> исключение -> забыт

    with pytest.raises(KeyError):
        backend.runner.send_input(p.key, "привет")


def test_stop_kill_forgets_agent_even_if_close_raises():
    backend, client, _ = make_backend()
    p = project()
    backend.runner.start(p)
    ch = client.channels[0]

    def boom():
        raise OSError("close failed")

    ch.close = boom
    with pytest.raises(SshUnavailable):
        backend.runner.stop(p.key, "kill")
    assert backend.runner.is_alive(p.key) is False
    # is_alive может вернуть False просто из-за битого соединения — проверим
    # ещё и напрямую, что запись реально убрана из словаря, а не просто
    # замаскирована сломанным соединением.
    assert p.key not in backend.runner._channels


def test_home_projects_dir_uses_sftp_normalize():
    client = FakeClient(home="/home/dev")
    backend, _, _ = make_backend(client)
    assert backend.files.home_projects_dir() == "/home/dev/.claude/projects"
    assert backend.files.home_projects_dir() == "/home/dev/.claude/projects"
    assert client._sftp.normalize_calls == 1  # результат закеширован


def test_home_projects_dir_falls_back_and_does_not_cache_failure(caplog):
    client = FakeClient(home="/home/dev")
    client._sftp.normalize_error = OSError("operation not supported")
    backend, _, _ = make_backend(client)

    with caplog.at_level(logging.WARNING):
        path = backend.files.home_projects_dir()
    assert path == "/root/.claude/projects"  # догадка для пользователя root
    assert "srv" in caplog.text

    client._sftp.normalize_error = None  # связь "восстановилась"
    assert backend.files.home_projects_dir() == "/home/dev/.claude/projects"


def test_explicit_home_skips_normalize_call():
    client = FakeClient(home="/should/not/be/used")
    backend, _, _ = make_backend(client, home="/explicit/home")
    assert backend.files.home_projects_dir() == "/explicit/home/.claude/projects"
    assert client._sftp.normalize_calls == 0


# --- Ошибка одного канала не убивает остальных агентов хоста (Finding 9) ---


def test_channel_failure_does_not_kill_other_agents_on_the_host():
    """Агент, вышедший секунду назад, даёт OSError на своём канале.

    Пометив по этому поводу всё соединение битым, монитор объявил бы
    мёртвыми и агентов остальных проектов того же хоста — диспетчер вернул
    бы их задачи в очередь и убил бы их агентов.
    """
    backend, client, _ = make_backend()
    a, b = project("/srv/a"), project("/srv/b")
    backend.runner.start(a)
    backend.runner.start(b)
    chan_a = client.channels[0]

    def boom(data):
        raise OSError("Socket is closed")

    chan_a.send = boom
    with pytest.raises(SshUnavailable):
        backend.runner.send_input(a.key, "привет")

    assert backend.is_broken is False
    assert backend.runner.is_alive(b.key) is True   # сосед жив
    assert backend.runner.is_alive(a.key) is False  # а сам канал забыт


def test_channel_failure_marks_connection_broken_when_transport_is_gone():
    backend, client, _ = make_backend()
    a, b = project("/srv/a"), project("/srv/b")
    backend.runner.start(a)
    backend.runner.start(b)

    client.transport_active = False                 # транспорт пропал целиком

    def boom(data):
        raise OSError("Socket is closed")

    client.channels[0].send = boom
    with pytest.raises(SshUnavailable):
        backend.runner.send_input(a.key, "привет")

    assert backend.is_broken is True
    assert backend.runner.is_alive(b.key) is False


def test_pump_failure_on_one_channel_spares_the_connection():
    backend, client, _ = make_backend()
    a, b = project("/srv/a"), project("/srv/b")
    backend.runner.start(a)
    backend.runner.start(b)

    def boom():
        raise OSError("recv failed")

    client.channels[0].recv_ready = boom
    backend.runner.tail_output(a.key)

    assert backend.is_broken is False
    assert backend.runner.is_alive(b.key) is True


def test_stop_failure_on_one_channel_spares_the_connection():
    backend, client, _ = make_backend()
    a, b = project("/srv/a"), project("/srv/b")
    backend.runner.start(a)
    backend.runner.start(b)

    def boom(data):
        raise OSError("Socket is closed")

    client.channels[0].send = boom
    with pytest.raises(SshUnavailable):
        backend.runner.stop(a.key, "interrupt")

    assert backend.is_broken is False
    assert backend.runner.is_alive(b.key) is True


def test_key_path_is_tilde_expanded(monkeypatch):
    """Форма ввода предлагает "~/.ssh/id_ed25519", а paramiko тильду не знает."""
    import agentmon.backends.ssh as ssh_module

    captured = {}

    class FakeParamiko:
        class AutoAddPolicy:
            pass

        class SSHClient:
            def load_system_host_keys(self):
                pass

            def set_missing_host_key_policy(self, policy):
                pass

            def connect(self, **kw):
                captured.update(kw)

    monkeypatch.setitem(__import__("sys").modules, "paramiko", FakeParamiko)
    monkeypatch.setenv("HOME", "/home/tester")
    ssh_module._real_connect({"host": "srv", "key_path": "~/.ssh/id_ed25519"})
    assert captured["key_filename"] == "/home/tester/.ssh/id_ed25519"
