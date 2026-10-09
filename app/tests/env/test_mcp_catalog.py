import pytest

from agentmon.env.config_schema import McpSelection
from agentmon.env.mcp_catalog import CATALOG, build_mcp_json


def test_catalog_has_five_servers():
    assert set(CATALOG) == {
        "1c-md", "1c-syntax-checker-mcp", "bsl-platform-context",
        "1c-naparnic", "code-index",
    }


def test_disabled_server_is_skipped():
    sel = [McpSelection(id="code-index", enabled=False, mode="managed")]
    assert build_mcp_json(sel) == {"mcpServers": {}}


def test_managed_http_uses_localhost_url():
    sel = [McpSelection(id="code-index", enabled=True, mode="managed")]
    out = build_mcp_json(sel)["mcpServers"]["code-index"]
    port = CATALOG["code-index"].default_port
    assert out == {"url": f"http://127.0.0.1:{port}"}


def test_external_url_is_passed_through():
    sel = [McpSelection(id="1c-naparnic", enabled=True, mode="external",
                        endpoint="http://host:9000/sse")]
    out = build_mcp_json(sel)["mcpServers"]["1c-naparnic"]
    assert out == {"url": "http://host:9000/sse"}


def test_external_empty_endpoint_raises():
    sel = [McpSelection(id="1c-md", enabled=True, mode="external", endpoint=None)]
    with pytest.raises(ValueError, match="external"):
        build_mcp_json(sel)


def test_external_command_endpoint_is_split():
    sel = [McpSelection(id="1c-md", enabled=True, mode="external", endpoint="my-mcp --port 9000")]
    out = build_mcp_json(sel)["mcpServers"]["1c-md"]
    assert out == {"command": "my-mcp", "args": ["--port", "9000"]}


def test_unknown_mcp_id_raises():
    sel = [McpSelection(id="does-not-exist", enabled=True, mode="managed")]
    with pytest.raises(ValueError, match="неизвестн"):
        build_mcp_json(sel)
