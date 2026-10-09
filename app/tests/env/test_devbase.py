import json
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.env import devbase


def cfg(tmp_path, kind="file", conn="/base/demo"):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir="/opt/1cv8",
        platform_version="8.3.27.1786", db_kind=kind, db_connection=conn,
        web_publication="", mcp=[], agents=[])


def test_git_init_creates_repo(tmp_path):
    devbase.git_init_project(tmp_path)          # real git, в корне проекта
    assert (tmp_path / ".git").exists()
    assert (tmp_path / ".gitignore").exists()


def test_git_init_idempotent(tmp_path):
    devbase.git_init_project(tmp_path)
    devbase.git_init_project(tmp_path)          # second call must not fail


def test_git_init_sets_user_config(tmp_path):
    import subprocess
    from types import SimpleNamespace
    cfg = SimpleNamespace(developer_id="dev1", developer_email="dev@example.com")
    devbase.git_init_project(tmp_path, config=cfg)
    name = subprocess.run(["git", "config", "user.name"], cwd=str(tmp_path),
                          capture_output=True, text=True).stdout.strip()
    email = subprocess.run(["git", "config", "user.email"], cwd=str(tmp_path),
                           capture_output=True, text=True).stdout.strip()
    assert name == "dev1" and email == "dev@example.com"


def _R(returncode=0, stdout="", stderr=""):
    class R:
        pass
    R.returncode = returncode
    R.stdout = stdout
    R.stderr = stderr
    return R


def test_git_commit_all_add_and_commit(tmp_path):
    from types import SimpleNamespace
    calls = []
    def rec(args, **kw):
        calls.append(args)
        return _R()
    cfg = SimpleNamespace(developer_id="dev1", developer_email="dev@example.com")
    devbase.git_commit_all(tmp_path, "init", config=cfg, run=rec)
    # первый вызов — git add .
    assert calls[0] == ["git", "add", "."]
    # второй — git commit с инлайновой идентичностью и -m init
    commit = calls[1]
    assert "commit" in commit and "-m" in commit
    assert commit[commit.index("-m") + 1] == "init"
    assert "-c" in commit
    assert "user.name=dev1" in commit and "user.email=dev@example.com" in commit


def test_git_commit_all_identity_fallback(tmp_path):
    calls = []
    def rec(args, **kw):
        calls.append(args)
        return _R()
    devbase.git_commit_all(tmp_path, run=rec)   # config=None → запасная идентичность
    commit = calls[1]
    assert "user.name=ai1c" in commit and "user.email=ai1c@local" in commit


def test_git_commit_all_nothing_to_commit_ok(tmp_path):
    def rec(args, **kw):
        if "commit" in args:
            return _R(returncode=1, stdout="nothing to commit, working tree clean")
        return _R()
    # не должно бросать исключение
    devbase.git_commit_all(tmp_path, run=rec)


def test_git_commit_all_other_failure_raises(tmp_path):
    import pytest
    def rec(args, **kw):
        if "commit" in args:
            return _R(returncode=1, stderr="фатальная ошибка")
        return _R()
    with pytest.raises(RuntimeError):
        devbase.git_commit_all(tmp_path, run=rec)


def test_write_devbase_file(tmp_path):
    devbase.write_devbase(cfg(tmp_path))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["cf_dir"] == "src/cf" and data["cfe_dir"] == "src/cfe"
    assert data["connection"] == {"type": "file", "path": "/base/demo"}


def test_write_devbase_server(tmp_path):
    devbase.write_devbase(cfg(tmp_path, kind="server", conn="srv:1541/base"))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["connection"] == {"type": "server", "server": "srv:1541", "base": "base"}


def test_write_devbase_server_srvr_ref_format(tmp_path):
    devbase.write_devbase(cfg(tmp_path, kind="server", conn="Srvr=host;Ref=base"))
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["connection"] == {"type": "server", "server": "host", "base": "base"}


def test_write_devbase_file_strips_prefix_and_credentials(tmp_path):
    devbase.write_devbase(cfg(tmp_path, kind="file", conn="File=/data/base"),
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
    devbase.write_devbase(c)
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
    devbase.write_devbase(c)
    data = json.loads((tmp_path / ".1c-devbase.json").read_text(encoding="utf-8"))
    assert data["platform_path"] == str(tmp_path / "1cv8")
