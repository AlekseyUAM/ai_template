# app/tests/env/test_content_conditions.py
from pathlib import Path

import pytest

from agentmon.backends.local import LocalProvisioner
from agentmon.env import content
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION, McpSelection


def cfg(tmp_path, mcp):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="iv", developer_email="iv@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="",
        mcp=mcp, agents=[],
    )


def sel(mcp_id, *, enabled=True, connection=None):
    return McpSelection(id=mcp_id, enabled=enabled, mode="managed",
                        connection=connection)


def skill_text(tmp_path, name):
    return (Path(tmp_path) / ".claude" / "skills" / name / "SKILL.md"
            ).read_text(encoding="utf-8")


# --- рендер маркеров ---

def test_render_conditionals_keeps_block_when_true():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nвнутри\n\nпосле\n"


def test_render_conditionals_drops_block_when_false():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nпосле\n"


def test_render_conditionals_inline_rows():
    text = "| a |\n<!-- @if 1c-md -->\n| b |\n<!-- @endif -->\n| c |\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "| a |\n| b |\n| c |\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": False}, filename="x.md"
    ) == "| a |\n| c |\n"


def test_render_conditionals_without_markers_unchanged():
    text = "обычный текст\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": True}, filename="x.md") == text


def test_render_conditionals_unclosed_marker_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "<!-- @if 1c-md -->\nтекст\n",
            {"1c-md": True, "1c_naparnic": True}, filename="x.md")


def test_render_conditionals_orphan_endif_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "текст\n<!-- @endif -->\n",
            {"1c-md": True, "1c_naparnic": True}, filename="x.md")


def test_render_conditionals_naparnic_block():
    text = ("до\n<!-- @if 1c_naparnic -->\n\nвнутри\n"
            "<!-- @endif -->\n\nпосле\n")
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": True}, filename="x.md"
    ) == "до\n\nвнутри\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nпосле\n"


def test_conditional_flags_by_enabled_mcp():
    assert content.conditional_flags([]) == {
        "1c-md": False, "1c_naparnic": False}
    assert content.conditional_flags([sel("1c-md")])["1c-md"] is True
    assert content.conditional_flags([sel("1c-md-queries")])["1c-md"] is True
    assert content.conditional_flags([sel("1c-naparnic")]) == {
        "1c-md": False, "1c_naparnic": True}
    assert content.conditional_flags(
        [sel("1c-naparnic", enabled=False)])["1c_naparnic"] is False


# --- деплой: mcp-usage ---

def test_deploy_1c_md_adds_validate_query_to_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" in text
    assert "метаданные, загруженные в БД" in text
    assert "<!-- @if " not in text and "<!-- @endif -->" not in text


def test_deploy_1c_md_queries_also_adds_section(tmp_path):
    conn = '"1c-md": {"type": "http", "url": "http://localhost/base/hs/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-md-queries", connection=conn)]),
        update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" in text
    assert "метаданные, загруженные в БД" in text
    assert "<!-- @if " not in text and "<!-- @endif -->" not in text


def test_deploy_without_1c_md_has_no_validate_query_in_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("bsl-ls")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" not in text
    assert "<!-- @if " not in text


def test_deploy_disabled_1c_md_has_no_validate_query(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md", enabled=False)]),
        update=False)
    assert "validate_query" not in skill_text(tmp_path, "mcp-usage")


# --- деплой: 1c_naparnic ---

def test_deploy_1c_naparnic_adds_ask_1c_ai_to_mcp_usage(tmp_path):
    conn = ('"1c_naparnic": {"type": "http", '
            '"url": "http://localhost:8003/mcp"}')
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-naparnic", connection=conn)]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "ask_1c_ai" in text
    assert "mcp__1c_naparnic__*" in text
    assert "<!-- @if " not in text and "<!-- @endif -->" not in text


def test_deploy_without_1c_naparnic_has_no_ask_1c_ai(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("bsl-ls")]), update=False)
    assert "ask_1c_ai" not in skill_text(tmp_path, "mcp-usage")


def test_deploy_disabled_1c_naparnic_has_no_ask_1c_ai(tmp_path):
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-naparnic", enabled=False)]), update=False)
    assert "ask_1c_ai" not in skill_text(tmp_path, "mcp-usage")


def test_renamed_1c_naparnic_server_name_substituted(tmp_path):
    conn = '"my_ai": {"type": "http", "url": "http://localhost:8003/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-naparnic", connection=conn)]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "mcp__my_ai__*" in text
    assert "mcp__1c_naparnic__*" not in text


