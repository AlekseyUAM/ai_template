from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.env import content, task_schema as ts


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir="/opt/1cv8",
        platform_version="8.3.27.1786", db_kind="file", db_connection="/b",
        web_publication="", mcp=[], agents=[])


def test_deploy_places_task_status_tool(tmp_path):
    content.deploy_content(cfg(tmp_path), update=False)
    assert (tmp_path / ".claude" / "tools" / "task_status.py").exists()
    assert (tmp_path / ".claude" / "agents" / "developer.md").exists()


def test_task_and_tool_coexist(tmp_path):
    content.deploy_content(cfg(tmp_path), update=False)
    spec = ts.create_task(tmp_path, title="T", goal="g", plan="p", constraints="c",
                          enabled_stages=ts.STAGE_NAMES)
    assert (ts.task_dir(tmp_path, spec.id) / "task.json").exists()
    assert (tmp_path / ".claude" / "tools" / "task_status.py").exists()
