# app/tests/env/test_content_deploy.py
import json
from pathlib import Path
import pytest
from agentmon.backends.local import LocalProvisioner
from agentmon.backends import RunResult
from agentmon.env.config_schema import EnvConfig, AgentModel, SCHEMA_VERSION, McpSelection
from agentmon.env import content


@pytest.fixture
def prov():
    return LocalProvisioner()


def cfg(tmp_path, agents):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="iv", developer_email="iv@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="", mcp=[], agents=agents,
    )


def test_deploy_copies_content(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    c = tmp_path / ".claude"
    assert (c / "checklists" / "developer.md").exists()
    assert (c / "skills" / "mcp-usage" / "SKILL.md").exists()
    assert (c / "rules" / "task-artifacts.md").exists()
    assert (c / "hooks" / "bsl_nudge.py").exists()
    assert (c / "settings.json").exists()
    assert (tmp_path / "CLAUDE.md").is_file()
    assert "Single-agent" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_deploy_copies_whole_template_tree(prov, tmp_path):
    # template — источник истины: любой добавленный файл/каталог шаблона
    # должен оказаться в созданном проекте (напр. logs/, .claude/VERSION).
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "logs" / ".gitkeep").exists()
    assert (tmp_path / ".claude" / "VERSION").exists()
    assert (tmp_path / ".claude" / "checklists" / "developer.md").exists()
    assert (tmp_path / "CLAUDE.md").is_file()


