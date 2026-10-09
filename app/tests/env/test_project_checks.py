from agentmon.env import project_checks as pc

def test_is_empty_dir_nonexistent(tmp_path):
    """Несуществующий каталог считается пустым (ок)."""
    target = tmp_path / "newproj"
    assert pc.is_empty_dir(str(target)) is True

def test_is_empty_dir_empty(tmp_path):
    """Существующий пустой каталог — ок."""
    target = tmp_path / "newproj"
    target.mkdir()
    assert pc.is_empty_dir(str(target)) is True

def test_is_empty_dir_nonempty(tmp_path):
    """Непустой каталог — не ок."""
    target = tmp_path / "newproj"
    target.mkdir()
    (target / "file.txt").write_text("x")
    assert pc.is_empty_dir(str(target)) is False

def test_is_empty_dir_regular_file(tmp_path):
    """Обычный файл по пути (не каталог) — не ок."""
    file = tmp_path / "notadir.txt"
    file.write_text("content")
    assert pc.is_empty_dir(str(file)) is False

def test_validate_name():
    assert pc.validate_name("demo")[0] is True
    assert pc.validate_name("2bad")[0] is False
    assert pc.validate_name("import")[0] is False      # ключевое слово
    assert pc.validate_name("with space")[0] is False

def test_requirements_structure():
    reqs = pc.requirements()
    names = {r["name"] for r in reqs}
    assert {"python3", "git", "claude", "node"} <= names
    assert "docker" not in names   # docker не нужен при установке проекта
    assert all(set(r) >= {"name", "ok", "detail"} for r in reqs)


def test_requirements_git_bash_on_windows(monkeypatch):
    """git bash добавляется в требования только на Windows."""
    import agentmon.env.project_checks as mod

    # Заглушка which, чтобы не триггерить win32-ветку реального shutil на Linux.
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/fake/" + name)

    monkeypatch.setattr(mod.sys, "platform", "win32")
    names = {r["name"] for r in pc.requirements()}
    assert "git bash" in names

    monkeypatch.setattr(mod.sys, "platform", "linux")
    names = {r["name"] for r in pc.requirements()}
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
        platform_dir="/opt/1c/platform",
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
        platform_dir="/opt/1c/platform", db_connection="File=/data/base",
        db_kind="file", out_log="/tmp/c.log")
    assert "/N" not in cmd and "/P" not in cmd


def test_build_check_db_command_file():
    cmd = pc.build_check_db_command(
        platform_dir="/opt/1c/platform",
        db_connection="File=/data/base", db_kind="file", out_log="/tmp/c.log")
    assert "/F" in cmd and cmd[cmd.index("/F") + 1] == "/data/base"


def test_check_db_requires_platform():
    res = pc.check_db(platform_dir="", db_connection="File=/b")
    assert res["ok"] is False and "платформ" in res["log"].lower()


def test_check_db_binary_not_found(tmp_path):
    res = pc.check_db(platform_dir=str(tmp_path), db_connection="File=/b")
    assert res["ok"] is False and "1cv8" in res["log"]


def test_check_db_success(tmp_path):
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0; stdout = "OK"; stderr = ""
        return R()
    res = pc.check_db(platform_dir=_fake_platform(tmp_path),
                      db_connection="Srvr=host;Ref=base", user="admin",
                      password="secret", run=fake_run)
    assert res["ok"] is True


def test_check_db_failure(tmp_path):
    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1; stdout = ""; stderr = "connection failed"
        return R()
    res = pc.check_db(platform_dir=_fake_platform(tmp_path),
                      db_connection="Srvr=host;Ref=base", user="admin",
                      password="secret", run=fake_run)
    assert res["ok"] is False
    assert "connection failed" in res["log"]
