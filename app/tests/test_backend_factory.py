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


# ---------------------------------------------------------------------------
# Docker-бэкенд в реестре
# ---------------------------------------------------------------------------

def docker_project(path="/docker/proj"):
    return Project(id=3, name="d", path=path, backend="docker", conn=None,
                   claude_cmd=None, created_at=0.0)


def make_with_docker():
    """Реестр со всеми тремя фабриками-заглушками (без реального Docker/SSH)."""
    made = []

    def local_factory():
        b = FakeBackend("local")
        made.append(b)
        return b

    def ssh_factory(conn):
        b = FakeBackend(f"ssh|{conn['user']}@{conn['host']}:{conn['port']}")
        made.append(b)
        return b

    def docker_factory(project):
        b = FakeBackend(f"docker||{project.path}")
        made.append(b)
        return b

    reg = BackendRegistry(
        claude_cmd="claude",
        local_factory=local_factory,
        ssh_factory=ssh_factory,
        docker_factory=docker_factory,
    )
    return reg, made


def test_key_for_docker_project():
    """key_for для docker-проекта = 'docker||<path>'."""
    reg, _ = make_with_docker()
    p = docker_project("/docker/myapp")
    assert reg.key_for(p) == "docker||/docker/myapp"


def test_docker_projects_different_paths_get_different_backends():
    """Два docker-проекта с разными путями → разные бэкенды."""
    reg, made = make_with_docker()
    b1 = reg.get(docker_project("/docker/proj1"))
    b2 = reg.get(docker_project("/docker/proj2"))
    assert b1 is not b2
    assert len(made) == 2


def test_docker_projects_same_path_cached():
    """Один путь → один бэкенд (кеш работает)."""
    reg, made = make_with_docker()
    b1 = reg.get(docker_project("/docker/proj"))
    b2 = reg.get(docker_project("/docker/proj"))
    assert b1 is b2
    assert len(made) == 1


def test_docker_unknown_backend_still_raises():
    """unknown backend по-прежнему бросает ValueError при наличии docker_factory."""
    reg, _ = make_with_docker()
    p = docker_project()
    p.backend = "podman"
    with pytest.raises(ValueError, match="podman"):
        reg.get(p)


def test_local_and_ssh_keys_unchanged_with_docker_factory():
    """Добавление docker_factory не ломает local/ssh key_for (регрессия)."""
    reg, _ = make_with_docker()
    assert reg.key_for(local()) == "local"
    assert reg.key_for(ssh()) == "ssh|root@srv:22"


def test_local_ssh_docker_all_coexist():
    """Все три типа бэкендов создаются и кешируются независимо."""
    reg, made = make_with_docker()
    bl = reg.get(local())
    bs = reg.get(ssh())
    bd = reg.get(docker_project())
    assert bl is not bs
    assert bs is not bd
    assert bd is not bl
    assert len(made) == 3
