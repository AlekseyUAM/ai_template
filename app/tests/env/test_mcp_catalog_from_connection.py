import pytest

from agentmon.env.config_schema import McpSelection
from agentmon.env.mcp_catalog import build_mcp_json, mcp_name_overrides


def test_build_mcp_json_uses_connection_fragment():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    servers = build_mcp_json(sel)["mcpServers"]
    assert servers == {
        "bsl_ls": {"type": "http", "url": "http://localhost:8001/mcp"}
    }


def test_build_mcp_json_rejects_non_object_server_value():
    # Значение сервера в произвольном MCP должно быть объектом, а не скаляром.
    sel = [McpSelection(
        id="custom", enabled=True, mode="managed",
        connection='"a": 123',
    )]
    with pytest.raises(ValueError, match="объект"):
        build_mcp_json(sel)


def test_build_mcp_json_custom_fragment_key():
    sel = [McpSelection(
        id="custom", enabled=True, mode="managed",
        connection='"name": {"type":"http","url":"http://localhost:8000/mcp"}',
    )]
    servers = build_mcp_json(sel)["mcpServers"]
    assert "name" in servers
    assert servers["name"] == {"type": "http", "url": "http://localhost:8000/mcp"}


def test_build_mcp_json_disabled_with_connection_skipped():
    sel = [McpSelection(
        id="bsl-ls", enabled=False, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    assert build_mcp_json(sel) == {"mcpServers": {}}


def test_build_mcp_json_bad_connection_raises():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {not valid json',
    )]
    with pytest.raises(ValueError, match="connection"):
        build_mcp_json(sel)


def test_overrides_renamed_mcp():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {"bsl_ls": "bsl_checker"}


def test_overrides_default_name_gives_no_entry():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_unknown_type_skipped():
    # вид "custom" существует, но без дефолтного mcp_name → пропуск
    sel = [McpSelection(
        id="custom", enabled=True, mode="managed",
        connection='"foo": {"type":"http","url":"http://x/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_absent_type_skipped():
    sel = [McpSelection(id="does-not-exist", enabled=True, mode="managed")]
    assert mcp_name_overrides(sel) == {}


def test_overrides_disabled_skipped():
    sel = [McpSelection(
        id="bsl-ls", enabled=False, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://x/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_without_connection_uses_id():
    # нет connection → актуальное имя = sel.id (standard_key вида)
    sel = [McpSelection(id="code-index", enabled=True, mode="managed")]
    assert mcp_name_overrides(sel) == {"code_index": "code-index"}

