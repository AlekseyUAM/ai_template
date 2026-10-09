import pytest

from agentmon.backends.factory import BackendRegistry
from agentmon.models import Project


class FakeBackend:
    def __init__(self, key):
        self.key = key
        self.closed = False
        self.runner = object()
        self.files = object()

    def close(self):
        self.closed = True


def local(path="/p/a"):
    return Project(id=1, name="a", path=path, backend="local", conn=None,
                   claude_cmd=None, created_at=0.0)


def ssh(host="srv", path="/srv/a", user="root", port=22):
    return Project(id=2, name="b", path=path, backend="ssh",
                   conn={"host": host, "port": port, "user": user, "key_path": None},
                   claude_cmd=None, created_at=0.0)


def make():
    made = []

    def local_factory():
        b = FakeBackend("local")
        made.append(b)
        return b

    def ssh_factory(conn):
        b = FakeBackend(f"ssh|{conn['user']}@{conn['host']}:{conn['port']}")
        made.append(b)
        return b

    return BackendRegistry(claude_cmd="claude", local_factory=local_factory,
                           ssh_factory=ssh_factory), made


def test_all_local_projects_share_one_backend():
    reg, made = make()
    assert reg.get(local("/p/a")) is reg.get(local("/p/b"))
    assert len(made) == 1


def test_projects_on_same_host_share_one_backend():
    reg, made = make()
    assert reg.get(ssh(path="/srv/a")) is reg.get(ssh(path="/srv/b"))
    assert len(made) == 1


def test_different_hosts_get_different_backends():
    reg, made = make()
    assert reg.get(ssh(host="h1")) is not reg.get(ssh(host="h2"))
    assert len(made) == 2


def test_different_users_on_same_host_get_different_backends():
    reg, made = make()
    assert reg.get(ssh(user="root")) is not reg.get(ssh(user="dev"))
    assert len(made) == 2


def test_key_for_matches_backend_key():
    reg, _ = make()
    p = ssh()
    assert reg.key_for(p) == "ssh|root@srv:22"
    assert reg.key_for(local()) == "local"


def test_invalidate_closes_and_drops_backend():
    reg, made = make()
    first = reg.get(local())
    reg.invalidate("local")
    assert first.closed is True
    assert reg.get(local()) is not first


def test_close_all_closes_every_backend():
    reg, made = make()
    reg.get(local())
    reg.get(ssh())
    reg.close_all()
    assert all(b.closed for b in made)
    assert reg.items() == []


def test_unknown_backend_raises():
    reg, _ = make()
    p = local()
    p.backend = "podman"
    with pytest.raises(ValueError, match="podman"):
        reg.get(p)
