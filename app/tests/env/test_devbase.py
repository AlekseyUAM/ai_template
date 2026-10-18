import json
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.env import devbase
from agentmon.backends.local import LocalProvisioner
from agentmon.backends import RunResult


def cfg(tmp_path, kind="file", conn="/base/demo"):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir="/opt/1cv8",
        platform_version="8.3.27.1786", db_kind=kind, db_connection=conn,
        web_publication="", mcp=[], agents=[])


class FakeProv:
    """Мини-Provisioner: записывает вызовы run(); возвращает заданный RunResult."""

    def __init__(self, run_fn=None):
        self.calls = []          # list of (args, cwd)
        self._run_fn = run_fn    # callable(args, cwd) -> RunResult; None → ok

    def run(self, cmd, cwd=None):
        self.calls.append((list(cmd), cwd))
        if self._run_fn is not None:
            return self._run_fn(cmd, cwd)
        return RunResult(0)

    # Заглушки для методов, которые могут вызываться
    def mkdirs(self, paths):
        pass

    def exists(self, path):
        return False

    def is_file(self, path):
        return False

    def write_text(self, path, content):
        pass


def test_git_init_creates_repo(tmp_path):
    devbase.git_init_project(LocalProvisioner(), str(tmp_path))   # real git
    assert (tmp_path / ".git").exists()
    assert (tmp_path / ".gitignore").exists()


def test_git_init_idempotent(tmp_path):
    devbase.git_init_project(LocalProvisioner(), str(tmp_path))
    devbase.git_init_project(LocalProvisioner(), str(tmp_path))   # second call must not fail


def test_git_init_sets_user_config(tmp_path):
    import subprocess
    from types import SimpleNamespace
    c = SimpleNamespace(developer_id="dev1", developer_email="dev@example.com")
    devbase.git_init_project(LocalProvisioner(), str(tmp_path), config=c)
    name = subprocess.run(["git", "config", "user.name"], cwd=str(tmp_path),
                          capture_output=True, text=True).stdout.strip()
    email = subprocess.run(["git", "config", "user.email"], cwd=str(tmp_path),
                           capture_output=True, text=True).stdout.strip()
    assert name == "dev1" and email == "dev@example.com"


def test_git_commit_all_add_and_commit(tmp_path):
    from types import SimpleNamespace
    prov = FakeProv()
    c = SimpleNamespace(developer_id="dev1", developer_email="dev@example.com")
    devbase.git_commit_all(prov, str(tmp_path), "init", config=c)
    calls = [args for args, _ in prov.calls]
    # первый вызов — git add .
    assert calls[0] == ["git", "add", "."]
    # второй — git commit с инлайновой идентичностью и -m init
    commit = calls[1]
    assert "commit" in commit and "-m" in commit
    assert commit[commit.index("-m") + 1] == "init"
    assert "-c" in commit
    assert "user.name=dev1" in commit and "user.email=dev@example.com" in commit


def test_git_commit_all_identity_fallback(tmp_path):
    prov = FakeProv()
    devbase.git_commit_all(prov, str(tmp_path))   # config=None → запасная идентичность
    calls = [args for args, _ in prov.calls]
    commit = calls[1]
    assert "user.name=ai1c" in commit and "user.email=ai1c@local" in commit


def test_git_commit_all_nothing_to_commit_ok(tmp_path):
    def run_fn(args, cwd):
        if "commit" in args:
            return RunResult(1, stdout="nothing to commit, working tree clean")
        return RunResult(0)
    prov = FakeProv(run_fn=run_fn)
    # не должно бросать исключение
    devbase.git_commit_all(prov, str(tmp_path))


def test_git_commit_all_other_failure_raises(tmp_path):
    import pytest
    def run_fn(args, cwd):
        if "commit" in args:
            return RunResult(1, stderr="фатальная ошибка")
        return RunResult(0)
    prov = FakeProv(run_fn=run_fn)
    with pytest.raises(RuntimeError):
        devbase.git_commit_all(prov, str(tmp_path))


def test_write_devbase_file(tmp_path):
    devbase.write_devbase(LocalProvisioner(), cfg(tmp_path))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["cf_dir"] == "src/cf" and data["cfe_dir"] == "src/cfe"
    assert data["connection"] == {"type": "file", "path": "/base/demo"}


def test_write_devbase_server(tmp_path):
    devbase.write_devbase(LocalProvisioner(), cfg(tmp_path, kind="server", conn="srv:1541/base"))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["connection"] == {"type": "server", "server": "srv:1541", "base": "base"}


def test_write_devbase_server_srvr_ref_format(tmp_path):
    devbase.write_devbase(LocalProvisioner(), cfg(tmp_path, kind="server", conn="Srvr=host;Ref=base"))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["connection"] == {"type": "server", "server": "host", "base": "base"}


def test_write_devbase_file_strips_prefix_and_credentials(tmp_path):
    devbase.write_devbase(LocalProvisioner(), cfg(tmp_path, kind="file", conn="File=/data/base"),
                          user="Администратор", password="pwd")
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["connection"] == {"type": "file", "path": "/data/base"}
    assert data["user"] == "Администратор" and data["password"] == "pwd"


def test_platform_path_dir_without_binary(tmp_path):
    from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
    c = EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir="/opt/1cv8",
        platform_version="8.3.27.1786", db_kind="file", db_connection="/base/demo",
        web_publication="", mcp=[], agents=[])
    devbase.write_devbase(LocalProvisioner(), c)
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["platform_path"] == ""


def test_platform_path_binary_file(tmp_path):
    from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
    bin_path = tmp_path / "1cv8"
    bin_path.write_text("stub")
    c = EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir=str(tmp_path),
        platform_version="8.3.27.1786", db_kind="file", db_connection="/base/demo",
        web_publication="", mcp=[], agents=[])
    devbase.write_devbase(LocalProvisioner(), c)
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["platform_path"] == str(tmp_path / "1cv8")
