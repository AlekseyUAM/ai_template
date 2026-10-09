"""Tests that psycopg is listed as a project dependency in pyproject.toml."""
import pathlib


def test_pyproject_contains_psycopg():
    """app/pyproject.toml must declare a psycopg dependency for PostgreSQL support."""
    pyproject = pathlib.Path(__file__).parents[2] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "psycopg" in text, (
        "psycopg not found in app/pyproject.toml — "
        "add psycopg[binary] to the [project] dependencies list"
    )


def test_requirements_contains_psycopg():
    """Прод-образ ставит requirements.txt — psycopg обязан быть и там (иначе
    контейнер против postgres падает ModuleNotFoundError при первом connect)."""
    req = pathlib.Path(__file__).parents[2] / "requirements.txt"
    assert "psycopg" in req.read_text(encoding="utf-8")


def test_requirements_has_no_test_only_deps():
    """pytest/httpx — тестовые зависимости, не должны попадать в прод-образ."""
    req = pathlib.Path(__file__).parents[2] / "requirements.txt"
    lines = [ln.strip() for ln in req.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    pkgs = {ln.split(";")[0].split("[")[0].strip().lower() for ln in lines}
    assert "pytest" not in pkgs and "httpx" not in pkgs
