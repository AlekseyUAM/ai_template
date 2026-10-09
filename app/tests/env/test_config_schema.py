from agentmon.env.config_schema import (
    EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION,
)


def sample_config():
    return EnvConfig(
        schema_version=SCHEMA_VERSION,
        project_name="demo", project_dir="/proj/demo",
        developer_id="ivanov", developer_email="i@e.ru",
        platform_dir="/opt/1cv8/8.3.27.1786", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/base/demo", web_publication="http://host/demo",
        mcp=[McpSelection(id="code-index", enabled=True, mode="managed",
                          endpoint=None, secret_env=None)],
        agents=[AgentModel(agent="developer", model="claude-opus-4-8", effort="high")],
    )


def test_roundtrip_dict():
    cfg = sample_config()
    assert EnvConfig.from_dict(cfg.to_dict()) == cfg
