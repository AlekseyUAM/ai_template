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
        assert "Stage checklist" in text, f"{name}: нет шапки чеклиста"
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


def test_mandatory_analyzers_are_documented():
    """Все обязательные скрипты явно названы в чеклистах и навыках."""
    code_scripts = ("analyze_code.py", "check_event_handlers.py")
    query_scripts = ("extract_queries.py", "analyze_query.py")
    for name in ("developer", "reviewer", "developer-tests"):
        text = (CONTENT / "checklists" / f"{name}.md").read_text(encoding="utf-8")
        for needle in code_scripts + query_scripts:
            assert needle in text, f"{name}.md: нет {needle}"
        assert "check_metadata_names.py --changed" in text, \
            f"{name}.md: нет check_metadata_names.py --changed"
    code_skill = (CONTENT / "skills" / "code-analyze" / "SKILL.md").read_text(
        encoding="utf-8")
    for needle in code_scripts + ("check_metadata_names.py --changed",):
        assert needle in code_skill, f"code-analyze/SKILL.md: нет {needle}"
    query_skill = (CONTENT / "skills" / "query-analyze" / "SKILL.md").read_text(
        encoding="utf-8")
    for needle in query_scripts:
        assert needle in query_skill, f"query-analyze/SKILL.md: нет {needle}"
