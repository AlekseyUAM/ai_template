import pytest
from agentmon.env.migration import migrate
from agentmon.env.config_schema import SCHEMA_VERSION


def test_adds_schema_version_when_absent():
    data = migrate({"project_name": "x"})
    assert data["schema_version"] == SCHEMA_VERSION


def test_already_current_is_unchanged():
    data = {"schema_version": SCHEMA_VERSION, "project_name": "x"}
    assert migrate(dict(data)) == data


def test_future_version_is_error():
    with pytest.raises(ValueError):
        migrate({"schema_version": SCHEMA_VERSION + 1})
