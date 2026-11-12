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
        text, True, filename="x.md") == "до\n\nвнутри\n\nпосле\n"


def test_render_conditionals_drops_block_when_false():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, False, filename="x.md") == "до\n\nпосле\n"


def test_render_conditionals_inline_rows():
    text = "| a |\n<!-- @if 1c-md -->\n| b |\n<!-- @endif -->\n| c |\n"
    assert content._render_conditional_blocks(
        text, True, filename="x.md") == "| a |\n| b |\n| c |\n"
    assert content._render_conditional_blocks(
        text, False, filename="x.md") == "| a |\n| c |\n"


def test_render_conditionals_without_markers_unchanged():
    text = "обычный текст\n"
    assert content._render_conditional_blocks(
        text, True, filename="x.md") == text


def test_render_conditionals_unclosed_marker_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "<!-- @if 1c-md -->\nтекст\n", True, filename="x.md")


def test_render_conditionals_orphan_endif_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "текст\n<!-- @endif -->\n", True, filename="x.md")


# --- деплой: mcp-usage ---

def test_deploy_1c_md_adds_validate_query_to_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" in text
    assert "метаданные, загруженные в БД" in text
    assert "<!-- @if" not in text and "<!-- @endif" not in text


def test_deploy_1c_md_queries_also_adds_section(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md-queries")]),
        update=False)
    assert "validate_query" in skill_text(tmp_path, "mcp-usage")


def test_deploy_without_1c_md_has_no_validate_query_in_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("bsl-ls")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "validate_query" not in text
    assert "<!-- @if" not in text


def test_deploy_disabled_1c_md_has_no_validate_query(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md", enabled=False)]),
        update=False)
    assert "validate_query" not in skill_text(tmp_path, "mcp-usage")


# --- деплой: query-analyze и переходы при обновлении ---

def test_deploy_1c_md_makes_validate_query_first_layer(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-md")]), update=False)
    text = skill_text(tmp_path, "query-analyze")
    assert "mcp__1c-md__validate_query" in text
    assert "analyze_query.py" in text          # локальные проверки остались
    assert "<!-- @if" not in text


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
        assert "<!-- @if" not in text, path
        assert "<!-- @endif" not in text, path


def test_template_markers_are_balanced():
    for path in content.CONTENT_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        content._render_conditional_blocks(text, True, filename=str(path))
        content._render_conditional_blocks(text, False, filename=str(path))
