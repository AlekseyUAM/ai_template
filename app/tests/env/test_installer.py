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


def test_install_writes_config_and_registers(tmp_path):
    registered = []
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=registered.append,
        dump_cf=False, dump_cfe=False, run=ok_run))
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


def test_install_runs_dumps_when_requested(tmp_path):
    calls = []
    def run(args, **kw):
        calls.append(args)
        return ok_run(args)
    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=True, dump_cfe=True, run=run))
    dump_calls = [c for c in calls if "/DumpConfigToFiles" in c]
    assert len(dump_calls) == 2       # cf и cfe


def test_install_tools_step_optional(tmp_path):
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, install_tools=True, run=ok_run))
    assert any(e.step == "tools-install" and e.status == "ok" for e in events)

    events2 = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, run=ok_run))
    assert not any(e.step == "tools-install" for e in events2)


def test_git_commit_step_on_create(tmp_path):
    """При создании с git_init=True выполняется шаг git-commit."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=True, run=ok_run))
    assert any(e.step == "git-commit" and e.status == "ok" for e in events)
    # git-commit идёт перед register
    names = [e.step for e in events if e.status == "ok"]
    assert names.index("git-commit") < names.index("register")


def test_git_commit_step_skipped_on_update(tmp_path):
    """При обновлении окружения шаг git-commit не выполняется."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=True, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=True, run=ok_run))
    assert not any(e.step == "git-commit" for e in events)


def test_git_commit_step_skipped_when_git_init_false(tmp_path):
    """git_init=False: шаг git-commit не выполняется."""
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False, run=ok_run))
    assert not any(e.step == "git-commit" for e in events)


def test_git_init_false_skips_git(tmp_path):
    """git_init=False: .1c-devbase.json пишется, но git init не запускается."""
    called = []
    def spy_run(args, **kw):
        called.append(args)
        return ok_run(args)

    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False, run=spy_run))

    # .1c-devbase.json должен быть написан
    assert (tmp_path / ".1c-devbase.json").exists()
    # git init не должен вызываться
    git_calls = [a for a in called if a and a[0] == "git" and "init" in a]
    assert git_calls == [], f"git init не должен вызываться, но вызван: {git_calls}"
    # git в корне проекта не должен быть создан (при ok_run он не создаётся сам)
    assert not (tmp_path / ".git").exists()


def test_update_does_not_touch_readme_mcp_dumps_git(tmp_path):
    """Обновление версии окружения: README, .mcp.json не трогаем, дампы и git init не делаем."""
    calls = []
    def spy_run(args, **kw):
        calls.append(args)
        return ok_run(args)

    # Исходная установка проекта.
    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=False, dump_cfe=False, git_init=False, run=spy_run))

    # Пользователь поправил README, .mcp.json и .1c-devbase.json вручную.
    (tmp_path / "README.md").write_text("мой readme\n", encoding="utf-8")
    (tmp_path / ".mcp.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".1c-devbase.json").write_text("мой devbase\n", encoding="utf-8")
    calls.clear()

    # Обновление окружения — даже если запрошены дампы, они не должны выполниться.
    events = list(installer.install_environment(
        cfg(tmp_path), update=True, register=lambda c: None,
        dump_cf=True, dump_cfe=True, run=spy_run))

    # README и .mcp.json не тронуты (и бэкапов нет).
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "мой readme\n"
    assert not (tmp_path / "README.md.bak").exists()
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{}\n"
    assert (tmp_path / ".1c-devbase.json").read_text(encoding="utf-8") == "мой devbase\n"
    # Шаги mcp/prepare-src и выгрузки не выполнялись.
    assert not any(e.step == "mcp" for e in events)
    assert not any(e.step == "prepare-src" for e in events)
    assert not any(e.step in ("dump-cf", "dump-cfe") for e in events)
    assert not any("/DumpConfigToFiles" in c for c in calls)
    # git init не вызывался.
    assert not any(c and c[0] == "git" and "init" in c for c in calls)
    # Но контент шаблона обновлён.
    assert any(e.step == "content" and e.status == "ok" for e in events)


def test_install_stops_on_dump_error(tmp_path):
    def run(args, **kw):
        class R:
            returncode = 1
            stderr = "нет платформы"
        return R()
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=True, dump_cfe=False, run=run))
    assert events[-1].status == "error"
    assert "нет платформы" in events[-1].detail
