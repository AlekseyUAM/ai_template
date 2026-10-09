import os

import pytest

from agentmon.backends.local import LocalBackend
from agentmon.models import Project


class FakePty:
    def __init__(self, cmd, cwd):
        self.cmd, self.cwd = cmd, cwd
        self.written = []
        self.alive = True
        self.killed = False
        self.terminated = False
        self.pending = ""
        self.raise_on_interrupt = False

    def write(self, text):
        self.written.append(text)

    def read_available(self):
        out, self.pending = self.pending, ""
        return out

    def interrupt(self):
        if self.raise_on_interrupt:
            # Имитирует EIO/EBADF при записи в PTY мёртвого процесса.
            raise OSError("simulated dead pty")
        self.written.append("\x1b")

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False


def make_backend(tmp_path):
    spawned = []

    def fake_spawn(cmd, cwd, env=None):
        p = FakePty(cmd, cwd)
        spawned.append(p)
        return p

    backend = LocalBackend(claude_cmd="claude --go", spawn_fn=fake_spawn,
                           home=str(tmp_path))
    return backend, spawned


def project(tmp_path, name="demo"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    return Project(id=1, name=name, path=str(d), backend="local", conn=None,
                   claude_cmd=None, created_at=0.0)


def test_start_spawns_with_command_and_cwd(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    agent_id = backend.runner.start(p)
    assert agent_id == p.key
    assert (spawned[0].cmd, spawned[0].cwd) == ("claude --go", p.path)


def test_project_can_override_command(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    p.claude_cmd = "claude-fake ."
    backend.runner.start(p)
    assert spawned[0].cmd == "claude-fake ."


def test_start_is_idempotent_while_alive(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    backend.runner.start(p)
    assert len(spawned) == 1


def test_start_respawns_after_death(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    spawned[0].alive = False
    backend.runner.start(p)
    assert len(spawned) == 2


def test_send_input_appends_carriage_return(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    backend.runner.send_input(p.key, "сделай дело")
    assert spawned[0].written == ["сделай дело\r"]


def test_send_input_strips_newlines(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    backend.runner.send_input(p.key, "первая\nвторая")
    assert spawned[0].written == ["первая вторая\r"]


def test_send_input_to_unknown_agent_raises(tmp_path):
    backend, _ = make_backend(tmp_path)
    with pytest.raises(KeyError):
        backend.runner.send_input("local||/nope", "x")


def test_stop_interrupt_sends_escape_and_keeps_agent(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    backend.runner.stop(p.key, "interrupt")
    assert spawned[0].written == ["\x1b"]
    assert backend.runner.is_alive(p.key) is True


def test_stop_kill_terminates_and_forgets_agent(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    backend.runner.stop(p.key, "kill")
    assert spawned[0].killed is True
    assert backend.runner.is_alive(p.key) is False


def test_is_alive_false_for_unknown_agent(tmp_path):
    backend, _ = make_backend(tmp_path)
    assert backend.runner.is_alive("local||/nope") is False


def test_tail_output_collects_pty_output(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    spawned[0].pending = "первая строка\n"
    backend.runner.is_alive(p.key)          # прокачивает буфер
    spawned[0].pending = "вторая строка\n"
    assert backend.runner.tail_output(p.key) == "первая строка\nвторая строка\n"


def test_tail_output_is_capped(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    spawned[0].pending = "x" * 100
    assert backend.runner.tail_output(p.key, limit=10) == "x" * 10


def test_shutdown_all_kills_every_agent(tmp_path):
    backend, spawned = make_backend(tmp_path)
    a, b = project(tmp_path, "a"), project(tmp_path, "b")
    b.id = 2
    backend.runner.start(a)
    backend.runner.start(b)
    backend.runner.shutdown_all()
    assert all(p.killed for p in spawned)
    assert backend.runner.is_alive(a.key) is False


def test_home_projects_dir_points_at_claude_projects(tmp_path):
    backend, _ = make_backend(tmp_path)
    assert backend.files.home_projects_dir() == str(tmp_path / ".claude" / "projects")


def test_list_files_reports_dir_and_session(tmp_path):
    backend, _ = make_backend(tmp_path)
    pdir = tmp_path / ".claude" / "projects" / "-home-u-demo"
    pdir.mkdir(parents=True)
    (pdir / "sess-1.jsonl").write_bytes(b"abc")
    (pdir / "notes.txt").write_bytes(b"ignore me")
    refs = backend.files.list_files(backend.files.home_projects_dir())
    assert len(refs) == 1
    assert (refs[0].dir_name, refs[0].session_id, refs[0].size) == (
        "-home-u-demo", "sess-1", 3)


def test_list_files_on_missing_dir_returns_empty(tmp_path):
    backend, _ = make_backend(tmp_path)
    assert backend.files.list_files(str(tmp_path / "nope")) == []


def test_read_from_returns_tail_and_new_offset(tmp_path):
    backend, _ = make_backend(tmp_path)
    f = tmp_path / "log.jsonl"
    f.write_bytes(b"0123456789")
    data, offset = backend.files.read_from(str(f), 4)
    assert (data, offset) == (b"456789", 10)


def test_read_from_missing_file_returns_empty(tmp_path):
    backend, _ = make_backend(tmp_path)
    assert backend.files.read_from(str(tmp_path / "nope"), 0) == (b"", 0)


def test_stop_interrupt_on_dead_process_does_not_raise_and_forgets_agent(tmp_path):
    backend, spawned = make_backend(tmp_path)
    p = project(tmp_path)
    backend.runner.start(p)
    spawned[0].raise_on_interrupt = True
    backend.runner.stop(p.key, "interrupt")  # не должно бросать OSError
    assert backend.runner.is_alive(p.key) is False


class _BrokenStatEntry:
    """Имитирует os.DirEntry, чей .stat() падает (гонка/сбой ФС)."""

    def __init__(self, name, path):
        self.name = name
        self.path = path

    def is_file(self):
        return True

    def is_dir(self):
        return False

    def stat(self):
        raise OSError("simulated stat failure")


def test_list_files_warns_and_continues_on_stat_error(tmp_path, monkeypatch, caplog):
    backend, _ = make_backend(tmp_path)
    pdir = tmp_path / ".claude" / "projects" / "-home-u-demo"
    pdir.mkdir(parents=True)
    (pdir / "good.jsonl").write_bytes(b"abc")

    real_scandir = os.scandir

    def fake_scandir(path):
        entries = list(real_scandir(path))
        if os.path.abspath(path) == os.path.abspath(str(pdir)):
            entries.append(_BrokenStatEntry("broken.jsonl", str(pdir / "broken.jsonl")))
        return entries

    monkeypatch.setattr(os, "scandir", fake_scandir)

    with caplog.at_level("WARNING"):
        refs = backend.files.list_files(backend.files.home_projects_dir())

    assert [r.session_id for r in refs] == ["good"]
    assert any("broken.jsonl" in rec.message for rec in caplog.records)


def test_list_files_skips_session_dir_deleted_mid_walk(tmp_path, monkeypatch, caplog):
    """Если каталог сессии исчезает между внешним и внутренним scandir,
    обновление не падает: сбойный каталог пропускается, остальные читаются."""
    backend, _ = make_backend(tmp_path)
    root = tmp_path / ".claude" / "projects"
    good = root / "-good"
    gone = root / "-gone"
    good.mkdir(parents=True)
    gone.mkdir(parents=True)
    (good / "s.jsonl").write_bytes(b"abc")

    real_scandir = os.scandir

    def fake_scandir(path):
        if os.path.abspath(path) == os.path.abspath(str(gone)):
            raise FileNotFoundError("session dir removed mid-walk")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", fake_scandir)

    with caplog.at_level("WARNING"):
        refs = backend.files.list_files(backend.files.home_projects_dir())

    assert [r.session_id for r in refs] == ["s"]
    assert any("gone" in rec.message for rec in caplog.records)


def test_read_from_error_logs_warning(tmp_path, caplog):
    backend, _ = make_backend(tmp_path)
    missing = str(tmp_path / "nope")
    with caplog.at_level("WARNING"):
        result = backend.files.read_from(missing, 0)
    assert result == (b"", 0)
    assert any(missing in rec.message for rec in caplog.records)
