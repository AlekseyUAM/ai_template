from pathlib import Path

TPL = Path(__file__).resolve().parents[3] / "template" / ".claude"
CHECKLISTS = TPL / "checklists"
RULES = TPL / "rules"


def test_each_checklist_lists_environment():
    for name in ("analyst", "architect", "developer-tests", "developer",
                 "reviewer", "technical-writer"):
        text = (CHECKLISTS / f"{name}.md").read_text(encoding="utf-8")
        assert "Возможности окружения" in text, name
        assert "code_index" in text, name
        assert ".claude/skills" in text, name


def test_bsl_checklists_mention_bsl_ls():
    # bsl_ls нужен там, где пишут/проверяют BSL или выносят вердикт.
    for name in ("developer", "developer-tests", "reviewer"):
        text = (CHECKLISTS / f"{name}.md").read_text(encoding="utf-8")
        assert "bsl_ls" in text, name


def test_each_checklist_has_output_artifact():
    for name in ("analyst", "architect", "developer-tests", "developer",
                 "reviewer", "technical-writer"):
        text = (CHECKLISTS / f"{name}.md").read_text(encoding="utf-8")
        assert "## Выход" in text, name


def test_single_agent_rule_handles_db_load():
    # Загрузку в ИБ / обновление БД ведёт исполнитель (single-agent), а не
    # отдельный оркестратор.
    text = (RULES / "single-agent-workflow.md").read_text(encoding="utf-8")
    assert "load-config" in text
    assert "update_db" in text


def test_long_operations_are_synchronous():
    # В `claude -p` ход завершается по end_turn, и фоновые задачи убиваются:
    # загрузка/тесты должны запускаться синхронно, а не через run_in_background.
    for path in (RULES / "single-agent-workflow.md",
                 RULES / "optimized-config-loading.md"):
        text = path.read_text(encoding="utf-8")
        assert "синхронно" in text, path
        assert "run_in_background" in text, path
        assert "харнесс сам разбудит" not in text, path
