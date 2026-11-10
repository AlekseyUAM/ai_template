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

# Ленивый импорт pg_portable: модуль лежит рядом с bootstrap.py в корне репо.
# Устанавливается здесь (не внутри функции), чтобы тесты могли подменить его
# через monkeypatch.setattr(bootstrap, "pg_portable", stub).
try:
    import pg_portable  # type: ignore[import]  # noqa: E402
except ImportError:
    pg_portable = None  # type: ignore[assignment]


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


def setup_database() -> tuple[str, str]:
    """Инициализирует базу данных и возвращает (dsn, pg_mode).

    Читает AI1C_PG_MODE из окружения (дефолт «host»):
      - «host»   → портативная PostgreSQL через pg_portable.provision(ROOT)
      - «docker» → поднять контейнер ai1c-postgres (прежнее поведение)
    При любой ошибке PG → SQLite-фолбэк; psycopg[binary] ставится только для PG.
    """
    # Хранилище (store) держим в отдельном файле: реестр использует AGENTMON_DB
    # (app/agentmon.db), и совмещать их нельзя — у таблиц projects разные схемы.
    _SQLITE_PATH = str(ROOT / "app" / "store.db")
    raw_mode = os.environ.get("AI1C_PG_MODE", "host")
    pg_mode = raw_mode.strip().lower()
    if pg_mode not in ("host", "docker"):
        warn(f"Неизвестное значение AI1C_PG_MODE={raw_mode!r} — буду использовать «host»")
        pg_mode = "host"

    if pg_mode == "docker":
        if not docker_available():
            warn("Docker недоступен — использую локальный SQLite (без Postgres)")
            return _SQLITE_PATH, pg_mode

        # Уже запущен и здоров — переиспользуем как есть, без рестарта и смены порта.
        port = pg_container_port()
        if port is not None:
            say(f"PostgreSQL уже запущен (ai1c-postgres, порт {port}) — переиспользую")
        else:
            # Контейнера нет/поднялся частично: убрать остатки (volume с данными
            # сохраняется) и поднять заново. free_port() после down → порт стабилен.
            try:
                compose(["down", "--remove-orphans"], env={**os.environ},
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass          # остатков может не быть — это не ошибка
            port = free_port()
            say(f"поднимаю PostgreSQL в Docker (deploy/postgres) на порту {port}")
            try:
                compose(["up", "-d"],
                        env={**os.environ, "AI1C_PG_PORT": str(port)}, check=True)
            except subprocess.CalledProcessError as exc:
                warn(f"docker compose up не удался ({exc}) — использую локальный SQLite")
                return _SQLITE_PATH, pg_mode

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
            warn("PostgreSQL не ответил за 30с — использую локальный SQLite")
            return _SQLITE_PATH, pg_mode
        return f"postgresql://ai1c:ai1c@127.0.0.1:{port}/ai1c", pg_mode

    # pg_mode == "host": портативная PostgreSQL
    # Используем модульный атрибут pg_portable (импортирован в начале файла),
    # чтобы тесты могли подменить его через monkeypatch.setattr(bootstrap, "pg_portable", stub).
    try:
        _ppmod = pg_portable
        if _ppmod is None:
            raise ImportError("pg_portable не найден")
        say("запускаю портативную PostgreSQL (pg_portable)…")
        dsn = _ppmod.provision(ROOT)
        say(f"портативная PostgreSQL готова: {dsn}")
        say("устанавливаю драйвер psycopg")
        run([str(venv_python()), "-m", "pip", "install", "psycopg[binary]"],
            stdout=subprocess.DEVNULL)
        return dsn, pg_mode
    except Exception as exc:
        warn(f"портативная PostgreSQL недоступна ({exc}) — использую локальный SQLite")
        return _SQLITE_PATH, pg_mode


def env_file_contents(
    dsn: str,
    db: str,
    *,
    pg_mode: str = "host",
) -> str:
    """Возвращает текст файла .ai1c.env — чистая функция, без I/O.

    dsn     — строка подключения к БД (postgresql://... или путь sqlite)
    db      — путь к файлу agentmon.db (для SQLite fallback)
    pg_mode — режим БД: «host» (портативная PG на хосте) или «docker» (контейнер ai1c-postgres)
    """
    return (
        "# Сгенерировано bootstrap.py — используется run.py\n"
        f"AGENTMON_DSN={dsn}\n"
        f"AGENTMON_DB={db}\n"
        "# AI1C_PG_MODE: host (портативная PG на хосте) | docker (контейнер ai1c-postgres)\n"
        f"AI1C_PG_MODE={pg_mode}\n"
    )


MANAGED_ENV_KEYS = ("AGENTMON_DSN", "AGENTMON_DB", "AI1C_PG_MODE")


def merge_env_text(existing: str, managed: dict[str, str]) -> str:
    """Обновить управляемые ключи, сохранив остальные строки и комментарии.

    .ai1c.env документирован как файл, куда пользователь добавляет
    AGENTMON_TG_TOKEN/AGENTMON_CLAUDE_CMD. Повторный bootstrap не должен их
    стирать.
    """
    out: list[str] = []
    seen: set[str] = set()
    for line in existing.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in managed:
                out.append(f"{key}={managed[key]}")
                seen.add(key)
                continue
        out.append(line)
    missing = [k for k in MANAGED_ENV_KEYS if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        if not any(line.startswith("# Управляемые") for line in out):
            out.append("# Управляемые ключи обновляются bootstrap.py")
        out.extend(f"{k}={managed[k]}" for k in missing)
    return "\n".join(out).rstrip("\n") + "\n"


def write_env(dsn: str, pg_mode: str = "host") -> None:
    db = str(ROOT / "app" / "agentmon.db")
    managed = {"AGENTMON_DSN": dsn, "AGENTMON_DB": db,
               "AI1C_PG_MODE": pg_mode}
    if ENV_FILE.exists():
        try:
            existing = ENV_FILE.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        text = merge_env_text(existing, managed) if existing else \
            env_file_contents(dsn, db, pg_mode=pg_mode)
    else:
        text = env_file_contents(dsn, db, pg_mode=pg_mode)
    ENV_FILE.write_text(text, encoding="utf-8")
    say(f"конфиг записан: .ai1c.env (AGENTMON_DSN={dsn}, AI1C_PG_MODE={pg_mode})")


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
    dsn, pg_mode = setup_database()
    write_env(dsn, pg_mode)
    check_tools()
    say("Готово. Поднять Web UI: python run.py")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        die(f"команда завершилась с ошибкой: {' '.join(map(str, exc.cmd))}")
