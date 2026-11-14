"""Подготовка benchmark-окружения: test.env → готовый проект AgentMon.

Секреты (test.env, .1c-devbase.json) не попадают в git. Модуль не читает
agentmon.config на уровне импорта: DSN и путь реестра передаёт CLI после
загрузки .ai1c.env.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .project_checks import infer_db_kind

REQUIRED_KEYS = (
    "BENCH_PROJECT_NAME", "BENCH_PROJECT_DIR", "BENCH_DEVELOPER_ID",
    "BENCH_DEVELOPER_EMAIL", "BENCH_PLATFORM_PATH", "BENCH_DB_CONNECTION",
    "BENCH_DB_USER", "BENCH_DB_PASSWORD", "MCP_BSL_LS_URL",
    "MCP_1C_PLATFORM_URL", "MCP_CODE_INDEX_PORT",
)
OPTIONAL_KEYS = (
    "MCP_1C_MD_URL", "BENCH_DT_PATH", "MCP_CODE_INDEX_HOST",
    "CODE_INDEX_WAIT_MINUTES",
)
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class SetupError(RuntimeError):
    """Ошибка подготовки benchmark-окружения (сообщение — для пользователя)."""


@dataclass(frozen=True)
class BenchConfig:
    project_name: str
    project_dir: str
    developer_id: str
    developer_email: str
    platform_path: str          # бинарник 1cv8
    platform_version: str
    db_kind: str                # "server" | "file"
    db_connection: str
    db_user: str
    db_password: str
    bsl_ls_url: str
    platform_url: str
    code_index_port: int
    code_index_host: str
    code_index_wait_minutes: int
    one_c_md_url: str | None
    dt_path: str | None


def parse_env_file(path: Path) -> dict[str, str]:
    """Прочитать KEY=value; комментарии и пустые строки игнорируются."""
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise SetupError(f"{path}: строка не в формате KEY=value: {raw!r}")
        data[key.strip()] = value.strip()
    return data


def _resolve_platform(raw: Path) -> Path:
    """Каталог платформы → бинарник 1cv8; сам файл возвращается как есть."""
    if raw.is_file():
        return raw
    for rel in ("1cv8", "bin/1cv8", "1cv8.exe", "bin/1cv8.exe"):
        candidate = raw / rel
        if candidate.is_file():
            return candidate
    raise SetupError(
        f"не найден бинарник 1cv8: {raw} "
        "(укажите каталог платформы или сам файл)")


def load_config(env_path: Path, *, repo_root: Path,
                warn: Callable[[str], None] = print) -> BenchConfig:
    """Разобрать test.env и проверить значения, не трогая БД и файловую систему проекта."""
    if not env_path.is_file():
        raise SetupError(f"не найден файл конфигурации: {env_path}")
    data = parse_env_file(env_path)

    missing = [key for key in REQUIRED_KEYS if key not in data]
    empty = [key for key in REQUIRED_KEYS
             if key != "BENCH_DB_PASSWORD" and not data.get(key, "").strip()]
    if missing or empty:
        raise SetupError(
            "не заданы обязательные ключи: " + ", ".join(missing + empty))

    unknown = sorted(set(data) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        warn(f"⚠ неизвестные ключи test.env игнорируются: {', '.join(unknown)}")

    for key in ("MCP_BSL_LS_URL", "MCP_1C_PLATFORM_URL", "MCP_1C_MD_URL"):
        value = data.get(key, "")
        if value and not _URL_RE.match(value):
            raise SetupError(f"{key} должен начинаться с http:// или https://")

    try:
        port = int(data["MCP_CODE_INDEX_PORT"])
    except ValueError:
        raise SetupError("MCP_CODE_INDEX_PORT должен быть целым числом") from None
    if not 1 <= port <= 65535:
        raise SetupError("MCP_CODE_INDEX_PORT должен быть в диапазоне 1..65535")

    try:
        wait_minutes = int(data.get("CODE_INDEX_WAIT_MINUTES") or "360")
    except ValueError:
        raise SetupError("CODE_INDEX_WAIT_MINUTES должен быть целым числом") from None
    if wait_minutes < 1:
        raise SetupError("CODE_INDEX_WAIT_MINUTES должен быть положительным")

    project_dir = Path(os.path.expanduser(data["BENCH_PROJECT_DIR"].strip()))
    if not project_dir.is_absolute():
        raise SetupError("BENCH_PROJECT_DIR должен быть абсолютным путём")

    platform_raw = Path(os.path.expanduser(data["BENCH_PLATFORM_PATH"].strip()))
    platform = _resolve_platform(platform_raw)
    version = _VERSION_RE.search(str(platform))
    if not version:
        raise SetupError(
            f"не удалось определить версию платформы из пути: {platform}")

    dt_path = None
    dt_raw = (data.get("BENCH_DT_PATH") or "").strip()
    if dt_raw:
        dt = Path(os.path.expanduser(dt_raw))
        if not dt.is_absolute():
            dt = repo_root / dt
        dt_path = str(dt.resolve())

    db_connection = data["BENCH_DB_CONNECTION"].strip()
    return BenchConfig(
        project_name=data["BENCH_PROJECT_NAME"].strip(),
        project_dir=str(project_dir.resolve()),
        developer_id=data["BENCH_DEVELOPER_ID"].strip(),
        developer_email=data["BENCH_DEVELOPER_EMAIL"].strip(),
        platform_path=str(platform),
        platform_version=version.group(1),
        db_kind=infer_db_kind(db_connection),
        db_connection=db_connection,
        db_user=data["BENCH_DB_USER"].strip(),
        db_password=data.get("BENCH_DB_PASSWORD", ""),
        bsl_ls_url=data["MCP_BSL_LS_URL"].strip(),
        platform_url=data["MCP_1C_PLATFORM_URL"].strip(),
        code_index_port=port,
        code_index_host=(data.get("MCP_CODE_INDEX_HOST") or "localhost").strip(),
        code_index_wait_minutes=wait_minutes,
        one_c_md_url=(data.get("MCP_1C_MD_URL") or "").strip() or None,
        dt_path=dt_path,
    )
