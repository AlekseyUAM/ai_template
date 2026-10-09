import json
from pathlib import Path
from agentmon.env.config_schema import EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION
from agentmon.env import scaffold


def cfg(tmp_path, mcp):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="http://h/demo",
        mcp=mcp, agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


def test_scaffold_creates_layout(tmp_path):
    scaffold.scaffold_layout(tmp_path)
    for rel in scaffold.LAYOUT_DIRS:
        assert (tmp_path / rel).is_dir()


def test_scaffold_is_idempotent(tmp_path):
    scaffold.scaffold_layout(tmp_path)
    scaffold.scaffold_layout(tmp_path)  # повторный вызов не падает
    assert (tmp_path / "src" / "cf").is_dir()


def test_write_env_files_writes_mcp_json(tmp_path):
    c = cfg(tmp_path, [McpSelection("code-index", True, "managed")])
    scaffold.write_env_files(c, update=False)
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "code-index" in data["mcpServers"]
    # docker-compose.mcp.yml больше не генерируется (контейнеры — со страницы MCP)
    assert not (tmp_path / "docker-compose.mcp.yml").exists()


def test_write_env_files_no_compose_when_no_managed(tmp_path):
    c = cfg(tmp_path, [McpSelection("1c-naparnic", True, "external",
                                    endpoint="http://h:9000/sse")])
    scaffold.write_env_files(c, update=False)
    assert not (tmp_path / "docker-compose.mcp.yml").exists()


def test_write_preserving_backs_up_on_update(tmp_path):
    p = tmp_path / "CLAUDE.md"
    scaffold.write_preserving(p, "первая\n", update=False)
    scaffold.write_preserving(p, "вторая\n", update=True)
    assert p.read_text(encoding="utf-8") == "вторая\n"
    assert (tmp_path / "CLAUDE.md.bak").read_text(encoding="utf-8") == "первая\n"
