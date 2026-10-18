from agentmon.backends.local import LocalProvisioner
from agentmon.env.content import deploy_content
from agentmon.env.config_schema import EnvConfig


def _config(tmp_path):
    return EnvConfig(
        schema_version=1, project_name="demo", project_dir=str(tmp_path),
        developer_id="dev", developer_email="d@e", platform_dir="",
        platform_version="", db_kind="server", db_connection="",
        web_publication="", mcp=[], agents=[], license_server=None)


def test_deploy_content_populates_claude(tmp_path):
    prov = LocalProvisioner()
    deploy_content(prov, _config(tmp_path), update=False)
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / ".claude" / "agents").is_dir()
    assert (tmp_path / "README.md").read_text(encoding="utf-8").startswith("## demo")
