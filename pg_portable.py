"""Портативная PostgreSQL на хосте — скачивание, initdb, pg_ctl, роль/БД.

Весь внешний I/O (download, extract, subprocess) инъектируем: реальные
умолчания используются только при «живом» запуске; тесты передают фейки и
никогда не обращаются к сети и не запускают настоящий PostgreSQL.

Типичное использование::

    from pg_portable import provision
    dsn = provision(ROOT)   # orchestrate: download → initdb → start → role/db

Ожидаемые каталоги (внутри <root>):
    .ai1c/pg/<PG_VERSION>/pgsql/bin/   — бинарники PostgreSQL
    .ai1c/pgdata/                       — кластер данных
    .ai1c/pg.log                        — лог pg_ctl
"""
from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

#: Версия EDB-сборки (менять здесь, если выходит новый релиз).
PG_VERSION: str = "16.4-1"

#: Базовый URL EDB portable-binaries.
EDB_BASE_URL: str = "https://get.enterprisedb.com/postgresql"

#: Шаблоны имён архивов по платформе (подставляется в binaries_url).
_ARCHIVE_TEMPLATES: dict[str, str] = {
    "windows": "postgresql-{version}-windows-x64-binaries.zip",
    "linux":   "postgresql-{version}-linux-x64-binaries.zip",
    "osx":     "postgresql-{version}-osx-binaries.zip",
}

#: Относительный путь к каталогу бинарников внутри root.
PG_DIR: str = ".ai1c/pg"

#: Относительный путь к каталогу данных кластера.
PGDATA: str = ".ai1c/pgdata"

#: Суперпользователь PostgreSQL (для initdb и psql).
SUPERUSER: str = "postgres"


# ---------------------------------------------------------------------------
# Утилиты: платформа
# ---------------------------------------------------------------------------

def binaries_url(system: str, arch: str) -> str:
    """Строит URL портативных бинарников EDB для заданной платформы.

    system — значение platform.system() («Windows», «Linux», «Darwin»).
    arch   — значение platform.machine() («AMD64», «x86_64», «arm64», …).

    Поддерживаются windows-x64, linux-x64 и osx (arm включён в osx-binaries).
    Поднимает RuntimeError для неизвестных платформ.
    """
    sys_key = system.lower()
    if sys_key == "windows":
        os_tag = "windows"
    elif sys_key == "linux":
        os_tag = "linux"
    elif sys_key == "darwin":
        os_tag = "osx"
    else:
        raise RuntimeError(
            f"Неподдерживаемая платформа: system={system!r}. "
            "Поддерживаются: Windows, Linux, Darwin."
        )

    # Проверяем архитектуру только для windows/linux (osx — один архив).
    arch_lower = arch.lower()
    if os_tag != "osx" and arch_lower not in ("amd64", "x86_64"):
        raise RuntimeError(
            f"Неподдерживаемая архитектура: arch={arch!r} для системы {system!r}. "
            "Поддерживается только x64 (amd64/x86_64)."
        )

    template = _ARCHIVE_TEMPLATES[os_tag]
    filename = template.format(version=PG_VERSION)
    return f"{EDB_BASE_URL}/{filename}"


def bin_exe(name: str) -> str:
    """Возвращает имя исполняемого файла: добавляет .exe на Windows."""
    if sys.platform == "win32":
        return name + ".exe"
    return name


# ---------------------------------------------------------------------------
# Загрузка и распаковка бинарников
# ---------------------------------------------------------------------------

def _default_download(url: str, dest: str) -> None:
    """Реальная загрузка через urllib (используется только в «живом» режиме)."""
    import urllib.request  # pylint: disable=import-outside-toplevel
    urllib.request.urlretrieve(url, dest)


def _default_extract(zip_path: str, dest: str) -> None:
    """Реальная распаковка через zipfile (используется только в «живом» режиме)."""
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def ensure_binaries(
    root,
    *,
    system: str | None = None,
    arch: str | None = None,
    download: Callable[[str, str], None] = _default_download,
    extract: Callable[[str, str], None] = _default_extract,
) -> str:
    """Гарантирует наличие портативных бинарников PostgreSQL.

    Целевой каталог: <root>/.ai1c/pg/<PG_VERSION>/pgsql/bin/.
    Если bin/initdb[.exe] уже присутствует — немедленно возвращает путь к bin
    (идемпотентно). Иначе скачивает zip через download() и распаковывает через
    extract(); EDB-архив содержит каталог pgsql/ верхнего уровня.

    На Posix выставляет +x для всех файлов в bin.
    Возвращает путь к каталогу bin (строку).
    """
    root = Path(root)
    system = system or platform.system()
    arch = arch or platform.machine()

    dest_dir = root / PG_DIR / PG_VERSION
    bin_dir = dest_dir / "pgsql" / "bin"
    initdb_exe = bin_dir / bin_exe("initdb")

    if initdb_exe.exists():
        return str(bin_dir)

    # Скачать
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"postgresql-{PG_VERSION}-binaries.zip"
    url = binaries_url(system, arch)
    download(url, str(zip_path))

    # Распаковать
    extract(str(zip_path), str(dest_dir))

    # Chmod +x на Posix
    if sys.platform != "win32" and bin_dir.is_dir():
        for entry in bin_dir.iterdir():
            if entry.is_file():
                entry.chmod(entry.stat().st_mode | 0o111)

    return str(bin_dir)


