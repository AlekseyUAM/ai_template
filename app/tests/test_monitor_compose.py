"""
Проверяем, что app/docker-compose.yml правильно сконфигурирован:
- config из .ai1c.env через ${...} (не захардкожен),
- корень репо смонтирован в /opt/ai1c,
- docker.sock смонтирован,
- host-gateway прописан для доступа к Postgres на хосте,
- PYTHONPATH указывает на src в смонтированном репо.

Тест читает файл как текст — YAML-парсер не требуется (PyYAML опционален).
"""
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent.parent / "docs"

import pytest

APP_DIR = Path(__file__).parent.parent
COMPOSE_FILE = APP_DIR / "docker-compose.yml"
REQUIREMENTS_FILE = APP_DIR / "requirements.txt"


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Опциональный YAML-разбор (если PyYAML доступен)
# ---------------------------------------------------------------------------
try:
    import yaml as _yaml  # noqa: F401
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@pytest.fixture(scope="module")
def compose_yaml(compose_text):
    if not _HAS_YAML:
        pytest.skip("PyYAML не установлен — YAML-тесты пропущены")
    import yaml
    return yaml.safe_load(compose_text)


# ---------------------------------------------------------------------------
# Текстовые проверки (всегда активны)
# ---------------------------------------------------------------------------

class TestComposeText:
    def test_host_gateway_extra_hosts(self, compose_text):
        """Postgres на хосте доступен через host.docker.internal."""
        assert "host.docker.internal:host-gateway" in compose_text

    def test_docker_sock_mounted(self, compose_text):
        """Монитор запускает docker-контейнеры → нужен docker.sock."""
        assert "/var/run/docker.sock:/var/run/docker.sock" in compose_text

    def test_repo_root_mounted(self, compose_text):
        """Корень репо смонтирован как /opt/ai1c (compose-файл лежит в app/)."""
        assert "../:/opt/ai1c" in compose_text

    def test_working_dir(self, compose_text):
        """working_dir указывает на app/ внутри смонтированного репо."""
        assert "working_dir: /opt/ai1c/app" in compose_text

    def test_pythonpath(self, compose_text):
        """PYTHONPATH ведёт к src/ пакета внутри смонтированного репо."""
        assert "PYTHONPATH" in compose_text
        assert "/opt/ai1c/app/src" in compose_text

    def test_agentmon_host_fixed(self, compose_text):
        """AGENTMON_HOST зафиксирован: слушать все интерфейсы в контейнере."""
        assert 'AGENTMON_HOST: "0.0.0.0"' in compose_text

    def test_agentmon_dsn_interpolated(self, compose_text):
        """AGENTMON_DSN берётся из .ai1c.env, а не захардкожен."""
        assert "${AGENTMON_DSN" in compose_text

    def test_port_interpolated(self, compose_text):
        """Порт берётся из .ai1c.env (с дефолтом 8765)."""
        assert "${AGENTMON_PORT" in compose_text


# ---------------------------------------------------------------------------
# YAML-проверки (если PyYAML доступен)
# ---------------------------------------------------------------------------

class TestComposeYaml:
    def test_extra_hosts_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        extra_hosts = svc.get("extra_hosts", [])
        assert any("host.docker.internal" in h and "host-gateway" in h for h in extra_hosts)

    def test_docker_sock_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        volumes = svc.get("volumes", [])
        assert any("/var/run/docker.sock" in str(v) for v in volumes)

    def test_repo_root_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        volumes = svc.get("volumes", [])
        assert any("/opt/ai1c" in str(v) for v in volumes)

    def test_working_dir_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        assert svc.get("working_dir") == "/opt/ai1c/app"

    def test_pythonpath_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        env = svc.get("environment", {})
        assert env.get("PYTHONPATH") == "/opt/ai1c/app/src"

    def test_agentmon_host_yaml(self, compose_yaml):
        svc = compose_yaml["services"]["agentmon"]
        env = svc.get("environment", {})
        assert env.get("AGENTMON_HOST") == "0.0.0.0"


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------

class TestRequirements:
    def test_httpx_omitted_by_default(self):
        """httpx нужен только опциональному Telegram-боту — в дефолтный образ его
        намеренно не кладём (образ лёгкий; см. test_pg_dependency и
        docs/DEPLOY-DOCKER.md). Telegram в docker — ручное добавление httpx."""
        text = REQUIREMENTS_FILE.read_text(encoding="utf-8")
        pkgs = {ln.split(";")[0].split("[")[0].strip().lower()
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("#")}
        assert "httpx" not in pkgs


# ---------------------------------------------------------------------------
# Документация
# ---------------------------------------------------------------------------

class TestDocs:
    def test_deploy_docker_md_exists(self):
        """docs/DEPLOY-DOCKER.md должен существовать — requirements.txt на него ссылается."""
        deploy_doc = DOCS_DIR / "DEPLOY-DOCKER.md"
        assert deploy_doc.exists(), f"Файл не найден: {deploy_doc}"

    def test_phases_mentions_monitor_mode(self):
        """docs/PHASES.md должен упоминать AI1C_MONITOR_MODE (docker-режим монитора реализован)."""
        phases = DOCS_DIR / "PHASES.md"
        assert phases.exists()
        assert "AI1C_MONITOR_MODE" in phases.read_text(encoding="utf-8")
