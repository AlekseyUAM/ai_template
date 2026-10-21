"""Content-тесты собственного Dockerfile образа агента.

Проверяем ключевые инварианты самодостаточной сборки без реального docker build.
"""
from agentmon.env import docker_image as di


def _text():
    return di.DOCKERFILE_PATH.read_text(encoding="utf-8")


def test_dockerfile_exists():
    assert di.DOCKERFILE_PATH.is_file(), f"нет Dockerfile: {di.DOCKERFILE_PATH}"


def test_copies_fixed_distr_name():
    # build_agent_image кладёт дистрибутив как distr.zip — Dockerfile ждёт это имя
    assert "distr.zip" in _text()


def test_installs_claude_cli():
    assert "@anthropic-ai/claude-code" in _text()


def test_runs_unattended_platform_install():
    t = _text()
    assert "--mode unattended" in t
    assert ".run" in t


def test_creates_current_symlink():
    assert "/opt/1cv8/current" in _text()


def test_sets_ru_locale():
    assert "ru_RU.UTF-8" in _text()


def test_no_deps_sandbox_leftovers():
    t = _text()
    # лёгкий образ: без фреймворка / bridge / test-runner / vanessa
    for forbidden in ("1c-agent-based-dev-framework", "mcp-bsl-lsp-bridge",
                      "mcp-yaxunit-runner", "VanessaExt"):
        assert forbidden not in t, f"лишнее в Dockerfile: {forbidden}"
