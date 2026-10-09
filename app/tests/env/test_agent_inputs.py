from pathlib import Path

AGENTS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "agents"


def test_each_agent_input_is_degradable():
    # downstream-агенты должны допускать отсутствие предыдущих артефактов и падать на TASK.md
    for name in ("architect", "developer", "tester", "reviewer"):
        text = (AGENTS / f"{name}.md").read_text(encoding="utf-8")
        assert "TASK.md" in text, f"{name}: нет упоминания TASK.md как fallback"


def test_analyst_explicitly_mentions_task_md():
    # analyst должен явно упомянуть TASK.md
    text = (AGENTS / "analyst.md").read_text(encoding="utf-8")
    assert "TASK.md" in text, "analyst: нет упоминания TASK.md"
