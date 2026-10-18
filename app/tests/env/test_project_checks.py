from agentmon.backends import RunResult
from agentmon.backends.local import LocalProvisioner
from agentmon.env import project_checks as pc


class FakeProv:
    def __init__(self, exists=None, which_map=None, run_result=None,
                 empty=True, files=None):
        self._exists = set(exists or [])
        self._files = set(files or [])
        self._which = which_map or {}
        self._run_result = run_result or RunResult(0, "", "")
        self._empty = empty
        self.run_calls = []

    def exists(self, path):
        return path in self._exists

    def is_file(self, path):
        return path in self._files

    def is_empty_dir(self, path):
        return self._empty

    def which(self, tool):
        return self._which.get(tool)

    def run(self, cmd, cwd=None):
        self.run_calls.append(cmd)
        return self._run_result

    def tempdir(self):
        return "/tmp"


def test_is_empty_dir_delegates_to_prov():
    prov = FakeProv(empty=False)
    assert pc.is_empty_dir(prov, "/srv/x") is False


def test_requirements_uses_prov_which():
    prov = FakeProv(which_map={"git": "/usr/bin/git"})
    rows = pc.requirements(prov)
    names = {r["name"]: r["ok"] for r in rows}
    assert names["git"] is True
    assert names["claude"] is False


def test_platform_binary_found_via_prov_exists():
    prov = FakeProv(exists={"/opt/1cv8/1cv8"})
    assert pc.platform_binary(prov, "/opt/1cv8") == "/opt/1cv8/1cv8"


def test_check_db_runs_designer_via_prov():
    prov = FakeProv(exists={"/opt/1cv8/1cv8"}, run_result=RunResult(0, "", ""))
    res = pc.check_db(prov, platform_dir="/opt/1cv8",
                      db_connection='srvr="s";ref="base"', db_kind="server")
    assert res["ok"] is True
    assert prov.run_calls and "DESIGNER" in prov.run_calls[0]


def test_check_db_dir_not_binary():
    """Каталог платформы существует, но 1cv8 внутри нет — binary не найден,
    prov.run не вызывается (исключает PermissionError при попытке exec каталога)."""
    prov = FakeProv(exists={"/opt/1cv8"})  # каталог существует, дочерних 1cv8 нет
    res = pc.check_db(prov, platform_dir="/opt/1cv8", db_connection="File=/b")
    assert res["ok"] is False
    assert "1cv8" in res["log"]
    assert not prov.run_calls


def test_is_empty_dir_nonexistent(tmp_path):
    """Несуществующий каталог считается пустым (ок)."""
    target = tmp_path / "newproj"
    prov = LocalProvisioner()
    assert pc.is_empty_dir(prov, str(target)) is True

def test_is_empty_dir_empty(tmp_path):
    """Существующий пустой каталог — ок."""
    target = tmp_path / "newproj"
    target.mkdir()
    prov = LocalProvisioner()
    assert pc.is_empty_dir(prov, str(target)) is True

def test_is_empty_dir_nonempty(tmp_path):
    """Непустой каталог — не ок."""
    target = tmp_path / "newproj"
    target.mkdir()
    (target / "file.txt").write_text("x")
    prov = LocalProvisioner()
    assert pc.is_empty_dir(prov, str(target)) is False

def test_is_empty_dir_regular_file(tmp_path):
    """Обычный файл по пути (не каталог) — не ок."""
    file = tmp_path / "notadir.txt"
    file.write_text("content")
    prov = LocalProvisioner()
    assert pc.is_empty_dir(prov, str(file)) is False

def test_validate_name():
    assert pc.validate_name("demo")[0] is True
    assert pc.validate_name("2bad")[0] is False
    assert pc.validate_name("import")[0] is False      # ключевое слово
    assert pc.validate_name("with space")[0] is False

def test_requirements_structure():
    prov = LocalProvisioner()
    reqs = pc.requirements(prov)
    names = {r["name"] for r in reqs}
    assert {"git", "claude", "node"} <= names
    assert "docker" not in names   # docker не нужен при установке проекта
    # python в PATH цели не требуется: скиллам разворачивается изолированный .venv
    assert "python3" not in names and "python" not in names
    assert all(set(r) >= {"name", "ok", "detail"} for r in reqs)


