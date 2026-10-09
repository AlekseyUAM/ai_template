from pathlib import Path
A = Path(__file__).resolve().parents[3] / "template" / ".claude" / "agents"
MCP = ["bsl_ls", "1c_platform", "1c_naparnic", "code_index"]

def test_each_agent_lists_mcp_and_skills():
    for name in ("analyst","architect","developer","tester","reviewer"):
        t = (A / f"{name}.md").read_text(encoding="utf-8")
        assert "Возможности окружения" in t, name
        for m in MCP:
            assert m in t, f"{name}:{m}"
        assert "1c-batch" in t and ".claude/skills" in t

def test_developer_handles_db_load():
    t = (A / "developer.md").read_text(encoding="utf-8")
    assert "Загрузка в базу" in t
    assert "load-config" in t
