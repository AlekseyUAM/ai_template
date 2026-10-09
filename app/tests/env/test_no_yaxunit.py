from pathlib import Path
TPL = Path(__file__).resolve().parents[3] / "template" / ".claude"


def test_no_yaxunit_hardcoded():
    for rel in ("agents/tester.md", "skills/sdd-tdd-workflow/SKILL.md"):
        text = (TPL / rel).read_text(encoding="utf-8").lower()
        assert "yaxunit" not in text and "яксюнит" not in text