def test_deploy_writes_project_readme(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("## demo")
    assert "setup-venv.py" in readme   # как переподнять .venv на свежем клоне




def test_update_leaves_readme_untouched(prov, tmp_path):
    # При обновлении версии окружения README проекта не трогаем вовсе.
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    (tmp_path / "README.md").write_text("мой текст\n", encoding="utf-8")
    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "мой текст\n"
    assert not (tmp_path / "README.md.bak").exists()


def test_update_backs_up_claude_md(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    md = tmp_path / "CLAUDE.md"
    md.write_text("моя правка\n", encoding="utf-8")
    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    bak = md.with_name("CLAUDE.md.bak")
    assert bak.exists() and "моя правка" in bak.read_text(encoding="utf-8")
    assert "Single-agent" in md.read_text(encoding="utf-8")


def test_settings_registers_hook(prov, tmp_path):
    import json
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    cmd = data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "bsl_nudge.py" in cmd


def test_settings_sets_utf8_env(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    data = json.loads((tmp_path / ".claude" / "settings.json")
                      .read_text(encoding="utf-8"))
    assert data["env"]["PYTHONUTF8"] == "1"
    assert data["env"]["PYTHONIOENCODING"] == "utf-8"


def test_local_settings_example_has_model_overrides(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    text = (tmp_path / ".claude" / "settings.local.json.example").read_text(
        encoding="utf-8")
    data = json.loads(text)
    # modelOverrides — top-level (не env): CLI не читает его из env.
    assert data["modelOverrides"]["claude-sonnet-4-6"] == "<model-id>"
    assert "modelOverrides" not in data["env"]


def test_copy_tree_handles_binary(prov, tmp_path):
    # place a binary file into a copy of the skills tree path is internal;
    # instead verify deploy still works and a known text skill lands intact
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    skill = (tmp_path / ".claude" / "skills" / "mcp-usage" / "SKILL.md").read_bytes()
    assert b"mcp-usage" in skill


def test_copy_tree_binary_safe(tmp_path):
    src = tmp_path / "src"; (src / "sub").mkdir(parents=True)
    (src / "sub" / "bin.dat").write_bytes(b"\x00\x01\x02\xff")
    (src / "sub" / "__pycache__").mkdir()
    (src / "sub" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    dst = tmp_path / "dst"
    LocalProvisioner().put_tree(str(src), str(dst))
    assert (dst / "sub" / "bin.dat").read_bytes() == b"\x00\x01\x02\xff"
    assert not (dst / "sub" / "__pycache__").exists()


def _bsl_renamed():
    return [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]


def test_deploy_substitutes_selected_mcp_name(prov, tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(prov, config, update=False)
    c = tmp_path / ".claude"

    dev = (c / "checklists" / "reviewer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_checker__" in dev
    assert "mcp__bsl_ls__" not in dev

    settings = (c / "settings.json").read_text(encoding="utf-8")
    assert "mcp__bsl_checker" in settings
    assert "mcp__bsl_ls" not in settings

    skill = (c / "skills" / "mcp-usage" / "SKILL.md").read_text(encoding="utf-8")
    assert "bsl_checker" in skill
    assert "bsl_ls" not in skill


def test_deploy_leaves_unselected_placeholder(prov, tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()   # code-index НЕ выбран
    content.deploy_content(prov, config, update=False)
    dev = (tmp_path / ".claude" / "checklists" / "analyst.md").read_text(encoding="utf-8")
    assert "mcp__code_index__" in dev


def test_deploy_update_applies_mcp_substitution(prov, tmp_path):
    """Обновление тоже переподставляет имя MCP: карточка проекта — источник истины."""
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(prov, config, update=True)
    dev = (tmp_path / ".claude" / "checklists" / "reviewer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_checker" in dev
    assert "mcp__bsl_ls__" not in dev



def test_code_index_repo_alias_substituted(prov, tmp_path):
    """Плейсхолдер алиаса репозитория в mcp-usage заменяется на имя проекта."""
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    skill = (tmp_path / ".claude" / "skills" / "mcp-usage" / "SKILL.md"
             ).read_text(encoding="utf-8")
    assert "{{CODE_INDEX_REPO}}" not in skill
    assert 'repo="demo"' in skill


def test_code_index_repo_alias_substituted_on_update(prov, tmp_path):
    """Имя проекта подставляется и при обновлении — put_tree не оставляет сырой
    плейсхолдер (в отличие от имён MCP, которые на обновлении не трогаем)."""
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    skill = (tmp_path / ".claude" / "skills" / "mcp-usage" / "SKILL.md"
             ).read_text(encoding="utf-8")
    assert "{{CODE_INDEX_REPO}}" not in skill
    assert 'repo="demo"' in skill


def test_deploy_no_overrides_when_default_name(prov, tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    content.deploy_content(prov, config, update=False)
    dev = (tmp_path / ".claude" / "checklists" / "reviewer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_ls__" in dev


# --- интерпретатор .venv впечатывается в вызовы (фикс кроссплатформенности #2) ---

def test_hook_command_points_to_project_venv(prov, tmp_path):
    import json
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    # settings.json остаётся валидным JSON, а команда хука зовёт интерпретатор .venv
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    py = content._shell_path(content.venv_python(prov, str(tmp_path)))
    for evt in ("PostToolUse", "UserPromptSubmit"):
        cmd = data["hooks"][evt][0]["hooks"][0]["command"]
        assert cmd.startswith(f'"{py}" ')          # абсолютный путь, не голый python
        assert "python" not in cmd.replace(py, "")  # кроме как в составе пути venv


def test_settings_windows_venv_path_uses_forward_slashes(prov, tmp_path, monkeypatch):
    # Регрессия: на Windows venv_python отдаёт путь с backslash
    # (C:\...\python.exe). Claude Code исполняет хуки через Git Bash, который
    # съедает литеральные backslash в тексте команды (claude-code#26759).
    # В команде путь должен быть с прямыми слэшами; JSON при этом валиден.
    win_py = r"C:\projects\demo\.venv\Scripts\python.exe"
    monkeypatch.setattr(prov, "venv_python", lambda project_dir: win_py)
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    # не бросает JSONDecodeError → файл остался валидным JSON
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for evt in ("PostToolUse", "UserPromptSubmit"):
        cmd = data["hooks"][evt][0]["hooks"][0]["command"]
        assert cmd.startswith('"C:/projects/demo/.venv/Scripts/python.exe" ')
        assert "\\" not in cmd.split('"')[1]


def test_skill_docs_use_forward_slashes_on_windows(prov, tmp_path, monkeypatch):
    """Команды в SKILL.md тоже исполняет Git Bash — путь venv без backslash."""
    win_py = r"C:\projects\demo\.venv\Scripts\python.exe"
    monkeypatch.setattr(prov, "venv_python", lambda project_dir: win_py)
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    text = (tmp_path / ".claude" / "skills" / "code-analyze" / "SKILL.md"
            ).read_text(encoding="utf-8")
    assert '"C:/projects/demo/.venv/Scripts/python.exe"' in text
    assert "C:\\projects" not in text


def test_skill_docs_use_venv_python(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    py = content.venv_python(prov, str(tmp_path))
    skills = tmp_path / ".claude" / "skills"
    import re
    bare = re.compile(r"\bpython (?=[\"'.$\\-])")
    for md in skills.rglob("SKILL.md"):
        text = md.read_text(encoding="utf-8")
        # ни одного голого вызова python не осталось (кроме как в составе пути venv)
        assert not bare.search(text.replace(py, "")), f"голый python остался в {md}"


def test_deploy_pins_vscode_interpreter(prov, tmp_path):
    # VS Code получает коммитнутый интерпретатор .venv — иначе авто-детект при первом
    # открытии даёт «Invalid python interpreter».
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    settings = tmp_path / ".vscode" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["python.defaultInterpreterPath"] == content.venv_python(prov, str(tmp_path))


def test_vscode_settings_preserved_on_update(prov, tmp_path):
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    vs = tmp_path / ".vscode" / "settings.json"
    vs.write_text('{"python.defaultInterpreterPath": "/custom/python"}\n', encoding="utf-8")
    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    assert (tmp_path / ".vscode" / "settings.json.bak").exists()


def test_deploy_does_not_create_venv(prov, tmp_path):
    # Сам деплой — только текст; .venv поднимается отдельным шагом provision_venv.
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    assert not (tmp_path / ".venv").exists()


def test_deploy_ships_venv_entrypoint(prov, tmp_path):
    # На свежем клоне .venv переподнимается setup-venv.py + requirements.txt.
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    assert (tmp_path / "setup-venv.py").exists()
    assert (tmp_path / "requirements.txt").exists()
    assert ".venv" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


class _FakeProv:
    """Minimal fake provisioner for provision_venv tests."""

    def __init__(self, venv_exists=False):
        self.calls = []
        self._venv_exists = venv_exists
        self._written: dict[str, str] = {}

    def exists(self, path):
        return self._venv_exists

    def python_cmd(self):
        import sys
        return [sys.executable]

    def venv_python(self, project_dir):
        from pathlib import Path
        return str(Path(project_dir) / ".venv" / "bin" / "python")

    def write_text(self, path, content):
        self._written[path] = content

    def run(self, cmd, cwd=None):
        self.calls.append(cmd)
        return RunResult(returncode=0)


def test_provision_venv_builds_and_installs(tmp_path):
    prov = _FakeProv(venv_exists=False)
    result = content.provision_venv(prov, cfg(tmp_path, []), update=False)
    assert result is None                               # успех → без предупреждения
    # 1) создание venv интерпретатором цели, 2) pip install -r requirements.txt
    assert prov.calls[0][1:3] == ["-m", "venv"]
    assert Path(prov.calls[0][-1]).resolve() == (tmp_path / ".venv").resolve()
    assert prov.calls[1][1:5] == ["-m", "pip", "install", "-r"]
    assert prov.calls[1][-1].endswith("requirements.txt")


def test_provision_venv_requirements_inside_venv(tmp_path):
    # Byte-for-byte constraint: requirements temp file must go INSIDE .venv, not
    # in the project root, to keep the meaningful project tree unchanged.
    prov = _FakeProv(venv_exists=False)
    content.provision_venv(prov, cfg(tmp_path, []), update=False)
    written_paths = list(prov._written.keys())
    assert all(".venv" in p for p in written_paths), (
        f"requirements temp file written outside .venv: {written_paths}"
    )


def test_provision_venv_warns_on_pip_failure(tmp_path):
    class _FailPipProv(_FakeProv):
        def run(self, cmd, cwd=None):
            self.calls.append(cmd)
            if "pip" in cmd:
                return RunResult(returncode=1, stderr="pip error")
            return RunResult(returncode=0)

    prov = _FailPipProv(venv_exists=False)
    # не бросает (создание проекта не блокируется), а возвращает текст предупреждения
    msg = content.provision_venv(prov, cfg(tmp_path, []), update=False)
    assert msg and "setup-venv.py" in msg


def test_update_backs_up_overwritten_template_file(tmp_path):
    """Правка пользователя в .claude не исчезает бесследно при update-env."""
    from agentmon.env.content import deploy_content
    from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION

    project = tmp_path / "proj"
    project.mkdir()
    cfg = EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="proj",
        project_dir=str(project), developer_id="i", developer_email="i@e.ru",
        platform_dir="", platform_version="", db_kind="file",
        db_connection="", web_publication="", mcp=[], agents=[])
    deploy_content(LocalProvisioner(), cfg, update=False)
    skill = project / ".claude" / "skills" / "1c-batch" / "SKILL.md"
    assert skill.exists()
    skill.write_text("моя правка\n", encoding="utf-8")

    deploy_content(LocalProvisioner(), cfg, update=True)

    bak = skill.with_name("SKILL.md.bak")
    assert bak.exists() and "моя правка" in bak.read_text(encoding="utf-8")
    assert skill.read_text(encoding="utf-8") != "моя правка\n"


# --- хук code-index-guard: конфиг генерируется при развёртывании ---

def _config(tmp_path, mcp):
    from agentmon.env.config_schema import EnvConfig
    return EnvConfig(
        schema_version=1, project_name="proj", project_dir=str(tmp_path / "p"),
        developer_id="", developer_email="", platform_dir="",
        platform_version="", db_kind="file", db_connection="",
        web_publication="", mcp=mcp, agents=[])


def test_deploy_writes_guard_config_and_hook(tmp_path):
    from agentmon.env.config_schema import McpSelection
    import json
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    # connection-фрагмент явно называет сервер code_index — префикс гарда должен
    # совпасть с ключом `.mcp.json`.
    cfg = _config(tmp_path, [McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="C:/proj/src/cf", project_name="proj",
        connection='"code_index": {"type": "http", "url": "http://x:1/mcp"}')])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    guard = (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml")
    text = guard.read_text(encoding="utf-8")
    assert 'path = "C:/proj/src/cf"' in text
    assert 'alias = "proj"' in text
    assert f'mcp_prefix = "{_expected_prefix(cfg)}"' in text
    assert 'mcp_prefix = "mcp__code_index__"' in text
    settings = json.loads((tmp_path / "p" / ".claude" / "settings.json")
                          .read_text(encoding="utf-8"))
    cmds = [h["command"] for e in settings["hooks"]["PreToolUse"]
            for h in e["hooks"]]
    assert any("code_index_guard.py" in c for c in cmds)


def test_deploy_without_code_index_has_no_hook(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    cfg = _config(tmp_path, [McpSelection(id="bsl-ls", enabled=True, mode="managed")])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    guard = tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
    assert guard.exists()
    text = guard.read_text(encoding="utf-8")
    assert "[[local]]" not in text
    # Префикс инертен (гард не регистрируется) — остаётся плейсхолдер.
    assert 'mcp_prefix = "mcp__code_index__"' in text
    settings = (tmp_path / "p" / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "code_index_guard.py" not in settings


def test_deploy_guard_prefix_no_connection(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.env.mcp_catalog import build_mcp_json
    from agentmon.backends.local import LocalProvisioner
    # Карточка без connection: ключ сервера в .mcp.json — sel.id (`code-index`).
    # Префикс гарда обязан называть тот же сервер, иначе deny-сообщения укажут
    # на несуществующие инструменты.
    sel = McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="C:/proj/src/cf", project_name="proj")
    cfg = _config(tmp_path, [sel])
    deploy_content(LocalProvisioner(), cfg, update=False)
    text = (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
            ).read_text(encoding="utf-8")
    assert 'mcp_prefix = "mcp__code-index__"' in text
    # Перекрёстная проверка инварианта: тот же ключ в .mcp.json.
    assert f'mcp_prefix = "{_expected_prefix(cfg)}"' in text
    servers = build_mcp_json([sel])["mcpServers"]
    assert list(servers) == ["code-index"]


def _expected_prefix(cfg, name="code") -> str:
    """Ожидаемый mcp_prefix гарда по фактическому ключу сервера в `.mcp.json`."""
    from agentmon.env.mcp_catalog import build_mcp_json
    keys = [k for k in build_mcp_json(cfg.mcp)["mcpServers"] if name in k]
    assert len(keys) == 1, keys
    return f"mcp__{keys[0]}__"


def _guard_text(tmp_path) -> str:
    return (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
            ).read_text(encoding="utf-8")


def test_deploy_guard_prefix_prefers_guarded_card(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    # Не-гард карточки (до и после) не перетягивают имя. Обе гард-карточки дают
    # ключ `code-index` — в .mcp.json выживает последняя, поэтому гард защищает
    # только её репозиторий (другой сервер модель не видит — абстенция, не тупик).
    cfg = _config(tmp_path, [
        McpSelection(id="bsl-ls", enabled=True, mode="managed",
                     connection='"bsl_checker": {"type": "http", '
                                '"url": "http://127.0.0.1:8001/mcp"}'),
        # Раннюю карточку тоже переименовываем фрагментом: без него `_server_name`
        # дал бы другой ключ, и последняя карточка не перекрыла бы её.
        McpSelection(id="code-index", enabled=True, mode="managed",
                     catalog_dir="C:/a", project_name="a",
                     connection='"code-index": {"command": "code-index-mcp"}'),
        McpSelection(id="code-index-local", enabled=True, mode="managed",
                     catalog_dir="C:/b", project_name="b",
                     connection='"code-index": {"command": "code-index-mcp"}')])
    deploy_content(LocalProvisioner(), cfg, update=False)
    text = _guard_text(tmp_path)
    assert f'mcp_prefix = "{_expected_prefix(cfg)}"' in text
    assert text.count("[[local]]") == 1
    assert 'path = "C:/b"' in text
    assert 'alias = "b"' in text
    assert 'path = "C:/a"' not in text


def test_deploy_guard_same_name_cards_only_last_served(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.env.mcp_catalog import build_mcp_json
    from agentmon.backends.local import LocalProvisioner
    # Две карточки с одинаковым ключом по умолчанию (`code_index`): dict в
    # build_mcp_json оставляет последнюю. Гард обязан совпасть с ней — иначе
    # deny-текст отправлял бы модель к серверу для чужого репозитория.
    # code-index-local без connection в реестре нет — ставим connection, но с
    # ключом по умолчанию `code_index` (как у карточки code-index).
    cards = [
        McpSelection(id="code-index", enabled=True, mode="managed",
                     catalog_dir="C:/proj/one/cf", project_name="one",
                     connection='"code_index": {"command": "code-index-mcp"}'),
        McpSelection(id="code-index-local", enabled=True, mode="managed",
                     catalog_dir="C:/proj/two/cf", project_name="two",
                     connection='"code_index": {"command": "code-index-mcp"}')]
    cfg = _config(tmp_path, cards)
    deploy_content(LocalProvisioner(), cfg, update=False)
    text = _guard_text(tmp_path)
    assert text.count("[[local]]") == 1
    assert 'path = "C:/proj/two/cf"' in text
    assert 'alias = "two"' in text
    assert 'path = "C:/proj/one/cf"' not in text
    assert f'mcp_prefix = "{_expected_prefix(cfg)}"' in text
    # Обе карточки дают ключ `code_index` — в .mcp.json один сервер (последний).
    assert list(build_mcp_json(cfg.mcp)["mcpServers"]) == ["code_index"]


def test_deploy_guard_last_wins_different_keys(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.env.mcp_catalog import build_mcp_json
    from agentmon.backends.local import LocalProvisioner
    # Ключи гард-карточек РАЗНЫЕ (code_index_queries и code_index): в .mcp.json
    # живут оба сервера, поэтому first-vs-last различимы. Хвостовая не-гард
    # карточка не перетягивает имя. Гард обязан называть последнюю гард-карточку
    # (code_index) и защищать только её репозиторий.
    cfg = _config(tmp_path, [
        McpSelection(id="code-index", enabled=True, mode="managed",
                     connection='"code_index_queries": {"type": "http", '
                                '"url": "http://x:1/mcp"}',
                     catalog_dir="C:/proj/one/cf", project_name="one"),
        McpSelection(id="code-index-local", enabled=True, mode="managed",
                     connection='"code_index": {"type": "http", '
                                '"url": "http://x:2/mcp"}',
                     catalog_dir="C:/proj/two/cf", project_name="two"),
        # `bsl-ls` нет в CATALOG — без connection build_mcp_json упадёт, поэтому
        # хвостовой карточке задаём свой (не гард) ключ фрагментом.
        McpSelection(id="bsl-ls", enabled=True, mode="managed",
                     connection='"bsl_ls": {"type": "http", '
                                '"url": "http://x:3/mcp"}')])
    deploy_content(LocalProvisioner(), cfg, update=False)
    text = _guard_text(tmp_path)
    assert 'mcp_prefix = "mcp__code_index__"' in text
    assert text.count("[[local]]") == 1
    assert 'path = "C:/proj/two/cf"' in text
    assert 'alias = "two"' in text
    assert 'path = "C:/proj/one/cf"' not in text
    keys = list(build_mcp_json(cfg.mcp)["mcpServers"])
    assert "code_index_queries" in keys
    assert "code_index" in keys
    # `code_index` — последний гард-ключ (bsl_ls идёт после, но это не гард).
    guarded = [k for k in keys if k.startswith("code_")]
    assert guarded == ["code_index_queries", "code_index"]
    # _expected_prefix не подходит: он требует единственный ключ `code`.


def test_deploy_guard_rejects_tilde_catalog_dir(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    # Ни хук, ни демон code-index не раскрывают `~` — карточка невалидна.
    cfg = _config(tmp_path, [McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="~/proj/src/cf", project_name="proj")])
    with pytest.raises(ValueError, match="абсолютный путь"):
        deploy_content(LocalProvisioner(), cfg, update=False)


def test_deploy_guard_uses_actual_mcp_name(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    # connection — фрагмент без внешних фигурных скобок (конвенция карточки
    # MCP: _parse_connection сам оборачивает его в {...}).
    cfg = _config(tmp_path, [McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="C:/proj/src/cf", project_name="proj",
        connection='"code_index_queries": {"type": "http", "url": "http://x:1/mcp"}')])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    text = (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
            ).read_text(encoding="utf-8")
    assert 'mcp_prefix = "mcp__code_index_queries__"' in text
    # Инвариант: префикс гарда = ключ фактического сервера в `.mcp.json`.
    assert f'mcp_prefix = "{_expected_prefix(cfg)}"' in text
    # Подстановка имён MCP не должна переименовать имя файла хука.
    settings = (tmp_path / "p" / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "code_index_guard.py" in settings
    assert "code_index_queries_guard.py" not in settings
    # Сам файл хука на месте под исходным именем.
    assert (tmp_path / "p" / ".claude" / "hooks" / "code_index_guard.py").exists()
    assert not (tmp_path / "p" / ".claude" / "hooks"
                / "code_index_queries_guard.py").exists()
