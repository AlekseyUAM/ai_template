#!/usr/bin/env python3
"""Запуск Web UI Agent Monitor (кроссплатформенно). Одна команда: python run.py

Требует предварительного  python bootstrap.py.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

try:
    import pg_portable as _pg_portable  # noqa: F401 — используется в ensure_host_pg
except ImportError:
    _pg_portable = None  # type: ignore[assignment]
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".ai1c.env"


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


def host_plan(env: dict, extra_args: list) -> tuple:
    """Вернуть (argv, env) для запуска агентмона.

    Поведение идентично оригинальному run.py — замена os.execve/subprocess.run.
    """
    argv = [str(venv_python()), "-m", "agentmon", *extra_args]
    return argv, env


def _with_port(dsn: str, port: int) -> str:
    """Заменить порт в DSN PostgreSQL, сохранив пользователя/пароль/базу."""
    return re.sub(r"^(postgres(?:ql)?://[^/]*?):\d+/",
                  rf"\g<1>:{port}/", dsn, count=1)


def ensure_host_pg(env: dict, *, run=subprocess.run) -> None:
    """Поднять портативную PostgreSQL при запуске монитора (если нужно).

    Если сервер уже запущен — сверяет фактический порт (postmaster.pid) с DSN
    и правит DSN. Если старт не удался — переводит DSN на SQLite, чтобы монитор
    не подключился к чужому процессу на старом порту.
    """
    if _pg_portable is None:
        return

    pg_mode = (env.get("AI1C_PG_MODE") or "host").strip().lower()
    if pg_mode != "host":
        return

    bin_dir, datadir, logfile = _pg_portable.paths(ROOT)

    if not datadir.is_dir():
        return

    if _pg_portable.status(bin_dir, datadir, run=run):
        actual = _pg_portable.running_port(datadir)
        dsn = env.get("AGENTMON_DSN") or ""
        if actual is not None and dsn.startswith("postgres"):
            env["AGENTMON_DSN"] = _with_port(dsn, actual)
        return

    port = _pg_portable.read_port(datadir)
    if port is None or not _pg_portable.port_available(port):
        port = _pg_portable.free_port()

    try:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        _pg_portable.start(bin_dir, datadir, port, logfile, run=run)
    except Exception as exc:  # noqa: BLE001
        print(f"[run] WARNING: не удалось запустить портативную PostgreSQL: {exc}. "
              f"Монитор стартует на SQLite.", file=sys.stderr)
        env["AGENTMON_DSN"] = str(ROOT / "app" / "store.db")
        return

    dsn = env.get("AGENTMON_DSN") or ""
    if dsn.startswith("postgres"):
        env["AGENTMON_DSN"] = _with_port(dsn, port)


def main() -> None:
    os.chdir(ROOT)

    env = dict(os.environ)
    load_env(env)

    if not VENV.is_dir():
        print("Сначала выполните: python bootstrap.py", file=sys.stderr)
        sys.exit(1)

    ensure_host_pg(env)

    port = env.get("AGENTMON_PORT", "8765")
    print(f"[run] Agent Monitor: http://127.0.0.1:{port}  (Ctrl+C для остановки)")

    cmd, env = host_plan(env, sys.argv[1:])
    if os.name == "nt":
        # на Windows нет os.exec* с нормальной обработкой Ctrl+C — используем subprocess
        sys.exit(subprocess.run(cmd, env=env).returncode)
    os.execve(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
