from pathlib import Path
A = Path(__file__).resolve().parents[3] / "template" / ".claude" / "agents"
SKILLS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "skills"
MCP = ["bsl_ls", "1c_platform", "1c_naparnic", "code_index"]

def test_each_agent_lists_mcp_and_skills():
    for name in ("analyst","architect","developer-tests","developer","reviewer"):
        t = (A / f"{name}.md").read_text(encoding="utf-8")
        assert "Возможности окружения" in t, name
        for m in MCP:
            assert m in t, f"{name}:{m}"
        assert "1c-batch" in t and ".claude/skills" in t

def test_orchestrator_handles_db_load():
    # Загрузку в ИБ / обновление БД ведёт оркестратор (после develop, по флагу
    # update_db), а не разработчик.
    t = (SKILLS / "task-orchestration" / "SKILL.md").read_text(encoding="utf-8")
    assert "load-config" in t
    assert "update_db" in t