# ---------------------------------------------------------------------------
# initdb / start / status / stop
# ---------------------------------------------------------------------------

def initdb(
    bin_dir,
    datadir,
    *,
    run: Callable = subprocess.run,
) -> None:
    """Инициализирует кластер PostgreSQL через initdb.

    Пропускает выполнение, если файл <datadir>/PG_VERSION уже существует
    (признак уже инициализированного кластера).
    Поднимает subprocess.CalledProcessError при ненулевом коде возврата.
    """
    datadir = Path(datadir)
    if (datadir / "PG_VERSION").exists():
        return

    datadir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(Path(bin_dir) / bin_exe("initdb")),
        "-D", str(datadir),
        "-U", SUPERUSER,
        "-A", "trust",
        "--encoding=UTF8",
    ]
    result = run(cmd, capture_output=True)
    rc = result.returncode if hasattr(result, "returncode") else 0
    if rc != 0:
        stderr = getattr(result, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise subprocess.CalledProcessError(rc, cmd, stderr=stderr)


def start(
    bin_dir,
    datadir,
    port: int,
    logfile,
    *,
    run: Callable = subprocess.run,
) -> None:
    """Запускает сервер PostgreSQL через pg_ctl start.

    Слушает только на 127.0.0.1; использует -w (ждёт готовности).
    Поднимает subprocess.CalledProcessError при ненулевом коде возврата.
    """
    cmd = [
        str(Path(bin_dir) / bin_exe("pg_ctl")),
        "-D", str(datadir),
        "-o", f"-p {port} -h 127.0.0.1",
        "-l", str(logfile),
        "-w",
        "start",
    ]
    result = run(cmd, capture_output=True)
    rc = result.returncode if hasattr(result, "returncode") else 0
    if rc != 0:
        stderr = getattr(result, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise subprocess.CalledProcessError(rc, cmd, stderr=stderr)


def status(
    bin_dir,
    datadir,
    *,
    run: Callable = subprocess.run,
) -> bool:
    """Возвращает True, если сервер PostgreSQL запущен (pg_ctl status → rc 0)."""
    cmd = [
        str(Path(bin_dir) / bin_exe("pg_ctl")),
        "-D", str(datadir),
        "status",
    ]
    result = run(cmd, capture_output=True)
    rc = result.returncode if hasattr(result, "returncode") else 0
    return rc == 0


def stop(
    bin_dir,
    datadir,
    *,
    run: Callable = subprocess.run,
) -> None:
    """Останавливает сервер PostgreSQL через pg_ctl stop.

    Игнорирует ошибку «уже остановлен» (rc != 0 при отсутствии сервера
    допустимо — не поднимает исключение).
    """
    cmd = [
        str(Path(bin_dir) / bin_exe("pg_ctl")),
        "-D", str(datadir),
        "-w",
        "stop",
    ]
    run(cmd, capture_output=True)


# ---------------------------------------------------------------------------
# Роль и база данных
# ---------------------------------------------------------------------------

def ensure_role_db(
    bin_dir,
    port: int,
    *,
    user: str = "ai1c",
    password: str = "ai1c",
    db: str = "ai1c",
    run: Callable = subprocess.run,
) -> None:
    """Идемпотентно создаёт роль и базу данных PostgreSQL.

    Шаг 1 — создать роль (если не существует) и выставить пароль через psql:
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='<user>') THEN
            CREATE ROLE <user> LOGIN PASSWORD '<password>';
          END IF;
        END $$;
        ALTER ROLE <user> WITH PASSWORD '<password>';

    Шаг 2 — создать БД (если не существует). CREATE DATABASE нельзя выполнять
    внутри транзакции/DO-блока, поэтому сначала проверяем pg_database, и только
    при отсутствии запускаем отдельную psql-команду CREATE DATABASE.

    Поднимает subprocess.CalledProcessError при ненулевом коде возврата.
    """
    # Защитный барьер на границе доверия: значения обычно константа ai1c,
    # но на случай внешнего вызова — блокируем SQL-метасимволы.
    _IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for _val in (user, db):
        if not _IDENT_RE.match(_val):
            raise ValueError(f"недопустимый идентификатор: {_val!r}")
    # Одинарная кавычка в пароле экранируется удвоением для SQL-литерала.
    safe_password = password.replace("'", "''")

    psql = str(Path(bin_dir) / bin_exe("psql"))
    base_args = [
        psql,
        "-h", "127.0.0.1",
        "-p", str(port),
        "-U", SUPERUSER,
        "-d", "postgres",
    ]

    # Шаг 1: роль
    role_sql = (
        "DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{user}') THEN "
        f"CREATE ROLE {user} LOGIN PASSWORD '{safe_password}'; "
        "END IF; "
        "END $$; "
        f"ALTER ROLE {user} WITH PASSWORD '{safe_password}';"
    )
    result = run(base_args + ["-c", role_sql], capture_output=True)
    rc = result.returncode if hasattr(result, "returncode") else 0
    if rc != 0:
        stderr = getattr(result, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise subprocess.CalledProcessError(rc, base_args, stderr=stderr)

    # Шаг 2: база данных — сначала проверяем наличие
    check_sql = f"SELECT 1 FROM pg_database WHERE datname='{db}';"
    result_check = run(base_args + ["-t", "-c", check_sql], capture_output=True)
    check_rc = result_check.returncode if hasattr(result_check, "returncode") else 0
    stdout = getattr(result_check, "stdout", b"")
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors="replace")

    if check_rc == 0 and "1" in stdout:
        # БД уже существует
        return

    # Создаём БД
    create_sql = f"CREATE DATABASE {db} OWNER {user};"
    result_create = run(base_args + ["-c", create_sql], capture_output=True)
    create_rc = result_create.returncode if hasattr(result_create, "returncode") else 0
    if create_rc != 0:
        stderr = getattr(result_create, "stderr", b"")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        raise subprocess.CalledProcessError(create_rc, base_args, stderr=stderr)


# ---------------------------------------------------------------------------
# DSN
# ---------------------------------------------------------------------------

def dsn(
    port: int,
    *,
    user: str = "ai1c",
    password: str = "ai1c",
    db: str = "ai1c",
) -> str:
    """Строит строку подключения PostgreSQL.

    Формат: postgresql://<user>:<password>@127.0.0.1:<port>/<db>
    """
    return f"postgresql://{user}:{password}@127.0.0.1:{port}/{db}"


# ---------------------------------------------------------------------------
# Свободный порт
# ---------------------------------------------------------------------------

def free_port(start: int = 5432, end: int = 5460) -> int:
    """Находит свободный TCP-порт в диапазоне [start, end) через socket-bind.

    Аналог bootstrap.free_port; возвращает start при исчерпании диапазона.
    """
    for port in range(start, end):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


# ---------------------------------------------------------------------------
# Главная оркестрация
# ---------------------------------------------------------------------------

def provision(
    root,
    *,
    port: int | None = None,
    system: str | None = None,
    arch: str | None = None,
    download: Callable[[str, str], None] = _default_download,
    extract: Callable[[str, str], None] = _default_extract,
    run: Callable = subprocess.run,
    free_port_fn: Callable[[], int] = free_port,
) -> str:
    """Оркестрация: скачать → initdb → запустить → создать роль/БД → вернуть DSN.

    Идемпотентна: повторный вызов переиспользует существующие бинарники,
    кластер данных, порт и запущенный сервер.

    Порт выбирается по приоритету:
      1. Явный параметр port.
      2. Сохранённый файл <datadir>/ai1c.port.
      3. Свободный порт (free_port()).
    Выбранный порт сохраняется в <datadir>/ai1c.port для следующих запусков.
    Возвращает DSN: postgresql://ai1c:ai1c@127.0.0.1:<port>/ai1c.
    """
    root = Path(root)

    # 1. Бинарники
    bin_dir = ensure_binaries(
        root,
        system=system,
        arch=arch,
        download=download,
        extract=extract,
    )

    # 2. Каталог данных
    datadir = root / PGDATA

    # 3. initdb (пропустит, если datadir/PG_VERSION уже есть)
    initdb(bin_dir, datadir, run=run)

    # 4. Разрешить порт
    port_file = datadir / "ai1c.port"
    if port is not None:
        chosen_port = port
    elif port_file.exists():
        try:
            chosen_port = int(port_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            chosen_port = free_port_fn()
    else:
        chosen_port = free_port_fn()

    # Сохранить выбранный порт
    port_file.write_text(str(chosen_port), encoding="utf-8")

    # 5. Запустить (если ещё не запущен)
    if not status(bin_dir, datadir, run=run):
        logfile = root / ".ai1c" / "pg.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        start(bin_dir, datadir, chosen_port, logfile, run=run)

    # 6. Создать роль и БД
    ensure_role_db(bin_dir, chosen_port, run=run)

    # 7. Вернуть DSN
    return dsn(chosen_port)
