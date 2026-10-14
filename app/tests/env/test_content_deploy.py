# app/tests/env/test_content_deploy.py
from pathlib import Path
from agentmon.env.config_schema import EnvConfig, AgentModel, SCHEMA_VERSION, McpSelection
from agentmon.env import content


def cfg(tmp_path, agents):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="iv", developer_email="iv@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="", mcp=[], agents=agents,
    )


def test_deploy_copies_content(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    c = tmp_path / ".claude"
    assert (c / "agents" / "developer.md").exists()
    assert (c / "skills" / "mcp-usage" / "SKILL.md").exists()
    assert (c / "rules" / "task-artifacts.md").exists()
    assert (c / "hooks" / "bsl_nudge.py").exists()
    assert (c / "settings.json").exists()
    assert not (tmp_path / "CLAUDE.md").exists()   # CLAUDE.md больше не генерируется


def test_deploy_copies_whole_template_tree(tmp_path):
    # template — источник истины: любой добавленный файл/каталог шаблона
    # должен оказаться в созданном проекте (напр. logs/, .claude/VERSION).
    content.deploy_content(cfg(tmp_path, []), update=False)
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "logs" / ".gitkeep").exists()
    assert (tmp_path / ".claude" / "VERSION").exists()


def test_deploy_writes_project_readme(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("## demo")
    assert "setup-venv.py" in readme   # как переподнять .venv на свежем клоне


def test_agent_model_effort_rendered(tmp_path):
    agents = [AgentModel("developer", "claude-opus-4-8", "high")]
    content.deploy_content(cfg(tmp_path, agents), update=False)
    text = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "{{MODEL}}" not in text and "{{EFFORT}}" not in text
    assert "claude-opus-4-8" in text and "high" in text


def test_agent_without_config_gets_default(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    text = (tmp_path / ".claude" / "agents" / "analyst.md").read_text(encoding="utf-8")
    assert "{{MODEL}}" not in text


def test_update_leaves_readme_untouched(tmp_path):
    # При обновлении версии окружения README проекта не трогаем вовсе.
    content.deploy_content(cfg(tmp_path, []), update=False)
    (tmp_path / "README.md").write_text("мой текст\n", encoding="utf-8")
    content.deploy_content(cfg(tmp_path, []), update=True)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "мой текст\n"
    assert not (tmp_path / "README.md.bak").exists()


def test_settings_registers_hook(tmp_path):
    import json
    content.deploy_content(cfg(tmp_path, []), update=False)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "bsl_nudge.py" in cmd


def test_copy_tree_handles_binary(tmp_path):
    # place a binary file into a copy of the skills tree path is internal;
    # instead verify deploy still works and a known text skill lands intact
    content.deploy_content(cfg(tmp_path, []), update=False)
    skill = (tmp_path / ".claude" / "skills" / "mcp-usage" / "SKILL.md").read_bytes()
    assert b"mcp-usage" in skill


def test_copy_tree_binary_safe(tmp_path):
    src = tmp_path / "src"; (src / "sub").mkdir(parents=True)
    (src / "sub" / "bin.dat").write_bytes(b"\x00\x01\x02\xff")
    (src / "sub" / "__pycache__").mkdir()
    (src / "sub" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    dst = tmp_path / "dst"
    content._copy_tree(src, dst)
    assert (dst / "sub" / "bin.dat").read_bytes() == b"\x00\x01\x02\xff"
    assert not (dst / "sub" / "__pycache__").exists()


def _bsl_renamed():
    return [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]


def test_deploy_substitutes_selected_mcp_name(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(config, update=False)
    c = tmp_path / ".claude"

    dev = (c / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_checker__" in dev
    assert "mcp__bsl_ls__" not in dev

    settings = (c / "settings.json").read_text(encoding="utf-8")
    assert "mcp__bsl_checker" in settings
    assert "mcp__bsl_ls" not in settings

    skill = (c / "skills" / "mcp-usage" / "SKILL.md").read_text(encoding="utf-8")
    assert "bsl_checker" in skill
    assert "bsl_ls" not in skill


def test_deploy_leaves_unselected_placeholder(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()   # code-index НЕ выбран
    content.deploy_content(config, update=False)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__code_index__" in dev


def test_deploy_update_skips_mcp_substitution(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(config, update=True)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_ls__" in dev
    assert "bsl_checker" not in dev


def test_deploy_no_overrides_when_default_name(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    content.deploy_content(config, update=False)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_ls__" in dev


# --- интерпретатор .venv впечатывается в вызовы (фикс кроссплатформенности #2) ---

def test_hook_command_points_to_project_venv(tmp_path):
    import json
    content.deploy_content(cfg(tmp_path, []), update=False)
    # settings.json остаётся валидным JSON, а команда хука зовёт интерпретатор .venv
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    py = content.venv_python(tmp_path).as_posix()
    for evt in ("PostToolUse", "UserPromptSubmit"):
        cmd = data["hooks"][evt][0]["hooks"][0]["command"]
        assert cmd.startswith(f'"{py}" ')          # абсолютный путь, не голый python
        assert "python" not in cmd.replace(py, "")  # кроме как в составе пути venv


def test_skill_docs_use_venv_python(tmp_path):
    content.deploy_content(cfg(tmp_path, []), update=False)
    py = content.venv_python(tmp_path).as_posix()
    skills = tmp_path / ".claude" / "skills"
    import re
    bare = re.compile(r"\bpython (?=[\"'.$\\-])")
    for md in skills.rglob("SKILL.md"):
        text = md.read_text(encoding="utf-8")
        # ни одного голого вызова python не осталось (кроме как в составе пути venv)
        assert not bare.search(text.replace(py, "")), f"голый python остался в {md}"


def test_deploy_does_not_create_venv(tmp_path):
    # Сам деплой — только текст; .venv поднимается отдельным шагом provision_venv.
    content.deploy_content(cfg(tmp_path, []), update=False)
    assert not (tmp_path / ".venv").exists()


def test_deploy_ships_venv_entrypoint(tmp_path):
    # На свежем клоне .venv переподнимается setup-venv.py + requirements.txt.
    content.deploy_content(cfg(tmp_path, []), update=False)
    assert (tmp_path / "setup-venv.py").exists()
    assert (tmp_path / "requirements.txt").exists()
    assert ".venv" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_provision_venv_builds_and_installs(tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        class R:
            returncode = 0
        return R()

    content.provision_venv(cfg(tmp_path, []), update=False, run=fake_run)
    # 1) создание venv интерпретатором agentmon, 2) pip install -r requirements.txt
    assert calls[0][1:3] == ["-m", "venv"]
    assert str(tmp_path / ".venv") in calls[0]
    assert calls[1][1:5] == ["-m", "pip", "install", "-r"]
    assert calls[1][-1].endswith("requirements.txt")


def test_provision_venv_warns_on_pip_failure(tmp_path, capsys):
    import subprocess

    def fake_run(cmd, **kwargs):
        if "pip" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        class R:
            returncode = 0
        return R()

    # не должно бросать — создание проекта не блокируется сбоем pip
    content.provision_venv(cfg(tmp_path, []), update=False, run=fake_run)
    err = capsys.readouterr().err
    assert "venv" in err and "requirements.txt" in err
