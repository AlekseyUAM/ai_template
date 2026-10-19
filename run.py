#!/usr/bin/env python3
"""Запуск Web UI Agent Monitor (кроссплатформенно). Одна команда: python run.py

Требует предварительного  python bootstrap.py.

Режим запуска задаётся ключом AI1C_MONITOR_MODE в .ai1c.env:
  (пусто или "host")  — хост-режим (поведение по умолчанию, запуск через .venv)
  "docker"            — docker-режим (docker compose up --build)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".ai1c.env"
COMPOSE_FILE = ROOT / "app" / "docker-compose.yml"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def load_env(env: dict[str, str]) -> None:
    """Прочитать .ai1c.env (формат KEY=value) в окружение."""
    if not ENV_FILE.is_file():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            env[key.strip()] = value.strip()


def resolve_mode(env: dict) -> str:
    """Вернуть режим запуска монитора: "host" или "docker".

    Читает AI1C_MONITOR_MODE из env (уже загруженного из .ai1c.env).
    Значения:
      пусто / "host"  → "host"  (режим по умолчанию)
      "docker"        → "docker"
      любой другой    → предупреждение в stderr, возврат "host"
    """
    raw = (env.get("AI1C_MONITOR_MODE") or "").strip().lower()
    if raw in ("", "host"):
        return "host"
    if raw == "docker":
        return "docker"
    print(
        f"[run] WARNING: неизвестный AI1C_MONITOR_MODE={raw!r}, используется host",
        file=sys.stderr,
    )
    return "host"


def host_plan(env: dict, extra_args: list) -> tuple:
    """Вернуть (argv, env) для запуска агентмона в хост-режиме.

    Поведение идентично оригинальному run.py — замена os.execve/subprocess.run.
    """
    argv = [str(venv_python()), "-m", "agentmon", *extra_args]
    return argv, env


def docker_env(env: dict) -> dict:
    """Вернуть копию env с переписанным AGENTMON_DSN для docker-режима.

    Если DSN — postgres(ql)://...@127.0.0.1:PORT/... или @localhost:PORT/...,
    хост и порт заменяются на ai1c-postgres:5432 — имя контейнера и его
    внутренний порт в общей сети ai1c-net.  Хост-опубликованный порт (PORT)
    недоступен из контейнера через loopback; оба контейнера (монитор и postgres)
    присоединяются к ai1c-net и общаются напрямую по имени сервиса.
    SQLite DSN, отсутствующий DSN и нелокальные хосты остаются без изменений.
    Входной словарь не мутируется.
    """
    result = dict(env)
    dsn = result.get("AGENTMON_DSN", "")
    if dsn.startswith(("postgres://", "postgresql://")):
        # Заменяем @127.0.0.1:<port> или @localhost:<port> → @ai1c-postgres:5432
        dsn_new = re.sub(
            r"@(127\.0\.0\.1|localhost):\d+",
            "@ai1c-postgres:5432",
            dsn,
            count=1,
        )
        if dsn_new != dsn:
            result["AGENTMON_DSN"] = dsn_new
    return result


def docker_prep_cmds() -> list[list[str]]:
    """Вернуть список команд подготовки docker-окружения перед compose up.

    Сейчас — одна команда: создать общую сеть ai1c-net (идемпотентно).
    Если сеть уже существует, docker network create вернёт ненулевой код —
    main() намеренно игнорирует этот код, чтобы не прерывать запуск.
    """
    return [["docker", "network", "create", "ai1c-net"]]


def docker_plan(env: dict, extra_args: list) -> tuple:
    """Вернуть (argv, env) для запуска монитора через docker compose.

    extra_args (аргументы, переданные в run.py) в docker-режиме НЕ пробрасываются
    в compose-команду — они предназначены для agentmon и не имеют смысла для
    `docker compose up`.
    """
    argv = ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "--build"]
    return argv, docker_env(env)


def main() -> None:
    os.chdir(ROOT)

    env = dict(os.environ)
    load_env(env)

    mode = resolve_mode(env)

    if mode == "host":
        # Хост-режим: требуется .venv (создаётся через bootstrap.py)
        if not VENV.is_dir():
            print("Сначала выполните: python bootstrap.py", file=sys.stderr)
            sys.exit(1)

        port = env.get("AGENTMON_PORT", "8765")
        print(f"[run] Agent Monitor: http://127.0.0.1:{port}  (Ctrl+C для остановки)")

        cmd, env = host_plan(env, sys.argv[1:])
        if os.name == "nt":
            # на Windows нет os.exec* с нормальной обработкой Ctrl+C — используем subprocess
            import subprocess

            sys.exit(subprocess.run(cmd, env=env).returncode)
        os.execve(cmd[0], cmd, env)

    else:
        # Docker-режим: .venv не нужен, compose сам поднимает контейнер
        import subprocess

        port = env.get("AGENTMON_PORT", "8765")
        print(f"[run] Agent Monitor (Docker): http://127.0.0.1:{port}  (Ctrl+C для остановки)")

        argv, denv = docker_plan(env, sys.argv[1:])

        # Идемпотентная подготовка: создать сеть ai1c-net (если не существует).
        # Ненулевой код (сеть уже есть) — не фатален, подавляем.
        for prep in docker_prep_cmds():
            subprocess.run(prep, env=denv)

        rc = subprocess.run(argv, env=denv).returncode
        sys.exit(rc)


if __name__ == "__main__":
    main()
