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
