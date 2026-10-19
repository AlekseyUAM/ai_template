from agentmon.backends import RunResult
from agentmon.backends.local import LocalProvisioner
from agentmon.env.config_schema import EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION
from agentmon.env import installer


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="",
        mcp=[McpSelection("code-index", True, "managed")],
        agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


def ok_run(args, **kw):
    class R:
        returncode = 0
        stderr = ""
    return R()


class SpyProv(LocalProvisioner):
    """LocalProvisioner, перехватывающий только DESIGNER-вызовы (dump).

    Вызовы с `/DumpConfigToFiles` перехватываются и возвращают scripted result.
    Остальные (git, pip, …) делегируются в LocalProvisioner.
    """

    def __init__(self, dump_returncode=0, dump_stderr=""):
        self.run_calls: list[list] = []
        self._dump_returncode = dump_returncode
        self._dump_stderr = dump_stderr

    def run(self, cmd, cwd=None, timeout=None) -> RunResult:
        self.run_calls.append(list(cmd))
        if "/DumpConfigToFiles" in cmd:
            return RunResult(self._dump_returncode, "", self._dump_stderr)
        return super().run(cmd, cwd=cwd, timeout=timeout)


def test_install_writes_config_and_registers(tmp_path):
    registered = []
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=registered.append,
        dump_cf=False, dump_cfe=False))
    # ai1c.config.json больше не генерируется — источник истины БД
    assert not (tmp_path / "ai1c.config.json").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / ".claude" / "agents" / "developer.md").exists()
    assert (tmp_path / ".claude" / "hooks" / "bsl_nudge.py").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert any(e.step == "content" and e.status == "ok" for e in events)
    assert len(registered) == 1
    assert events[-1].status == "ok"
    assert any(e.step == "register" and e.status == "ok" for e in events)
    assert (tmp_path / ".1c-devbase.json").exists()
    assert any(e.step == "prepare-src" and e.status == "ok" for e in events)


def test_venv_step_warns_on_pip_failure(tmp_path):
    """Сбой pip при подъёме .venv даёт статус "warn", но не валит установку."""
    from agentmon.backends import RunResult
    from agentmon.backends.local import LocalProvisioner

    class PipFailProv(LocalProvisioner):
        def run(self, cmd, cwd=None):
            if "pip" in cmd:
                return RunResult(returncode=1, stderr="pip error")
            return super().run(cmd, cwd=cwd)

    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, prov=PipFailProv()))
    venv = [e for e in events if e.step == "venv"]
    assert any(e.status == "warn" and "setup-venv.py" in e.detail for e in venv)
    # предупреждение не прерывает установку — register всё равно ok
    assert events[-1].status == "ok"
    assert any(e.step == "register" and e.status == "ok" for e in events)


def test_venv_step_ok_on_success(tmp_path):
    """Успешный подъём .venv → шаг venv со статусом "ok"."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False))
    assert any(e.step == "venv" and e.status == "ok" for e in events)


def test_install_runs_dumps_when_requested(tmp_path):
    prov = SpyProv(dump_returncode=0)
    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=True, dump_cfe=True, prov=prov))
    dump_calls = [c for c in prov.run_calls if "/DumpConfigToFiles" in c]
    assert len(dump_calls) == 2       # cf и cfe


def test_install_tools_step_optional(tmp_path):
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, install_tools=True))
    assert any(e.step == "tools-install" and e.status == "ok" for e in events)

    events2 = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False))
    assert not any(e.step == "tools-install" for e in events2)


def test_git_commit_step_on_create(tmp_path):
    """При создании с git_init=True выполняется шаг git-commit."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=True))
    assert any(e.step == "git-commit" and e.status == "ok" for e in events)
    # git-commit идёт перед register
    names = [e.step for e in events if e.status == "ok"]
    assert names.index("git-commit") < names.index("register")


def test_git_commit_step_skipped_on_update(tmp_path):
    """При обновлении окружения шаг git-commit не выполняется."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=True, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=True))
    assert not any(e.step == "git-commit" for e in events)


def test_git_commit_step_skipped_when_git_init_false(tmp_path):
    """git_init=False: шаг git-commit не выполняется."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False))
    assert not any(e.step == "git-commit" for e in events)


def test_git_init_false_skips_git(tmp_path):
    """git_init=False: .1c-devbase.json пишется, но git init не запускается."""
    # Используем SpyProv: перехватывает все run-вызовы через провайдер.
    prov = SpyProv()

    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False, prov=prov))

    # .1c-devbase.json должен быть написан
    assert (tmp_path / ".1c-devbase.json").exists()
    # git init не должен вызываться через prov.run
    git_calls = [c for c in prov.run_calls if c and c[0] == "git" and "init" in c]
    assert git_calls == [], f"git init не должен вызываться, но вызван: {git_calls}"
    # git в корне проекта не должен быть создан
    assert not (tmp_path / ".git").exists()


def test_update_does_not_touch_readme_mcp_dumps_git(tmp_path):
    """Обновление версии окружения: README, .mcp.json не трогаем, дампы и git init не делаем."""
    prov = SpyProv()

    # Исходная установка проекта.
    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False, prov=prov))

    # Пользователь поправил README, .mcp.json и .1c-devbase.json вручную.
    (tmp_path / "README.md").write_text("мой readme\n", encoding="utf-8")
    (tmp_path / ".mcp.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".1c-devbase.json").write_text("мой devbase\n", encoding="utf-8")
    prov.run_calls.clear()

    # Обновление окружения — даже если запрошены дампы, они не должны выполниться.
    events = list(installer.install_environment(
        cfg(tmp_path), update=True, register=lambda c: None,
        dump_cf=True, dump_cfe=True, prov=prov))

    # README и .mcp.json не тронуты (и бэкапов нет).
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "мой readme\n"
    assert not (tmp_path / "README.md.bak").exists()
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{}\n"
    assert (tmp_path / ".1c-devbase.json").read_text(encoding="utf-8") == "мой devbase\n"
    # Шаги mcp/prepare-src и выгрузки не выполнялись.
    assert not any(e.step == "mcp" for e in events)
    assert not any(e.step == "prepare-src" for e in events)
    assert not any(e.step in ("dump-cf", "dump-cfe") for e in events)
    assert not any("/DumpConfigToFiles" in c for c in prov.run_calls)
    # git init не вызывался.
    assert not any(c and c[0] == "git" and "init" in c for c in prov.run_calls)
    # Но контент шаблона обновлён.
    assert any(e.step == "content" and e.status == "ok" for e in events)


def test_install_stops_on_dump_error(tmp_path):
    # SpyProv перехватывает DESIGNER-вызовы: rc=1, stderr="нет платформы".
    # Чтобы не ждать 900с реального sleep, патчим installer.dump — он берётся
    # из модульного импорта, поэтому lambda в install_environment увидит патч.
    original_dump = installer.dump

    def fast_dump(config, kind, **kw):
        kw.setdefault("max_wait", 0)
        kw.setdefault("sleep", lambda _s: None)
        return original_dump(config, kind, **kw)

    installer.dump = fast_dump
    try:
        prov = SpyProv(dump_returncode=1, dump_stderr="нет платформы")
        events = list(installer.install_environment(
            cfg(tmp_path), update=False, register=lambda c: None,
            dump_cf=True, dump_cfe=False, prov=prov))
    finally:
        installer.dump = original_dump

    assert events[-1].status == "error"
    assert "нет платформы" in events[-1].detail
