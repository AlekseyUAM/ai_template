#!/usr/bin/env python3
"""Единая установка и подготовка окружения Agent Monitor (кроссплатформенно).

Одна команда:  python bootstrap.py
  - создаёт виртуальное окружение .venv
  - ставит приложение (app, editable) и зависимости
  - поднимает PostgreSQL в Docker (если докер доступен), иначе использует SQLite
  - пишет конфиг .ai1c.env (AGENTMON_DSN) для run.py
  - проверяет наличие нужных инструментов

Запускается системным python3 — не зависит от пакетов приложения.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
ENV_FILE = ROOT / ".ai1c.env"
COMPOSE_FILE = ROOT / "deploy" / "postgres" / "docker-compose.yml"


# --- вывод -----------------------------------------------------------------
def _supports_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # включаем ENABLE_VIRTUAL_TERMINAL_PROCESSING для stdout
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True


_COLOR = _supports_color()


def _emit(color: str, msg: str) -> None:
    if _COLOR:
        print(f"\033[1;{color}m[setup]\033[0m {msg}")
    else:
        print(f"[setup] {msg}")


def say(msg: str) -> None:
    _emit("36", msg)


def warn(msg: str) -> None:
    _emit("33", msg)


def die(msg: str) -> None:
    _emit("31", msg)
    sys.exit(1)


# --- пути venv --------------------------------------------------------------
def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


# --- шаги -------------------------------------------------------------------
def ensure_venv() -> None:
    if VENV.is_dir():
        return
    say("создаю виртуальное окружение .venv")
    try:
        run([sys.executable, "-m", "venv", str(VENV)])
    except subprocess.CalledProcessError:
        die(
            "не удалось создать venv. Установите пакет: "
            "sudo apt install python3-venv (или python3-full)"
        )


def install_app() -> None:
    py = str(venv_python())
    run([py, "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL)
    say("устанавливаю приложение (app, editable) и зависимости")
    run([py, "-m", "pip", "install", "-e", str(ROOT / "app")])


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def free_port(start: int = 5432, end: int = 5460) -> int:
    for port in range(start, end):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def compose(args: list[str], env: dict[str, str], **kwargs) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(cmd, env=env, **kwargs)


def pg_container_port() -> int | None:
    """Опубликованный host-порт запущенного контейнера ai1c-postgres, иначе None."""
    r = subprocess.run(
        ["docker", "inspect", "-f",
         '{{if .State.Running}}'
         '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}{{end}}',
         "ai1c-postgres"],
        capture_output=True, text=True,
    )
    out = r.stdout.strip()
    return int(out) if r.returncode == 0 and out.isdigit() else None


def setup_database() -> str:
    if not docker_available():
        warn("Docker недоступен — использую локальный SQLite (без Postgres)")
        return str(ROOT / "app" / "agentmon.db")

    # Уже запущен и здоров — переиспользуем как есть, без рестарта и смены порта.
    port = pg_container_port()
    if port is not None:
        say(f"PostgreSQL уже запущен (ai1c-postgres, порт {port}) — переиспользую")
    else:
        # Контейнера нет/поднялся частично: убрать остатки (volume с данными
        # сохраняется) и поднять заново. free_port() после down → порт стабилен.
        compose(["down", "--remove-orphans"], env={**os.environ},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = free_port()
        say(f"поднимаю PostgreSQL в Docker (deploy/postgres) на порту {port}")
        compose(["up", "-d"], env={**os.environ, "AI1C_PG_PORT": str(port)}, check=True)

    say("устанавливаю драйвер psycopg")
    run([str(venv_python()), "-m", "pip", "install", "psycopg[binary]"],
        stdout=subprocess.DEVNULL)

    say("жду готовности PostgreSQL…")
    ready = False
    for _ in range(30):
        rc = subprocess.run(
            ["docker", "exec", "ai1c-postgres", "pg_isready", "-U", "ai1c"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        if rc == 0:
            ready = True
            break
        time.sleep(1)
    if not ready:
        warn("PostgreSQL не ответил за 30с — проверьте контейнер ai1c-postgres")
    return f"postgresql://ai1c:ai1c@127.0.0.1:{port}/ai1c"


def write_env(dsn: str) -> None:
    ENV_FILE.write_text(
        "# Сгенерировано bootstrap.py — используется run.py\n"
        f"AGENTMON_DSN={dsn}\n"
        f"AGENTMON_DB={ROOT / 'app' / 'agentmon.db'}\n",
        encoding="utf-8",
    )
    say(f"конфиг записан: .ai1c.env (AGENTMON_DSN={dsn})")


def check_tools() -> None:
    for tool in ("git", "docker", "claude"):
        if shutil.which(tool):
            say(f"найдено: {tool}")
        else:
            warn(f"не найдено (не блокирует работу UI): {tool}")


def main() -> None:
    os.chdir(ROOT)
    ensure_venv()
    install_app()
    dsn = setup_database()
    write_env(dsn)
    check_tools()
    say("Готово. Поднять Web UI: python run.py")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        die(f"команда завершилась с ошибкой: {' '.join(map(str, exc.cmd))}")