def test_no_conditional_markers_leak_with_1c_naparnic(tmp_path):
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-md"), sel("1c-naparnic")]), update=False)
    for path in (Path(tmp_path) / ".claude").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "<!-- @if " not in text, path
        assert "<!-- @endif -->" not in text, path


# --- деплой: query-analyze и переходы при обновлении ---

def test_deploy_1c_md_makes_validate_query_first_layer(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__1c-md__validate_query" in text
    assert "analyze_query.py" in text          # локальные проверки остались
    assert "<!-- @if " not in text


def test_deploy_1c_md_queries_makes_validate_query_first_layer(tmp_path):
    # Реальная карточка этого вида тоже называет сервер `1c-md` (дефолт вида):
    # без connection имя упало бы в id `1c-md-queries` и override переименовал бы
    # инструмент в `mcp__1c-md-queries__…`.
    conn = '"1c-md": {"type": "http", "url": "http://localhost/base/hs/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-md-queries", connection=conn)]),
        update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__1c-md__validate_query" in text
    assert "analyze_query.py" in text


def test_deploy_without_1c_md_keeps_query_analyze_as_is(tmp_path):
    content.deploy_content(LocalProvisioner(), cfg(tmp_path, []), update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "validate_query" not in text
    assert "analyze_query.py" in text


def test_update_adds_then_removes_1c_md_blocks(tmp_path):
    prov = LocalProvisioner()
    content.deploy_content(prov, cfg(tmp_path, []), update=False)
    assert "validate_query" not in skill_text(tmp_path, "query-analyze")

    content.deploy_content(prov, cfg(tmp_path, [sel("1c-md")]), update=True)
    assert "validate_query" in skill_text(tmp_path, "query-analyze")
    assert "validate_query" in skill_text(tmp_path, "mcp-usage")

    content.deploy_content(prov, cfg(tmp_path, []), update=True)
    assert "validate_query" not in skill_text(tmp_path, "query-analyze")
    assert "validate_query" not in skill_text(tmp_path, "mcp-usage")


def test_renamed_1c_md_server_name_substituted(tmp_path):
    conn = ('"my_md": {"type": "http", '
            '"url": "http://localhost/base/hs/mcp"}')
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md", connection=conn)]),
        update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__my_md__validate_query" in text
    assert "mcp__1c-md__validate_query" not in text


def test_conditional_render_keeps_venv_python(tmp_path):
    prov = LocalProvisioner()
    content.deploy_content(prov, cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "query-analyze")
    expected = content._shell_path(content.venv_python(prov, str(tmp_path)))
    assert expected in text


def test_no_conditional_markers_leak_into_project(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md-queries")]),
        update=False)
    for path in (Path(tmp_path) / ".claude").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "<!-- @if " not in text, path
        assert "<!-- @endif -->" not in text, path


def test_template_markers_are_balanced():
    for path in content.CONTENT_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        content._render_conditional_blocks(
            text, {"1c-md": True, "1c_naparnic": True}, filename=str(path))
        content._render_conditional_blocks(
            text, {"1c-md": False, "1c_naparnic": False}, filename=str(path))


# --- деплой: имена MCP в чеклистах ---

CHECKLISTS = ("analyst", "architect", "developer", "developer-tests",
              "reviewer", "technical-writer")


def checklist_text(tmp_path, name):
    return (Path(tmp_path) / ".claude" / "checklists" / f"{name}.md"
            ).read_text(encoding="utf-8")


def test_deploy_substitutes_bsl_ls_in_checklists(tmp_path):
    conn = '"bsl_checker": {"type": "http", "url": "http://localhost:8001/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("bsl-ls", connection=conn)]), update=False)
    text = checklist_text(tmp_path, "reviewer")
    assert "mcp__bsl_checker__check" in text
    assert "mcp__bsl_ls__" not in text


def test_deploy_substitutes_code_index_in_checklists(tmp_path):
    conn = '"my_ci": {"type": "http", "url": "http://localhost:8002/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("code-index", connection=conn)]), update=False)
    text = checklist_text(tmp_path, "analyst")
    assert "mcp__my_ci__*" in text
    assert "mcp__code_index__*" not in text


def test_deploy_checklist_python_invocations_rewritten(tmp_path):
    content.deploy_content(LocalProvisioner(), cfg(tmp_path, []), update=False)
    text = checklist_text(tmp_path, "developer-tests")
    assert "run-tests.py" in text
    assert ".venv" in text
    assert "{{" not in text
    assert not text.startswith("---")


def test_deploy_no_agents_dir(tmp_path):
    content.deploy_content(LocalProvisioner(), cfg(tmp_path, []), update=False)
    assert not (Path(tmp_path) / ".claude" / "agents").exists()
