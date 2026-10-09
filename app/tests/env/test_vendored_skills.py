from pathlib import Path
SK = Path(__file__).resolve().parents[3] / "template" / ".claude" / "skills"

def test_key_skills_present():
    for n in ("meta-info", "form-edit", "web-test", "1c-batch",
              "mcp-usage", "task-orchestration"):
        assert (SK / n / "SKILL.md").exists(), n

def test_duplicates_excluded():
    for n in ("db-dump-cf", "epf-build", "erf-build", "db-run", "db-create"):
        assert not (SK / n).exists(), n

def test_python_runtime():
    text = (SK / "meta-info" / "SKILL.md").read_text(encoding="utf-8")
    assert "python " in text and "powershell.exe" not in text
