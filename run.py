#!/usr/bin/env python3
"""Запуск Web UI Agent Monitor (кроссплатформенно). Одна команда: python run.py

Требует предварительного  python bootstrap.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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


def main() -> None:
    os.chdir(ROOT)
    if not VENV.is_dir():
        print("Сначала выполните: python bootstrap.py", file=sys.stderr)
        sys.exit(1)

    env = dict(os.environ)
    load_env(env)

    port = env.get("AGENTMON_PORT", "8765")
    print(f"[run] Agent Monitor: http://127.0.0.1:{port}  (Ctrl+C для остановки)")

    cmd = [str(venv_python()), "-m", "agentmon", *sys.argv[1:]]
    if os.name == "nt":
        # на Windows нет os.exec* с нормальной обработкой Ctrl+C — используем subprocess
        import subprocess

        sys.exit(subprocess.run(cmd, env=env).returncode)
    os.execve(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
