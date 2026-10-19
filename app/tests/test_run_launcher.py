"""Тесты для run.py: resolve_mode, docker_env, host_plan, docker_plan.

Импорт run.py выполняется через sys.path — аналогично test_docker_create.py /
test_ssh_create.py.  run.py живёт в корне репо (ROOT), а не в src/agentmon.
"""
import importlib
import os
import sys
from pathlib import Path

# Вставляем корень репо в путь, чтобы `import run` нашёл run.py
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import run  # noqa: E402


# ---------------------------------------------------------------------------
# resolve_mode
# ---------------------------------------------------------------------------


class TestResolveMode:
    def test_empty_env_returns_host(self):
        assert run.resolve_mode({}) == "host"

    def test_explicit_host_returns_host(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": "host"}) == "host"

    def test_explicit_docker_returns_docker(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": "docker"}) == "docker"

    def test_docker_uppercase_returns_docker(self):
        # регистронезависимо
        assert run.resolve_mode({"AI1C_MONITOR_MODE": "DOCKER"}) == "docker"

    def test_docker_mixed_case(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": "Docker"}) == "docker"

    def test_junk_value_returns_host(self, capsys):
        result = run.resolve_mode({"AI1C_MONITOR_MODE": "vm"})
        assert result == "host"
        captured = capsys.readouterr()
        assert "vm" in captured.err  # предупреждение должно упомянуть значение

    def test_whitespace_around_docker(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": "  docker  "}) == "docker"

    def test_empty_string_returns_host(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": ""}) == "host"

    def test_none_value_returns_host(self):
        assert run.resolve_mode({"AI1C_MONITOR_MODE": None}) == "host"


# ---------------------------------------------------------------------------
# docker_env
# ---------------------------------------------------------------------------


class TestDockerEnv:
    def _make(self, dsn):
        return {"AGENTMON_DSN": dsn, "OTHER": "x"}

    def test_postgres_loopback_ipv4(self):
        # Хост И порт заменяются; userinfo (ai1c:ai1c) и путь (/ai1c) сохраняются
        env = self._make("postgresql://ai1c:ai1c@127.0.0.1:5433/ai1c")
        result = run.docker_env(env)
        assert result["AGENTMON_DSN"] == "postgresql://ai1c:ai1c@ai1c-postgres:5432/ai1c"

    def test_postgres_loopback_localhost_with_query(self):
        # localhost, userinfo (u:p), путь (/db) и query string (?sslmode=disable) сохраняются
        env = self._make("postgres://u:p@localhost:5432/db?sslmode=disable")
        result = run.docker_env(env)
        assert result["AGENTMON_DSN"] == "postgres://u:p@ai1c-postgres:5432/db?sslmode=disable"

    def test_postgres_loopback_localhost(self):
        env = self._make("postgres://user:pw@localhost:5432/db")
        result = run.docker_env(env)
        assert result["AGENTMON_DSN"] == "postgres://user:pw@ai1c-postgres:5432/db"

    def test_sqlite_unchanged(self):
        env = self._make("sqlite:///x.db")
        result = run.docker_env(env)
        assert result["AGENTMON_DSN"] == "sqlite:///x.db"

    def test_external_host_unchanged(self):
        env = self._make("postgresql://u:p@db.example.com:5432/db")
        result = run.docker_env(env)
        assert result["AGENTMON_DSN"] == "postgresql://u:p@db.example.com:5432/db"

    def test_missing_dsn_unchanged(self):
        env = {"OTHER": "x"}
        result = run.docker_env(env)
        assert "AGENTMON_DSN" not in result

    def test_input_not_mutated(self):
        original_dsn = "postgresql://ai1c:ai1c@127.0.0.1:5433/ai1c"
        env = self._make(original_dsn)
        run.docker_env(env)
        assert env["AGENTMON_DSN"] == original_dsn  # входной словарь не тронут

    def test_other_keys_preserved(self):
        env = self._make("postgresql://u:p@localhost:5432/db")
        result = run.docker_env(env)
        assert result["OTHER"] == "x"


# ---------------------------------------------------------------------------
# host_plan
# ---------------------------------------------------------------------------


class TestHostPlan:
    def test_argv_structure_no_extra(self):
        env = {"AGENTMON_PORT": "8765"}
        argv, returned_env = run.host_plan(env, [])
        assert argv[1:] == ["-m", "agentmon"]
        assert returned_env is env

    def test_argv_structure_with_extra(self):
        env = {}
        argv, _ = run.host_plan(env, ["--debug", "--port", "9000"])
        assert argv[1:] == ["-m", "agentmon", "--debug", "--port", "9000"]

    def test_argv_first_element_is_venv_python(self):
        argv, _ = run.host_plan({}, [])
        assert argv[0] == str(run.venv_python())

    def test_env_returned_as_is(self):
        env = {"KEY": "val"}
        _, returned_env = run.host_plan(env, [])
        assert returned_env is env  # тот же объект, без копирования


# ---------------------------------------------------------------------------
# docker_prep_cmds
# ---------------------------------------------------------------------------


class TestDockerPrepCmds:
    def test_returns_list_of_lists(self):
        result = run.docker_prep_cmds()
        assert isinstance(result, list)
        assert all(isinstance(cmd, list) for cmd in result)

    def test_contains_network_create(self):
        """docker_prep_cmds содержит команду создания сети ai1c-net."""
        result = run.docker_prep_cmds()
        assert ["docker", "network", "create", "ai1c-net"] in result

    def test_exact_value(self):
        """Ровно одна команда — идемпотентное создание сети."""
        result = run.docker_prep_cmds()
        assert result == [["docker", "network", "create", "ai1c-net"]]


# ---------------------------------------------------------------------------
# docker_plan
# ---------------------------------------------------------------------------


class TestDockerPlan:
    def test_argv_is_compose_up(self):
        argv, _ = run.docker_plan({}, [])
        assert argv == [
            "docker",
            "compose",
            "-f",
            str(run.COMPOSE_FILE),
            "up",
            "--build",
        ]

    def test_compose_file_path(self):
        assert run.COMPOSE_FILE == run.ROOT / "app" / "docker-compose.yml"

    def test_extra_args_not_forwarded(self):
        # extra_args в docker-режиме игнорируются
        argv, _ = run.docker_plan({}, ["--debug"])
        assert "--debug" not in argv

    def test_env_dsn_rewritten(self):
        env = {"AGENTMON_DSN": "postgresql://u:p@127.0.0.1:5432/db"}
        _, denv = run.docker_plan(env, [])
        assert "ai1c-postgres:5432" in denv["AGENTMON_DSN"]

    def test_input_env_not_mutated(self):
        env = {"AGENTMON_DSN": "postgresql://u:p@localhost:5432/db"}
        run.docker_plan(env, [])
        assert "@localhost:" in env["AGENTMON_DSN"]  # оригинал не тронут
