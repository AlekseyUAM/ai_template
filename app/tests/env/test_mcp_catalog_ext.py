from agentmon.env.mcp_catalog import CATALOG


def test_1c_md_is_extension():
    s = CATALOG["1c-md"]
    assert s.kind == "extension"
    assert s.download and s.download.endswith("MCP_Сервер.cfe")


def test_docker_presets_have_port():
    for k in ("1c-syntax-checker-mcp", "bsl-platform-context",
              "1c-naparnic", "code-index"):
        s = CATALOG[k]
        assert s.kind == "docker" and s.default_port


def test_naparnic_needs_token():
    assert CATALOG["1c-naparnic"].needs_token is True
