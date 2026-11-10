"""Тесты для bootstrap.env_file_contents и bootstrap.setup_database.

Импорт bootstrap.py выполняется через sys.path — аналогично test_run_launcher.py.
bootstrap.py живёт в корне репо (ROOT); импорт не вызывает main() (она под if __name__).
"""
import sys
import types
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

# Вставляем корень репо в путь, чтобы `import bootstrap` нашёл bootstrap.py
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402


# ---------------------------------------------------------------------------
# Вспомогательный парсер KEY=value — воспроизводит логику run.load_env
# ---------------------------------------------------------------------------

def _parse_env(text: str) -> dict[str, str]:
    """Парсит текст .ai1c.env: пропускает # и пустые строки, делит по первому '='."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Тесты env_file_contents
# ---------------------------------------------------------------------------

_DSN = "postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c"
_DB = "/opt/ai1c/app/agentmon.db"


class TestEnvFileContents:
    def test_contains_dsn(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert f"AGENTMON_DSN={_DSN}" in text

    def test_contains_db(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert f"AGENTMON_DB={_DB}" in text

    def test_ends_with_newline(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert text.endswith("\n")

    def test_round_trip_parse_keys(self):
        """Текст корректно разбирается парсером KEY=value — ключи присутствуют."""
        text = bootstrap.env_file_contents(_DSN, _DB)
        env = _parse_env(text)
        assert env["AGENTMON_DSN"] == _DSN
        assert env["AGENTMON_DB"] == _DB
        assert env["AI1C_PG_MODE"] == "host"

    def test_no_spaces_around_equals(self):
        """KEY=value без пробелов вокруг '=' для совместимости с run.load_env."""
        text = bootstrap.env_file_contents(_DSN, _DB)
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            assert " = " not in line, f"пробелы вокруг '=' в строке: {line!r}"

    # --- новые тесты AI1C_PG_MODE -------------------------------------------

    def test_default_pg_mode_is_host(self):
        """По умолчанию AI1C_PG_MODE=host."""
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert "AI1C_PG_MODE=host" in text

    def test_explicit_pg_mode_docker(self):
        """При pg_mode='docker' файл содержит AI1C_PG_MODE=docker."""
        text = bootstrap.env_file_contents(_DSN, _DB, pg_mode="docker")
        assert "AI1C_PG_MODE=docker" in text

    def test_round_trip_parse_pg_mode(self):
        """Round-trip: парсер находит все ключи, включая AI1C_PG_MODE."""
        text = bootstrap.env_file_contents(_DSN, _DB, pg_mode="host")
        env = _parse_env(text)
        assert env["AGENTMON_DSN"] == _DSN
        assert env["AGENTMON_DB"] == _DB
        assert env["AI1C_PG_MODE"] == "host"

    def test_round_trip_parse_pg_mode_docker(self):
        """Round-trip для pg_mode=docker."""
        text = bootstrap.env_file_contents(_DSN, _DB, pg_mode="docker")
        env = _parse_env(text)
        assert env["AI1C_PG_MODE"] == "docker"


# ---------------------------------------------------------------------------
# Тесты setup_database
# ---------------------------------------------------------------------------

_SENTINEL_DSN = "postgresql://ai1c:ai1c@127.0.0.1:15432/ai1c"
_SQLITE_PATH = str(bootstrap.ROOT / "app" / "store.db")


def _make_pg_portable_stub(dsn: str) -> types.ModuleType:
    """Создаёт минимальный модуль-заглушку pg_portable с нужным provision."""
    mod = types.ModuleType("pg_portable")
    mod.provision = MagicMock(return_value=dsn)
    return mod


class TestSetupDatabaseHostMode:
    """AI1C_PG_MODE=host (дефолт): pg_portable.provision + psycopg install."""

    def test_host_mode_returns_sentinel_dsn(self, monkeypatch):
        """provision возвращает DSN → setup_database отдаёт его + pg_mode='host'."""
        stub = _make_pg_portable_stub(_SENTINEL_DSN)
        monkeypatch.setenv("AI1C_PG_MODE", "host")
        monkeypatch.setattr(bootstrap, "pg_portable", stub, raising=False)
        monkeypatch.setattr(bootstrap, "run", MagicMock())
        monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))

        dsn, pg_mode = bootstrap.setup_database()

        assert dsn == _SENTINEL_DSN
        assert pg_mode == "host"

    def test_host_mode_default_env(self, monkeypatch):
        """Без AI1C_PG_MODE в окружении → тот же хост-путь."""
        monkeypatch.delenv("AI1C_PG_MODE", raising=False)
        stub = _make_pg_portable_stub(_SENTINEL_DSN)
        monkeypatch.setattr(bootstrap, "pg_portable", stub, raising=False)
        monkeypatch.setattr(bootstrap, "run", MagicMock())
        monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))

        dsn, pg_mode = bootstrap.setup_database()

        assert dsn == _SENTINEL_DSN
        assert pg_mode == "host"

    def test_host_mode_installs_psycopg(self, monkeypatch):
        """При успешной provision должен вызываться pip install psycopg[binary]."""
        stub = _make_pg_portable_stub(_SENTINEL_DSN)
        monkeypatch.setenv("AI1C_PG_MODE", "host")
        monkeypatch.setattr(bootstrap, "pg_portable", stub, raising=False)
        fake_run = MagicMock()
        monkeypatch.setattr(bootstrap, "run", fake_run)
        monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))

        bootstrap.setup_database()

        # Должен быть хотя бы один вызов pip install psycopg[binary]
        calls_str = [" ".join(str(a) for a in call.args[0]) for call in fake_run.call_args_list]
        assert any("psycopg[binary]" in c for c in calls_str)

    def test_host_mode_provision_raises_sqlite_fallback(self, monkeypatch):
        """provision бросает → warn + SQLite-фолбэк; psycopg НЕ устанавливается."""
        stub = types.ModuleType("pg_portable")
        stub.provision = MagicMock(side_effect=RuntimeError("тест-ошибка"))
        monkeypatch.setenv("AI1C_PG_MODE", "host")
        monkeypatch.setattr(bootstrap, "pg_portable", stub, raising=False)
        fake_run = MagicMock()
        monkeypatch.setattr(bootstrap, "run", fake_run)
        monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))

        warned: list[str] = []
        monkeypatch.setattr(bootstrap, "warn", lambda msg: warned.append(msg))

        dsn, pg_mode = bootstrap.setup_database()

        assert dsn == _SQLITE_PATH
        assert pg_mode == "host"
        # warn был вызван с упоминанием SQLite
        assert any("SQLite" in w for w in warned)
        # psycopg не устанавливался
        calls_str = [" ".join(str(a) for a in call.args[0]) for call in fake_run.call_args_list]
        assert not any("psycopg[binary]" in c for c in calls_str)


class TestSetupDatabaseDockerMode:
    """AI1C_PG_MODE=docker: старый docker-путь."""

    def test_docker_mode_no_docker_sqlite_fallback(self, monkeypatch):
        """docker-режим + docker недоступен → SQLite + pg_mode='docker'."""
        monkeypatch.setenv("AI1C_PG_MODE", "docker")
        monkeypatch.setattr(bootstrap, "docker_available", MagicMock(return_value=False))

        dsn, pg_mode = bootstrap.setup_database()

        assert dsn == _SQLITE_PATH
        assert pg_mode == "docker"

    def test_docker_mode_uses_docker_path(self, monkeypatch):
        """docker-режим + docker доступен → docker-ветка, возвращает postgres DSN."""
        monkeypatch.setenv("AI1C_PG_MODE", "docker")
        monkeypatch.setattr(bootstrap, "docker_available", MagicMock(return_value=True))
        # Контейнер уже запущен на порту 5499
        monkeypatch.setattr(bootstrap, "pg_container_port", MagicMock(return_value=5499))
        fake_run = MagicMock()
        monkeypatch.setattr(bootstrap, "run", fake_run)
        monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))
        # Заглушка pg_isready — возвращает rc=0 сразу
        import subprocess as _sp
        fake_proc = MagicMock()
        fake_proc.returncode = 0
        monkeypatch.setattr(_sp, "run", MagicMock(return_value=fake_proc))

        dsn, pg_mode = bootstrap.setup_database()

        assert dsn == "postgresql://ai1c:ai1c@127.0.0.1:5499/ai1c"
        assert pg_mode == "docker"


# ---------------------------------------------------------------------------
# write_env: пользовательские ключи не теряются
# ---------------------------------------------------------------------------

class TestWriteEnvMerge:
    def test_preserves_user_keys(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".ai1c.env"
        env_file.write_text(
            "# комментарий пользователя\n"
            "AGENTMON_DSN=sqlite:///old.db\n"
            "AGENTMON_TG_TOKEN=secret-token\n"
            "AGENTMON_CLAUDE_CMD=/opt/claude --flag\n",
            encoding="utf-8")
        monkeypatch.setattr(bootstrap, "ENV_FILE", env_file)
        monkeypatch.setattr(bootstrap, "say", lambda msg: None)

        bootstrap.write_env("postgresql://u@h/db", "host")

        text = env_file.read_text(encoding="utf-8")
        assert "AGENTMON_DSN=postgresql://u@h/db" in text
        assert "AGENTMON_TG_TOKEN=secret-token" in text
        assert "AGENTMON_CLAUDE_CMD=/opt/claude --flag" in text
        assert "# комментарий пользователя" in text
        assert text.count("AGENTMON_DSN=") == 1

    def test_adds_missing_managed_keys(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".ai1c.env"
        env_file.write_text("AGENTMON_TG_TOKEN=t\n", encoding="utf-8")
        monkeypatch.setattr(bootstrap, "ENV_FILE", env_file)
        monkeypatch.setattr(bootstrap, "say", lambda msg: None)

        bootstrap.write_env("sqlite:///x.db", "docker")

        env = _parse_env(env_file.read_text(encoding="utf-8"))
        assert env["AGENTMON_TG_TOKEN"] == "t"
        assert env["AGENTMON_DSN"] == "sqlite:///x.db"
        assert env["AI1C_PG_MODE"] == "docker"


def test_docker_health_timeout_falls_back_to_sqlite(monkeypatch):
    """Контейнер не ответил за 30 с → SQLite, а не DSN на мёртвую БД."""
    monkeypatch.setenv("AI1C_PG_MODE", "docker")
    monkeypatch.setattr(bootstrap, "docker_available", MagicMock(return_value=True))
    monkeypatch.setattr(bootstrap, "pg_container_port", MagicMock(return_value=5499))
    monkeypatch.setattr(bootstrap, "run", MagicMock())
    monkeypatch.setattr(bootstrap, "venv_python", MagicMock(return_value="/fake/python"))
    monkeypatch.setattr(bootstrap.time, "sleep", lambda s: None)
    import subprocess as _sp
    fake_proc = MagicMock()
    fake_proc.returncode = 1             # pg_isready всегда не готов
    monkeypatch.setattr(_sp, "run", MagicMock(return_value=fake_proc))
    warned = []
    monkeypatch.setattr(bootstrap, "warn", lambda msg: warned.append(msg))

    dsn, pg_mode = bootstrap.setup_database()

    assert dsn == _SQLITE_PATH
    assert any("SQLite" in w for w in warned)


def test_docker_compose_failure_falls_back_to_sqlite(monkeypatch):
    import subprocess as _sp
    monkeypatch.setenv("AI1C_PG_MODE", "docker")
    monkeypatch.setattr(bootstrap, "docker_available", MagicMock(return_value=True))
    monkeypatch.setattr(bootstrap, "pg_container_port", MagicMock(return_value=None))
    monkeypatch.setattr(bootstrap, "free_port", MagicMock(return_value=5500))
    def fake_compose(args, **kwargs):
        if "up" in args:
            raise _sp.CalledProcessError(1, ["docker", "compose"])
        return MagicMock(returncode=0)
    monkeypatch.setattr(bootstrap, "compose", fake_compose)
    warned = []
    monkeypatch.setattr(bootstrap, "warn", lambda msg: warned.append(msg))

    dsn, pg_mode = bootstrap.setup_database()

    assert dsn == _SQLITE_PATH
    assert any("SQLite" in w for w in warned)
