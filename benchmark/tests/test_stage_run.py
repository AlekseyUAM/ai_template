import pytest

from bench_run import BenchError
from stage_run import (DEFAULT_STAGE_LIMITS, parse_stage_limits,
                       parse_stage_overrides, stage_limit_minutes,
                       task_budget_minutes)


def test_parse_stage_overrides_empty():
    assert parse_stage_overrides([]) == {}


def test_parse_stage_overrides_values():
    assert parse_stage_overrides(["tests=5", "develop=12"]) == {
        "tests": 5, "develop": 12}


@pytest.mark.parametrize("raw", ["tests", "tests=0", "tests=-1", "tests=x"])
def test_parse_stage_overrides_rejects_bad(raw):
    with pytest.raises(BenchError):
        parse_stage_overrides([raw])


def test_parse_stage_limits_keeps_defaults_and_overrides():
    limits = parse_stage_limits(["tests=5"])
    assert limits["tests"] == 5
    assert limits["develop"] == DEFAULT_STAGE_LIMITS["develop"]


def test_task_budget_minutes_reads_int():
    assert task_budget_minutes({"max_minutes": 30}) == 30


def test_task_budget_minutes_accepts_numeric_string():
    assert task_budget_minutes({"max_minutes": "30"}) == 30


def test_task_budget_minutes_absent_or_invalid():
    assert task_budget_minutes({}) is None
    assert task_budget_minutes({"max_minutes": 0}) is None
    assert task_budget_minutes({"max_minutes": "x"}) is None


def test_stage_limit_default_without_task_budget():
    assert stage_limit_minutes("develop", None) == DEFAULT_STAGE_LIMITS["develop"]


def test_stage_limit_capped_by_remaining_budget():
    assert stage_limit_minutes("develop", 12) == 12


def test_stage_limit_uses_whole_remaining_budget():
    # With a task budget the default per-stage cap no longer limits the stage:
    # the stage may consume the whole remaining budget.
    assert stage_limit_minutes("testing", 20) == 20


def test_stage_limit_explicit_override():
    assert stage_limit_minutes("develop", 20, {"develop": 15}) == 15
    assert stage_limit_minutes("develop", 10, {"develop": 15}) == 10


def test_stage_limit_zero_when_budget_exhausted():
    assert stage_limit_minutes("develop", 0) == 0
    assert stage_limit_minutes("develop", 0.5) == 0


def test_stage_limit_minimum_one_minute():
    assert stage_limit_minutes("develop", 1.5) == 1


def test_stage_limit_unknown_stage_defaults_to_30():
    assert stage_limit_minutes("custom", None) == 30
