from agentmon.env.mcp_types import MCP_TYPES, get_type, build_connection, types_payload


def test_seven_types_present():
    keys = {t.key for t in MCP_TYPES}
    assert keys == {
        "custom", "1c-md", "1c-md-queries", "bsl-ls",
        "1c-platform", "1c-naparnic", "code-index",
    }


def test_custom_is_first_and_minimal():
    # Произвольный — первым в списке (вид по умолчанию в UI)
    assert MCP_TYPES[0].key == "custom"
    t = get_type("custom")
    assert t.fields == ("name", "purpose", "connection")
    assert t.action is None


def test_metadata_type_fields_and_defaults():
    t = get_type("1c-md")
    assert t.title == "Метаданные (http-сервис в 1С)"
    assert t.fields == ("name", "mcp_name", "purpose", "url", "db_name", "connection")
    assert t.defaults["mcp_name"] == "1c-md"
    assert t.defaults["url"] == "localhost"
    assert t.defaults["db_name"] == "my_database"
    assert t.defaults["purpose"] == "Вся информация об актуальных метаданных конфигурации"
    assert t.action == "cfe"
    assert t.cfe_path == "deps/mcp_tools_cfe/MCP_Сервер.cfe"


def test_metadata_queries_separate_cfe_and_purpose():
    t = get_type("1c-md-queries")
    assert t.action == "cfe"
    assert t.cfe_path == "deps/mcp_tools_cfe/1c-mcp-tools-1.0.6.cfe"
    assert t.defaults["mcp_name"] == "1c-md"
    assert "Произвольные запросы" in t.defaults["purpose"]


def test_bsl_ls_defaults_and_docker():
    t = get_type("bsl-ls")
    assert t.fields == ("name", "mcp_name", "purpose", "url", "port", "connection")
    assert t.defaults["mcp_name"] == "bsl_ls"
    assert t.defaults["port"] == 8001
    assert t.action == "docker"


def test_platform_is_sse():
    t = get_type("1c-platform")
    assert t.defaults["mcp_name"] == "1c_platform"
    assert t.defaults["port"] == 8002
    assert '"type": "sse"' in t.connection_template
    assert '"transport": "sse"' in t.connection_template


def test_platform_requires_platform_path():
    t = get_type("1c-platform")
    assert "platform_path" in t.fields
    assert t.required == ("platform_path",)


def test_naparnic_has_token_field():
    t = get_type("1c-naparnic")
    assert "token" in t.fields
    assert t.defaults["mcp_name"] == "1c_naparnic"
    assert t.defaults["port"] == 8003


def test_code_index_requires_catalog_dir():
    t = get_type("code-index")
    assert "catalog_dir" in t.fields
    assert t.required == ("catalog_dir",)
    assert t.defaults["mcp_name"] == "code_index"
    assert t.defaults["port"] == 8004


def test_build_connection_metadata_uses_defaults():
    conn = build_connection("1c-md")
    assert '"1c-md":' in conn
    assert '"url": "http://localhost/my_database/hs/mcp"' in conn


def test_build_connection_metadata_substitutes_db_name_and_url():
    conn = build_connection("1c-md", db_name="my_base", url="host1")
    assert '"url": "http://host1/my_base/hs/mcp"' in conn


def test_types_payload_metadata_field_labels():
    md = next(p for p in types_payload() if p["key"] == "1c-md")
    assert md["field_labels"] == {"url": "URL хоста", "db_name": "Имя базы"}


def test_build_connection_substitutes_name_url_port():
    conn = build_connection("bsl-ls", mcp_name="bsl2", url="example", port=9100)
    assert '"bsl2":' in conn
    assert '"url": "http://example:9100/mcp"' in conn


def test_build_connection_custom_default_text():
    conn = build_connection("custom")
    assert '"name":' in conn
    assert '"url": "http://localhost:8000/mcp"' in conn


def test_types_payload_is_json_serialisable():
    import json
    payload = types_payload()
    assert isinstance(payload, list)
    json.dumps(payload)  # не должно падать
    md = next(p for p in payload if p["key"] == "1c-md")
    assert md["has_cfe"] is True
    assert md["fields"] == ["name", "mcp_name", "purpose", "url", "db_name", "connection"]
    custom = next(p for p in payload if p["key"] == "custom")
    assert custom["has_cfe"] is False
