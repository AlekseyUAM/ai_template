"""
Тесты для task_model.py — модели задач v2 с гейтами.
"""
import pytest
from agentmon.env.task_model import (
    DEFAULT_STAGES,
    STAGE_NAMES,
    build_stages,
    overall_status,
    validate_task,
)


class TestBuildStages:
    """Тесты для build_stages(enabled_names, gated_names=())."""

    def test_build_stages_empty(self):
        """Все этапы отключены при пустом enabled_names."""
        stages = build_stages([])
        assert len(stages) == 7
        for stage in stages:
            assert stage["enabled"] is False
            assert stage["status"] == "skipped"
            assert stage["approved"] is False
            assert stage["gate"] is False
            assert stage["changed_files"] == []

    def test_build_stages_all_enabled(self):
        """Все этапы включены."""
        stages = build_stages(STAGE_NAMES)
        assert len(stages) == 7
        for stage in stages:
            assert stage["enabled"] is True
            assert stage["status"] == "pending"
            assert stage["approved"] is False
            assert stage["gate"] is False
            assert stage["changed_files"] == []

    def test_build_stages_partial_enabled(self):
        """Частично включённые этапы."""
        enabled = ["analyze", "plan", "develop"]
        stages = build_stages(enabled)

        for stage in stages:
            if stage["name"] in enabled:
                assert stage["enabled"] is True
                assert stage["status"] == "pending"
            else:
                assert stage["enabled"] is False
                assert stage["status"] == "skipped"

    def test_build_stages_with_gates(self):
        """Этапы с гейтами обозначены правильно."""
        enabled = ["analyze", "plan", "develop"]
        gated = ["plan", "review"]
        stages = build_stages(enabled, gated_names=gated)

        for stage in stages:
            if stage["name"] in gated:
                assert stage["gate"] is True
            else:
                assert stage["gate"] is False

    def test_build_stages_has_all_required_fields(self):
        """Каждый этап содержит все необходимые поля."""
        stages = build_stages(["analyze"])

        required_fields = {
            "name", "enabled", "subagent", "artifact", "gate",
            "approved", "status", "changed_files"
        }

        for stage in stages:
            assert set(stage.keys()) == required_fields

    def test_build_stages_preserves_stage_defaults(self):
        """Стадии содержат правильные subagent и artifact."""
        stages = build_stages(STAGE_NAMES)

        stage_dict = {s["name"]: s for s in stages}
        assert stage_dict["analyze"]["subagent"] == "analyst"
        assert stage_dict["analyze"]["artifact"] == "ANALYZE.md"
        assert stage_dict["plan"]["subagent"] == "architect"
        assert stage_dict["develop"]["subagent"] == "developer"
        assert stage_dict["testing"]["subagent"] == "tester"


class TestOverallStatus:
    """Тесты для overall_status(stages) -> str."""

    def test_overall_status_no_enabled_stages(self):
        """Если нет включённых этапов -> 'done'."""
        stages = build_stages([])
        assert overall_status(stages) == "done"

    def test_overall_status_all_done(self):
        """Все включённые этапы done -> 'done'."""
        stages = build_stages(["analyze", "plan"])
        for stage in stages:
            if stage["enabled"]:
                stage["status"] = "done"
        assert overall_status(stages) == "done"

    def test_overall_status_any_failed(self):
        """Любой enabled этап failed -> 'failed'."""
        stages = build_stages(["analyze", "plan", "develop"])
        stages[0]["status"] = "failed"  # analyze failed
        stages[1]["status"] = "done"
        stages[2]["status"] = "pending"
        assert overall_status(stages) == "failed"

    def test_overall_status_any_running(self):
        """Любой enabled этап running -> 'running' (если нет failed)."""
        stages = build_stages(["analyze", "plan", "develop"])
        stages[0]["status"] = "done"
        stages[1]["status"] = "running"
        stages[2]["status"] = "pending"
        assert overall_status(stages) == "running"

    def test_overall_status_planned_default(self):
        """Если есть pending enabled -> 'planned'."""
        stages = build_stages(["analyze", "plan"])
        stages[0]["status"] = "done"
        stages[1]["status"] = "pending"
        assert overall_status(stages) == "planned"

    def test_overall_status_awaiting_user_gated(self):
        """Гейтед этап done, not approved, и есть enabled pending после -> 'awaiting_user'."""
        stages = build_stages(["analyze", "plan", "develop"])

        # Установим gates: plan гейтирован
        stages[1]["gate"] = True
        stages[1]["status"] = "done"
        stages[1]["approved"] = False  # не одобрен
        stages[2]["status"] = "pending"  # есть pending после

        assert overall_status(stages) == "awaiting_user"

    def test_overall_status_awaiting_user_multiple_gates(self):
        """Проверка awaiting_user с несколькими гейтами."""
        stages = build_stages(["analyze", "plan", "tests", "develop", "testing"])

        stages[1]["gate"] = True
        stages[1]["status"] = "done"
        stages[1]["approved"] = False
        stages[2]["status"] = "pending"

        assert overall_status(stages) == "awaiting_user"

    def test_overall_status_awaiting_user_not_triggered_when_no_pending_after(self):
        """awaiting_user не срабатывает если нет pending после гейта."""
        stages = build_stages(["analyze", "plan", "develop"])

        stages[0]["status"] = "done"  # analyze
        stages[1]["gate"] = True  # plan
        stages[1]["status"] = "done"
        stages[1]["approved"] = False
        stages[3]["status"] = "done"  # develop (индекс 3)

        # Раз нет enabled pending после гейта, это done (не awaiting_user)
        assert overall_status(stages) == "done"

    def test_overall_status_priority_failed_over_awaiting_user(self):
        """Приоритет: failed > awaiting_user."""
        stages = build_stages(["analyze", "plan", "develop"])

        stages[0]["status"] = "failed"  # Failed в analyze
        stages[1]["gate"] = True
        stages[1]["status"] = "done"
        stages[1]["approved"] = False
        stages[2]["status"] = "pending"

        assert overall_status(stages) == "failed"

    def test_overall_status_awaiting_user_approved_gate_no_trigger(self):
        """Если гейтированный этап уже approved -> не awaiting_user."""
        stages = build_stages(["analyze", "plan", "develop"])

        stages[1]["gate"] = True
        stages[1]["status"] = "done"
        stages[1]["approved"] = True  # одобрен
        stages[2]["status"] = "pending"

        assert overall_status(stages) != "awaiting_user"


