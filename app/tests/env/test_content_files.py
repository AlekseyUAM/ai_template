from pathlib import Path

CONTENT = Path(__file__).resolve().parents[3] / "template" / ".claude"
AGENTS = {"analyst", "architect", "developer", "tester", "reviewer"}
SKILLS = {"mcp-usage", "bsl-coding-standards", "sdd-tdd-workflow", "task-orchestration",
          "query-analyze", "query-review"}
RULES = {"search-before-write", "verify-with-syntax-checker", "task-artifacts",
         "task-lifecycle", "cyclic-review-workflow", "optimized-config-loading"}


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "нет frontmatter"
    end = text.index("\n---", 4)
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def test_exactly_five_agents():
    files = {p.stem for p in (CONTENT / "agents").glob("*.md")}
    assert files == AGENTS


def test_agent_frontmatter_valid():
    for name in AGENTS:
        text = (CONTENT / "agents" / f"{name}.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
        assert "tools" in fm
        assert fm["model"] == "{{MODEL}}"
        assert fm["effort"] == "{{EFFORT}}"
        assert len(text) > 400, "промпт слишком короткий"


def test_skills_present_and_valid():
    found = {p.name for p in (CONTENT / "skills").iterdir() if p.is_dir()}
    assert SKILLS <= found
    for name in SKILLS:
        text = (CONTENT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
        assert "allowed-tools" in fm


def test_rules_present_and_valid():
    found = {p.stem for p in (CONTENT / "rules").glob("*.md")}
    assert found == RULES
    for name in RULES:
        text = (CONTENT / "rules" / f"{name}.md").read_text(encoding="utf-8")
        fm = _frontmatter(text)
        assert fm["name"] == name
        assert fm["description"]
