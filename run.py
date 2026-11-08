#!/usr/bin/env python3
"""Запуск Web UI Agent Monitor (кроссплатформенно). Одна команда: python run.py

Требует предварительного  python bootstrap.py.
"""
from __future__ import annotations

import os
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


def ensure_host_pg(env: dict, *, run=subprocess.run) -> None:
    """Поднять портативную PostgreSQL при запуске монитора (если нужно).

    Условия для запуска:
    - AI1C_PG_MODE == "host" (или не задан — дефолт host).
    - Каталог данных <ROOT>/.ai1c/pgdata существует (portable PG была provisioned).
    - pg_portable доступен (мягкий import — при отсутствии модуля no-op).

    Если PostgreSQL не запущена — вызывает pg_portable.start().
    Ошибки start логируются в stderr, но НЕ прерывают запуск монитора.
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
        return  # уже запущена

    port = _pg_portable.read_port(datadir)
    if port is None:
        # Файл порта потерян/повреждён (при нормальном provision не случается);
        # берём дефолт, но предупреждаем — DSN в .ai1c.env может указывать на другой порт.
        port = 5432
        print("[run] WARNING: .ai1c/pgdata/ai1c.port не найден — старт PG на 5432",
              file=sys.stderr)

    try:
        logfile.parent.mkdir(parents=True, exist_ok=True)
        _pg_portable.start(bin_dir, datadir, port, logfile, run=run)
    except Exception as exc:  # noqa: BLE001
        print(f"[run] WARNING: не удалось запустить портативную PostgreSQL: {exc}", file=sys.stderr)


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
