from pathlib import Path

CONTENT = Path(__file__).resolve().parents[3] / "template" / ".claude"
CHECKLISTS = {"analyst", "architect", "developer-tests", "developer", "reviewer",
              "technical-writer"}
SKILLS = {"mcp-usage", "bsl-coding-standards", "sdd-tdd-workflow",
          "query-analyze", "query-review"}
RULES = {"search-before-write", "verify-with-syntax-checker", "task-artifacts",
         "task-lifecycle", "cyclic-review-workflow", "optimized-config-loading",
         "run-unit-tests", "user-feedback", "single-agent-workflow"}


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "нет frontmatter"
    end = text.index("\n---", 4)
    fm = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def test_checklists_set_matches():
    files = {p.stem for p in (CONTENT / "checklists").glob("*.md")}
    assert files == CHECKLISTS


def test_checklists_are_not_agents():
    # Чеклисты не должны выглядеть как определения субагентов: без frontmatter
    # Claude Code не показывает их в списке агентов и не тратит контекст.
    for name in CHECKLISTS:
        text = (CONTENT / "checklists" / f"{name}.md").read_text(encoding="utf-8")
        assert not text.startswith("---\n"), f"{name}: frontmatter субагента"
        assert "Чеклист этапа" in text, f"{name}: нет шапки чеклиста"
        assert len(text) > 400, "чеклист слишком короткий"


def test_agents_dir_removed():
    assert not (CONTENT / "agents").exists()


def test_skills_present_and_valid():
    found = {p.name for p in (CONTENT / "skills").iterdir() if p.is_dir()}
    assert SKILLS <= found
    assert "task-orchestration" not in found
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