class TestValidateTask:
    """Тесты для validate_task(*, name, goal, plan, constraints, tests, enabled_names)."""

    def test_validate_task_all_valid(self):
        """Все поля валидны -> пустой список ошибок."""
        errors = validate_task(
            name="Задача 1",
            identifier="TASK-1",
            goal="Цель задачи",
            plan="План выполнения",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=["analyze"]
        )
        assert errors == []

    def test_validate_task_empty_identifier(self):
        """Пустой идентификатор -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=[]
        )
        assert any("идентификатор" in e.lower() for e in errors)

    def test_validate_task_identifier_with_path_separators(self):
        """Идентификатор с '/', '\\' или '..' -> ошибка."""
        for bad in ("a/b", "a\\b", "..", "x/../y"):
            errors = validate_task(
                name="Задача",
                identifier=bad,
                goal="Цель",
                plan="План",
                constraints="Ограничения",
                tests="Тесты",
                enabled_names=[]
            )
            assert any("идентификатор" in e.lower() for e in errors), bad

    def test_validate_task_empty_name(self):
        """Пустое имя -> ошибка."""
        errors = validate_task(
            name="",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=[]
        )
        assert any("название" in e.lower() for e in errors)

    def test_validate_task_empty_goal(self):
        """Пустая цель -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="",
            plan="План",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=[]
        )
        assert any("цель" in e.lower() for e in errors)

    def test_validate_task_empty_plan(self):
        """Пустой план -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=[]
        )
        assert any("план" in e.lower() for e in errors)

    def test_validate_task_empty_constraints(self):
        """Пустые ограничения -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="",
            tests="Тесты",
            enabled_names=[]
        )
        assert any("ограничения" in e.lower() for e in errors)

    def test_validate_task_tests_enabled_but_empty(self):
        """Этап 'tests' включен, но tests текст пуст -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="",
            enabled_names=["tests"]
        )
        assert any("tests" in e.lower() for e in errors)

    def test_validate_task_testing_without_tests_stage(self):
        """Этап 'testing' включен без 'tests' -> ошибка."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=["testing"]  # testing есть, но tests нет
        )
        assert any("testing" in e.lower() and "tests" in e.lower() for e in errors)

    def test_validate_task_both_tests_and_testing_valid(self):
        """'testing' с 'tests' -> валидно."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="Тесты",
            enabled_names=["tests", "testing"]
        )
        # Не должно быть ошибки про testing/tests
        assert not any("testing" in e.lower() and "tests" in e.lower() for e in errors)

    def test_validate_task_multiple_errors(self):
        """Множество ошибок."""
        errors = validate_task(
            name="",
            identifier="TASK-1",
            goal="",
            plan="",
            constraints="",
            tests="",
            enabled_names=["tests"]
        )
        # Должно быть несколько ошибок
        assert len(errors) >= 5

    def test_validate_task_tests_content_with_tests_stage(self):
        """'tests' включен с непустым текстом -> валидно."""
        errors = validate_task(
            name="Задача",
            identifier="TASK-1",
            goal="Цель",
            plan="План",
            constraints="Ограничения",
            tests="unit: check x; integration: check y",
            enabled_names=["tests"]
        )
        assert not any("tests" in e.lower() for e in errors)