def test_requirements_git_bash_on_windows(monkeypatch):
    """git bash добавляется в требования только на Windows."""
    import agentmon.env.project_checks as mod

    prov = FakeProv(which_map={"git": "/fake/git", "claude": "/fake/claude",
                                "node": "/fake/node", "bash": "/fake/bash"})

    monkeypatch.setattr(mod.sys, "platform", "win32")
    names = {r["name"] for r in pc.requirements(prov)}
    assert "git bash" in names

    monkeypatch.setattr(mod.sys, "platform", "linux")
    names = {r["name"] for r in pc.requirements(prov)}
    assert "git bash" not in names


def test_infer_db_kind():
    assert pc.infer_db_kind("Srvr=host;Ref=base") == "server"
    assert pc.infer_db_kind("srvr=host;ref=base") == "server"
    assert pc.infer_db_kind("File=/data/base") == "file"
    assert pc.infer_db_kind("/data/base") == "file"
    assert pc.infer_db_kind("") == "file"


def test_current_env_version():
    assert pc.current_env_version().strip() != ""


def _fake_platform(tmp_path):
    """Создаёт каталог платформы с фиктивным исполняемым 1cv8/1cv8.exe."""
    import sys
    pdir = tmp_path / "1cv8"
    pdir.mkdir()
    name = "1cv8.exe" if sys.platform.startswith("win") else "1cv8"
    (pdir / name).write_text("", encoding="utf-8")
    return str(pdir)


def test_build_check_db_command_server():
    cmd = pc.build_check_db_command(
        "/opt/1c/platform/1cv8",
        db_connection="Srvr=host;Ref=base",
        user="admin", password="secret", db_kind="server", out_log="/tmp/c.log")
    assert cmd[0].endswith(("1cv8", "1cv8.exe"))
    assert "DESIGNER" in cmd and "/S" in cmd
    assert cmd[cmd.index("/S") + 1] == "host\\base"
    assert "/N" in cmd and "admin" in cmd
    assert "/DumpDBCfgList" in cmd and "-AllExtensions" in cmd
    assert "/Out" in cmd and "/tmp/c.log" in cmd


def test_auth_args_empty_omitted():
    assert pc.auth_args("", "") == []


def test_auth_args_user_with_empty_password_omits_p():
    # пустой пароль → только /N, без /P (пустой /P "" ломает 1cv8)
    assert pc.auth_args("Администратор", "") == ["/N", "Администратор"]


def test_auth_args_user_and_password():
    assert pc.auth_args("admin", "secret") == ["/N", "admin", "/P", "secret"]


def test_build_check_db_command_no_auth_omits_flags():
    cmd = pc.build_check_db_command(
        "/opt/1c/platform/1cv8", db_connection="File=/data/base",
        db_kind="file", out_log="/tmp/c.log")
    assert "/N" not in cmd and "/P" not in cmd


def test_build_check_db_command_file():
    cmd = pc.build_check_db_command(
        "/opt/1c/platform/1cv8",
        db_connection="File=/data/base", db_kind="file", out_log="/tmp/c.log")
    assert "/F" in cmd and cmd[cmd.index("/F") + 1] == "/data/base"


def test_check_db_requires_platform():
    prov = FakeProv()
    res = pc.check_db(prov, platform_dir="", db_connection="File=/b")
    assert res["ok"] is False and "платформ" in res["log"].lower()


def test_check_db_binary_not_found(tmp_path):
    # FakeProv: platform_dir does not exist and has no 1cv8 children → None from platform_binary
    prov = FakeProv(exists=set())
    res = pc.check_db(prov, platform_dir=str(tmp_path), db_connection="File=/b")
    assert res["ok"] is False and "1cv8" in res["log"]


def test_check_db_success(tmp_path):
    pdir = _fake_platform(tmp_path)
    prov = FakeProv(exists={pdir + "/1cv8"}, run_result=RunResult(0, "OK", ""))
    res = pc.check_db(prov, platform_dir=pdir,
                      db_connection="Srvr=host;Ref=base", user="admin",
                      password="secret")
    assert res["ok"] is True


def test_check_db_failure(tmp_path):
    pdir = _fake_platform(tmp_path)
    prov = FakeProv(exists={pdir + "/1cv8"},
                    run_result=RunResult(1, "", "connection failed"))
    res = pc.check_db(prov, platform_dir=pdir,
                      db_connection="Srvr=host;Ref=base", user="admin",
                      password="secret")
    assert res["ok"] is False
    assert "connection failed" in res["log"]
