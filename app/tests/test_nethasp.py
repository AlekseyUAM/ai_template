from agentmon.env.nethasp import render_nethasp_ini, deploy_nethasp
from agentmon.env.config_schema import EnvConfig
from agentmon.backends.local import LocalProvisioner


def test_render_contains_server_addr():
    ini = render_nethasp_ini("10.0.0.5")
    assert "[NH_SERVER]" in ini
    assert "NH_SERVER_ADDR = 10.0.0.5" in ini
    assert "NH_TCPIP = Enabled" in ini


def test_deploy_writes_file_when_server_set(tmp_path):
    prov = LocalProvisioner()
    cfg = EnvConfig(schema_version=1, project_name="d", project_dir=str(tmp_path),
                    developer_id="x", developer_email="x", platform_dir="",
                    platform_version="", db_kind="server", db_connection="",
                    web_publication="", mcp=[], agents=[], license_server="10.0.0.5")
    deploy_nethasp(prov, cfg, home=str(tmp_path / "home"))
    assert (tmp_path / "conf" / "nethasp.ini").read_text(encoding="utf-8").find("10.0.0.5") > 0
    assert (tmp_path / "home" / ".1cv8" / "conf" / "nethasp.ini").exists()


def test_deploy_writes_platform_conf(tmp_path):
    platform = tmp_path / "opt" / "1cv8"
    platform.mkdir(parents=True)
    prov = LocalProvisioner()
    cfg = EnvConfig(schema_version=1, project_name="d", project_dir=str(tmp_path),
                    developer_id="x", developer_email="x",
                    platform_dir=str(platform),
                    platform_version="8.3", db_kind="server", db_connection="",
                    web_publication="", mcp=[], agents=[], license_server="10.0.0.5")
    deploy_nethasp(prov, cfg, home=str(tmp_path / "home"))
    assert (platform / "conf" / "nethasp.ini").exists()


def test_deploy_noop_when_server_empty(tmp_path):
    prov = LocalProvisioner()
    cfg = EnvConfig(schema_version=1, project_name="d", project_dir=str(tmp_path),
                    developer_id="x", developer_email="x", platform_dir="",
                    platform_version="", db_kind="server", db_connection="",
                    web_publication="", mcp=[], agents=[], license_server=None)
    deploy_nethasp(prov, cfg)
    assert not (tmp_path / "conf" / "nethasp.ini").exists()
