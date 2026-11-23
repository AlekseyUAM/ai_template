"""Подготовка benchmark-окружения: test.env → готовый проект AgentMon.

Секреты (test.env, .1c-devbase.json) не попадают в git. Модуль не читает
agentmon.config на уровне импорта: DSN и путь реестра передаёт CLI после
загрузки .ai1c.env.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..pycmd import PYTHON_CMD
from .config_schema import SCHEMA_VERSION, EnvConfig, McpSelection
from .devbase import _parse_connection, git_commit_all, git_init_project
from . import code_index_bench
from .code_index_bench import (NativeIndex, start_code_index,
                               wait_code_index_ready)
from .installer import install_environment
from .net_probe import default_http_ok, default_tcp_ok, url_host_port
from .project_checks import current_env_version, infer_db_kind, validate_name
from .timefmt import to_local_iso
from ..paths import same_path
from ..store.mcp import McpRepo
from ..store.projects import ProjectRepo
from ..store.tasks import TaskRepo

REQUIRED_KEYS = (
    "BENCH_PROJECT_NAME", "BENCH_PROJECT_DIR", "BENCH_DEVELOPER_ID",
    "BENCH_DEVELOPER_EMAIL", "BENCH_PLATFORM_PATH", "BENCH_DB_CONNECTION",
    "BENCH_DB_USER", "BENCH_DB_PASSWORD", "MCP_BSL_LS_URL",
    "MCP_1C_PLATFORM_URL", "MCP_CODE_INDEX_PORT", "CODE_INDEX_DIR",
)
OPTIONAL_KEYS = (
    "MCP_1C_MD_URL", "MCP_1C_NAPARNIC_URL", "BENCH_DT_PATH",
    "MCP_CODE_INDEX_HOST", "CODE_INDEX_WAIT_MINUTES",
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
    code_index_dir: str          # каталог нативного code-index
    one_c_md_url: str | None
    one_c_naparnic_url: str | None
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


def load_env_file(path: Path, env: dict[str, str]) -> None:
    """Прочитать KEY=value в env, перезаписывая существующие ключи (как run.py)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            env[key.strip()] = value.strip()


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
             if key != "BENCH_DB_PASSWORD"
             and key in data and not data[key].strip()]
    if missing or empty:
        raise SetupError(
            "не заданы обязательные ключи: " + ", ".join(missing + empty))

    unknown = sorted(set(data) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        warn(f"⚠ неизвестные ключи test.env игнорируются: {', '.join(unknown)}")

    for key in ("MCP_BSL_LS_URL", "MCP_1C_PLATFORM_URL", "MCP_1C_MD_URL",
                "MCP_1C_NAPARNIC_URL"):
        value = data.get(key, "")
        if value and not _URL_RE.match(value):
            raise SetupError(f"{key} должен начинаться с http:// или https://")
        if value:
            try:
                url_host_port(value)
            except ValueError:
                raise SetupError(
                    f"{key}: некорректный URL {value!r} "
                    "(проверьте порт: http://host:порт/путь)") from None

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

    code_index_raw = (data.get("CODE_INDEX_DIR") or "").strip()
    if not code_index_raw:
        raise SetupError("не задан CODE_INDEX_DIR")
    code_index_dir = Path(os.path.expanduser(code_index_raw))
    if not code_index_dir.is_absolute():
        raise SetupError("CODE_INDEX_DIR должен быть абсолютным путём")
    # Сравнение разрешённых путей: симлинк на проект или на CODE_INDEX_DIR
    # иначе прошёл бы проверку, а start_code_index затем удалил бы каталог
    # внутри проекта.
    project_real = project_dir.resolve()
    code_index_real = code_index_dir.resolve()
    if (code_index_real == project_real
            or project_real in code_index_real.parents):
        raise SetupError("CODE_INDEX_DIR не должен находиться внутри "
                         "BENCH_PROJECT_DIR")

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
        code_index_dir=str(code_index_dir.resolve()),
        one_c_md_url=(data.get("MCP_1C_MD_URL") or "").strip() or None,
        one_c_naparnic_url=(
            data.get("MCP_1C_NAPARNIC_URL") or "").strip() or None,
        dt_path=dt_path,
    )


EXTENSIONS = (
    ("app/web/assets/ЮнитТесты.cfe", "ЮнитТесты"),
    ("deps/mcp_tools_cfe/1c-mcp-tools-1.0.6.cfe", "mcp_tools"),
)


@dataclass(frozen=True)
class McpPlan:
    standard_key: str
    mcp_name: str
    kind: str
    connection_json: str
    purpose: str = ""
    url: str | None = None
    port: int | None = None
    catalog_dir: str | None = None
    project_name: str | None = None
    code_index_dir: str | None = None


def _connection_http(name: str, url: str) -> str:
    """Фрагмент справочника MCP: `"<имя>": {...}` (без внешних фигурных скобок)."""
    entry = json.dumps({"type": "http", "url": url}, ensure_ascii=False)
    return f'"{name}": {entry}'


def _connection_platform(url: str) -> str:
    """Фрагмент справочника MCP: `"1c_platform": {...}` через stdio-мост."""
    server = json.dumps(
        {
            "type": "stdio",
            "command": PYTHON_CMD,
            "args": [".claude/mcp/sse_stdio_bridge.py", url],
        },
        ensure_ascii=False,
    )
    return f"\"1c_platform\": {server}"


def check_mcp_url(url: str, *, http_ok=default_http_ok, log=print,
                  attempts: int = 6, delay: float = 5.0,
                  sleep=time.sleep) -> None:
    """Дождаться ответа 1c-md по адресу `url`.

    Сразу после restore-ib веб-публикация 1С поднимается не мгновенно:
    первый запрос может упереться в таймаут http_ok (5 с) или оборваться.
    Поэтому пробуем несколько раз, прежде чем объявить сервер недоступным.
    """
    for attempt in range(1, attempts + 1):
        if http_ok(url):
            log(f"✓ 1c-md доступен: {url}")
            return
        if attempt < attempts:
            log(f"⚠ 1c-md не ответил ({attempt}/{attempts - 1}) — повтор "
                f"через {delay:g} с")
            sleep(delay)
    raise SetupError(f"1c-md недоступен по адресу {url}")


def create_project_row(store, cfg: BenchConfig) -> int:
    return ProjectRepo(store).add(
        name=cfg.project_name,
        path=cfg.project_dir,
        identifier=cfg.developer_id,
        email=cfg.developer_email,
        platform_dir=cfg.platform_path,
        platform_version=cfg.platform_version,
        db_kind=cfg.db_kind,
        db_connection=cfg.db_connection,
        web_publication="",
        env_version=current_env_version(),
        now=time.time(),
    )


def preflight(cfg: BenchConfig, *, repo_root: Path, store, registry,
              tcp_ok=default_tcp_ok, http_ok=default_http_ok,
              allow_existing: bool = False) -> None:
    """Проверить всё, что можно проверить до создания каталога и записей БД.

    allow_existing=True пропускает проверки уже существующего проекта — режим
    пересоздания: сначала проверяются остальные условия, чтобы не удалить
    проект при ошибке в конфигурации.
    """
    ok, error = validate_name(cfg.project_name)
    if not ok:
        raise SetupError(f"недопустимое BENCH_PROJECT_NAME: {error}")

    project_dir = Path(cfg.project_dir)
    if not allow_existing:
        if project_dir.exists() and (not project_dir.is_dir()
                                     or any(project_dir.iterdir())):
            raise SetupError(f"каталог проекта не пуст или не является каталогом: "
                             f"{project_dir}")

        for row in ProjectRepo(store).list():
            if row["name"] == cfg.project_name or same_path(
                    row["path"], cfg.project_dir):
                raise SetupError(
                    "проект с таким именем или каталогом уже существует: "
                    f"{row['name']} ({row['path']})")

        for project in registry.list():
            if same_path(project.path, cfg.project_dir):
                raise SetupError(
                    f"каталог уже зарегистрирован в реестре: {project.path}")

    if cfg.dt_path:
        if not Path(cfg.dt_path).is_file():
            raise SetupError(f"не найден BENCH_DT_PATH: {cfg.dt_path}")
    else:
        cf_dir = repo_root / "benchmark" / "cf"
        if not cf_dir.is_dir():
            raise SetupError(f"не найден каталог конфигурации: {cf_dir}")
        for rel, name in EXTENSIONS:
            if not (repo_root / rel).is_file():
                raise SetupError(f"не найдено расширение {name}: {repo_root / rel}")

    for key, url in (("MCP_BSL_LS_URL", cfg.bsl_ls_url),
                     ("MCP_1C_PLATFORM_URL", cfg.platform_url)):
        if not tcp_ok(url):
            raise SetupError(f"{key}: сервер недоступен по адресу {url}")

    if cfg.one_c_naparnic_url and not http_ok(cfg.one_c_naparnic_url):
        raise SetupError(
            "MCP_1C_NAPARNIC_URL: сервер недоступен по адресу "
            f"{cfg.one_c_naparnic_url}")


_PROJECT_MARKERS = (".1c-devbase.json", ".claude", "tasks")


def _git_head_has_marker(project_dir: Path) -> bool:
    """Признак проекта остался только в git-истории?

    После прерванного удаления рабочие файлы-маркеры уже стёрты, но HEAD
    ещё хранит `.1c-devbase.json`. Нет git/репозитория — признака нет.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(project_dir), "cat-file", "-e",
             "HEAD:.1c-devbase.json"],
            capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


def _assert_deletable(project_dir: Path) -> None:
    """Не дать удалить произвольный непустой каталог вместо benchmark-проекта."""
    if project_dir.is_symlink():
        raise SetupError(
            f"каталог проекта — символическая ссылка: {project_dir}. "
            "Удалите её вручную.")
    resolved = project_dir.resolve()
    if (resolved == Path("/") or resolved == Path.home().resolve()
            or len(resolved.parts) < 3):
        raise SetupError(f"отказ удалять каталог: {resolved}")
    markers_found = any((project_dir / marker).exists()
                        for marker in _PROJECT_MARKERS)
    if not markers_found and not _git_head_has_marker(project_dir):
        raise SetupError(
            f"каталог {project_dir} не похож на benchmark-проект "
            f"(нет {', '.join(_PROJECT_MARKERS)}); удалять не буду.")


def _rmtree_force(path: Path) -> None:
    """Удалить дерево, сняв read-only с файлов.

    Git на Windows создаёт pack-файлы в `.git/objects/pack` доступными только
    для чтения, и `shutil.rmtree` падает на них с PermissionError.
    """
    for root, _dirs, files in os.walk(path):
        for name in files:
            entry = Path(root) / name
            try:
                entry.chmod(entry.stat().st_mode | stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path)


def remove_existing_project(cfg: BenchConfig, *, store, registry,
                            log=print) -> None:
    """Удалить существующий benchmark-проект: каталог, store и реестр.

    Используется режимом пересоздания setup'а. MCP-карточки не удаляются:
    они переиспользуются по точному совпадению подключения.
    """
    project_dir = Path(cfg.project_dir)
    if project_dir.exists():
        if not project_dir.is_dir():
            raise SetupError(f"путь проекта не является каталогом: {project_dir}")
        if any(project_dir.iterdir()):
            _assert_deletable(project_dir)

    removed = False
    project_repo = ProjectRepo(store)
    for row in list(project_repo.list()):
        if row["name"] == cfg.project_name or same_path(
                row["path"], cfg.project_dir):
            project_repo.delete(row["id"])
            removed = True
            log(f"✓ удалена запись проекта из store: #{row['id']} {row['name']}")

    for project in list(registry.list()):
        if same_path(project.path, cfg.project_dir):
            registry.delete(project.id)
            removed = True
            log(f"✓ удалена запись проекта из реестра: #{project.id} {project.name}")

    if project_dir.exists():
        _rmtree_force(project_dir)
        removed = True
        log(f"✓ удалён каталог проекта: {project_dir}")

    if not removed:
        log("✓ существующий проект не найден — создаю новый")


def build_mcp_plans(cfg: BenchConfig) -> list[McpPlan]:
    bsl_host, bsl_port = url_host_port(cfg.bsl_ls_url)
    plans = [
        McpPlan(
            standard_key="bsl-ls", mcp_name="bsl_ls", kind="docker",
            connection_json=_connection_http("bsl_ls", cfg.bsl_ls_url),
            purpose="Статический анализ кода на соответствие стандартам 1С",
            url=bsl_host, port=bsl_port,
        ),
        McpPlan(
            standard_key="1c-platform", mcp_name="1c_platform", kind="docker",
            connection_json=_connection_platform(cfg.platform_url),
            purpose=("Справочная информация по встроенным функциям, типам "
                     "данных, методам и свойствам платформы"),
        ),
    ]
    if cfg.one_c_md_url:
        plans.append(McpPlan(
            standard_key="1c-md-queries", mcp_name="1c-md", kind="extension",
            connection_json=_connection_http("1c-md", cfg.one_c_md_url),
            purpose=("Произвольные запросы к данным, вся информация об "
                     "актуальных метаданных конфигурации"),
        ))
    if cfg.one_c_naparnic_url:
        naparnic_host, naparnic_port = url_host_port(cfg.one_c_naparnic_url)
        plans.append(McpPlan(
            standard_key="1c-naparnic", mcp_name="1c_naparnic",
            kind="docker",
            connection_json=_connection_http("1c_naparnic",
                                             cfg.one_c_naparnic_url),
            purpose=("Объяснение логики кода, любые вопросы по информационно-"
                     "технологическому сопровождению 1С"),
            url=naparnic_host, port=naparnic_port,
        ))
    plans.append(McpPlan(
        standard_key="code-index", mcp_name="code_index", kind="local",
        connection_json=_connection_http(
            "code_index",
            f"http://{cfg.code_index_host}:{cfg.code_index_port}/mcp"),
        purpose=("Полнотекстовый поиск по функциям и классам, граф вызовов, "
                 "паспорт объекта"),
        url=cfg.code_index_host, port=cfg.code_index_port,
        catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
        project_name=cfg.project_name,
        code_index_dir=cfg.code_index_dir,
    ))
    return plans


def _connection_equal(left: str | None, right: str) -> bool:
    """Сравнить фрагменты connection_json семантически, а не по форматированию."""
    try:
        return json.loads("{" + (left or "") + "}") == json.loads("{" + right + "}")
    except (TypeError, ValueError):
        return (left or "") == right


def _unique_card_name(repo, base: str) -> str:
    name, index = base, 2
    while repo.by_name(name) is not None:
        name = f"{base} {index}"
        index += 1
    return name


def resolve_mcp_cards(mcp_repo, plans: list[McpPlan], *, project_id: int,
                      project_name: str, log=print,
                      created_out: list[int] | None = None
                      ) -> tuple[dict[str, int], list[int]]:
    """Найти точные карточки или создать новые; связать их с проектом.

    created_out (необязательный) пополняется сразу после создания карточки —
    чтобы частичный сбой можно было откатить. Возвращает
    (карта standard_key → mcp_id, id созданных карточек).
    """
    existing = mcp_repo.list()
    by_key: dict[str, int] = {}
    created = created_out if created_out is not None else []
    for plan in plans:
        match = None
        for row in existing:
            if row.get("standard_key") != plan.standard_key:
                continue
            if not _connection_equal(row.get("connection_json"), plan.connection_json):
                continue
            if plan.standard_key in ("code-index", "code-index-local"):
                if not same_path(row.get("catalog_dir") or "", plan.catalog_dir or ""):
                    continue
                if (row.get("project_name") or "") != (plan.project_name or ""):
                    continue
                if not same_path(row.get("code_index_dir") or "",
                                 plan.code_index_dir or ""):
                    continue
            match = row
            break
        if match is not None:
            by_key[plan.standard_key] = match["id"]
            log(f"✓ MCP «{plan.mcp_name}»: переиспользую карточку #{match['id']}")
            continue
        mid = mcp_repo.add(
            name=_unique_card_name(mcp_repo, f"{project_name}: {plan.mcp_name}"),
            purpose=plan.purpose,
            kind=plan.kind,
            standard_key=plan.standard_key,
            connection_json=plan.connection_json,
            port=plan.port,
            mcp_name=plan.mcp_name,
            url=plan.url,
            catalog_dir=plan.catalog_dir,
            project_name=plan.project_name,
            code_index_dir=plan.code_index_dir,
        )
        by_key[plan.standard_key] = mid
        created.append(mid)
        existing = mcp_repo.list()
        log(f"✓ MCP «{plan.mcp_name}»: создана карточка #{mid}")
    mcp_repo.set_for_project(project_id, list(by_key.values()))
    return by_key, created


def build_env_config(cfg: BenchConfig, plans: list[McpPlan]) -> EnvConfig:
    return EnvConfig(
        schema_version=SCHEMA_VERSION,
        project_name=cfg.project_name,
        project_dir=cfg.project_dir,
        developer_id=cfg.developer_id,
        developer_email=cfg.developer_email,
        platform_dir=cfg.platform_path,
        platform_version=cfg.platform_version,
        db_kind=cfg.db_kind,
        db_connection=cfg.db_connection,
        web_publication="",
        mcp=[
            McpSelection(
                id=plan.standard_key,
                enabled=True,
                mode="managed",
                connection=plan.connection_json,
                catalog_dir=plan.catalog_dir,
                project_name=plan.project_name,
                code_index_dir=plan.code_index_dir,
            )
            for plan in plans
        ],
        agents=[],
    )


def build_create_base_command(cfg: BenchConfig) -> list[str]:
    """Команда CREATEINFOBASE для серверной или файловой базы."""
    conn = _parse_connection(cfg.db_kind, cfg.db_connection)
    if cfg.db_kind == "file":
        return [cfg.platform_path, "CREATEINFOBASE", f'File="{conn["path"]}"']
    return [
        cfg.platform_path, "CREATEINFOBASE",
        f'Srvr={conn["server"]};Ref={conn["base"]}',
    ]


def ensure_base(cfg: BenchConfig, *, prov, log=print) -> None:
    """Создать базу, если её нет. Существование серверной базы заранее не проверить:
    неудачный CREATEINFOBASE не фатален — ошибка проявится на restore/load."""
    if cfg.db_kind == "file":
        conn = _parse_connection(cfg.db_kind, cfg.db_connection)
        if Path(conn["path"]).exists():
            log(f"✓ база уже существует: {conn['path']}")
            return
    cmd = build_create_base_command(cfg)
    res = prov.run(cmd)
    if res.returncode != 0:
        tail = ((res.stdout or "") + (res.stderr or "")).strip()[-1000:]
        log(f"⚠ CREATEINFOBASE вернул код {res.returncode} "
            f"(возможно, база уже существует): {tail}")
    else:
        log(f"✓ база создана: {cfg.db_connection}")


def base_load_steps(cfg: BenchConfig, repo_root: Path) -> list[list[str]]:
    """Последовательность аргументов 1c-batch для подготовки базы."""
    if cfg.dt_path:
        return [["restore-ib", cfg.dt_path]]
    steps = [["load-config", str(repo_root / "benchmark" / "cf")]]
    for rel, name in EXTENSIONS:
        steps.append(["load-cfg-extension", str(repo_root / rel), "--name", name])
        steps.append(["update-db-cfg", "--extension", name])
    return steps


def base_dump_steps() -> list[list[str]]:
    return [
        ["dump-config", "src/cf"],
        ["dump-config", "src/cfe", "--all-extensions"],
    ]


def _venv_python(project_dir: str) -> str:
    base = Path(project_dir) / ".venv"
    suffix = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return str(base / suffix)


_DB_LOCK_MARK = "Ошибка исключительной блокировки информационной базы"
_BATCH_RETRY_DELAYS = (30, 60)


def run_batch_step(project_dir: str, args: list[str], *, prov, log=print,
                   retry_delays=_BATCH_RETRY_DELAYS,
                   sleep=time.sleep) -> None:
    """Выполнить команду 1c-batch интерпретатором .venv проекта.

    Транзиентная блокировка ИБ (фоновое задание/чужой сеанс) повторяется по
    `retry_delays`: без ретрая setup падает на ровном месте.
    """
    script = (Path(project_dir) / ".claude" / "skills" / "1c-batch"
              / "scripts" / "1c-batch.py")
    cmd = [_venv_python(project_dir), str(script), *args]
    attempt = 0
    while True:
        res = prov.run(cmd, cwd=project_dir)
        tail = ((res.stdout or "") + (res.stderr or "")).strip()[-2000:]
        if res.returncode == 0:
            log(f"✓ 1c-batch {args[0]}")
            return
        if (_DB_LOCK_MARK in tail and attempt < len(retry_delays)):
            delay = retry_delays[attempt]
            attempt += 1
            log(f"⚠ 1c-batch {args[0]}: ИБ заблокирована — повтор "
                f"{attempt}/{len(retry_delays)} через {delay} с")
            sleep(delay)
            continue
        raise SetupError(
            f"1c-batch {' '.join(args)} завершился с кодом "
            f"{res.returncode}:\n{tail}")


@dataclass(frozen=True)
class ImportedTask:
    identifier: str
    task_id: int
    folder: str


_TASK_HEADER_RE = re.compile(r"^(# Задача .+?) \(#\d+\):", re.MULTILINE)


def _task_max_minutes(data: dict, folder: str) -> int:
    """max_minutes задачи: отсутствует → 60; не целое или < 1 → SetupError."""
    value = data.get("max_minutes")
    if value is None:
        return 60
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        raise SetupError(
            f"{folder}/task.json: max_minutes должен быть целым числом, "
            f"получено {value!r}") from None
    if minutes < 1:
        raise SetupError(
            f"{folder}/task.json: max_minutes должен быть не меньше 1, "
            f"получено {value!r}")
    return minutes


def _task_identifier(data: dict, folder: str) -> str:
    """identifier из task.json, иначе номер из имени папки (task#001 → #001)."""
    identifier = str(data.get("identifier") or "").strip()
    if identifier:
        return identifier
    digits = re.sub(r"\D", "", folder)
    return f"#{digits}" if digits else folder


def _source_task_dirs(repo_root: Path) -> list[Path]:
    tasks_root = repo_root / "benchmark" / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(
        path for path in tasks_root.iterdir()
        if path.is_dir() and (path / "task.json").is_file()
    )


def import_tasks(*, project_id: int, cfg: BenchConfig, repo_root: Path,
                 store, log=print) -> list[ImportedTask]:
    """Скопировать задачи benchmark/tasks, завести их в БД и обновить id в файлах."""
    sources = _source_task_dirs(repo_root)
    if not sources:
        raise SetupError(f"в {repo_root / 'benchmark' / 'tasks'} нет ни одной задачи")

    repo = TaskRepo(store)
    imported: list[ImportedTask] = []
    for source in sources:
        raw = (source / "task.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        identifier = _task_identifier(data, source.name)
        max_minutes = _task_max_minutes(data, source.name)

        destination = Path(cfg.project_dir) / "tasks" / source.name
        shutil.copytree(source, destination)

        now = time.time()
        task_id = repo.add(
            project_id=project_id,
            name=data.get("name", ""),
            identifier=identifier,
            goal=data.get("goal", ""),
            plan=data.get("plan", ""),
            constraints=data.get("constraints", ""),
            tests=data.get("tests", ""),
            stages_json=json.dumps(data.get("stages", []), ensure_ascii=False),
            status="planned",
            stage=None,
            now=now,
            kind=data.get("kind") or "real",
            update_db=1 if data.get("update_db") else 0,
            max_minutes=max_minutes,
            interactive=0,
            mark_changes=1 if data.get("mark_changes") else 0,
        )

        data["id"] = task_id
        data["project_id"] = project_id
        data["developer_id"] = cfg.developer_id
        data["status"] = "planned"
        data["stage"] = None
        data["started_at"] = None
        data["finished_at"] = None
        data["created_at"] = to_local_iso(now)
        data["update_db"] = bool(data.get("update_db"))
        data["mark_changes"] = bool(data.get("mark_changes"))
        (destination / "task.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        task_md = destination / "TASK.md"
        if task_md.is_file():
            text = task_md.read_text(encoding="utf-8")
            updated = _TASK_HEADER_RE.sub(
                lambda match: f"{match.group(1)} (#{task_id}):", text, count=1)
            if updated != text:
                task_md.write_text(updated, encoding="utf-8")
            else:
                log(f"⚠ {source.name}/TASK.md: заголовок не распознан — "
                    "id не обновлён")

        imported.append(ImportedTask(identifier, task_id, source.name))
        log(f"✓ задача {identifier} → #{task_id} ({source.name})")
    return imported


def commit_init(cfg: BenchConfig, prov) -> None:
    git_init_project(prov, cfg.project_dir, config=cfg)
    git_commit_all(prov, cfg.project_dir, "init", config=cfg)


def commit_baseline(cfg: BenchConfig, tasks: list[ImportedTask], prov) -> None:
    if not tasks:
        return
    git_commit_all(
        prov, cfg.project_dir,
        f"baseline before task{tasks[0].identifier}", config=cfg)


@dataclass(frozen=True)
class SetupResult:
    project_id: int
    task_ids: list[int]
    code_index: str
    project_dir: str


@dataclass
class RollbackState:
    project_dir: str
    project_id: int | None = None
    task_ids: list[int] | None = None
    created_mcp_ids: list[int] | None = None
    code_index: NativeIndex | None = None

    def __post_init__(self) -> None:
        if self.task_ids is None:
            self.task_ids = []
        if self.created_mcp_ids is None:
            self.created_mcp_ids = []


def rollback(state: RollbackState, *, store, run=subprocess.run,
             log=print) -> None:
    """Убрать записи этого запуска; каталог проекта оставить для диагностики."""
    warnings: list[str] = []

    def warn(message: str) -> None:
        warnings.append(message)
        log(f"⚠ {message}")

    task_repo = TaskRepo(store)
    for task_id in state.task_ids:
        try:
            task_repo.delete(task_id)
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат задачи #{task_id}: {exc}")

    mcp_repo = McpRepo(store)
    if state.project_id is not None:
        try:
            mcp_repo.set_for_project(state.project_id, [])
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат связей MCP: {exc}")
    for mid in state.created_mcp_ids:
        try:
            mcp_repo.delete(mid)
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат MCP #{mid}: {exc}")
    if state.project_id is not None:
        try:
            ProjectRepo(store).delete(state.project_id)
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат проекта #{state.project_id}: {exc}")

    if state.code_index is not None:
        try:
            code_index_bench.stop_code_index(
                state.code_index.code_index_dir, run=run, log=log)
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат code-index {state.code_index.code_index_dir}: {exc}")

    if warnings:
        log("✗ Откат выполнен частично: " + "; ".join(warnings))
    else:
        log("✗ Откат выполнен.")
    log(f"✗ Каталог проекта оставлен для диагностики: {state.project_dir}. "
        "Удалите его перед повторным запуском.")


def run_setup(cfg: BenchConfig, *, repo_root: Path, store, registry,
              prov=None, run=subprocess.run, sleep=time.sleep,
              clock=time.monotonic, log=print, tcp_ok=default_tcp_ok,
              http_ok=default_http_ok, install_env=install_environment,
              batch_run=run_batch_step, launch_index=start_code_index,
              wait_index=wait_code_index_ready,
              recreate: bool = False) -> SetupResult:
    """Полный сценарий подготовки проекта. Ошибка → откат записей БД.

    recreate=True: предварительно проверить конфигурацию и удалить существующий
    проект (каталог, запись store и реестра), затем создать заново.
    """
    if prov is None:
        from ..backends.local import LocalProvisioner
        prov = LocalProvisioner()

    if recreate:
        preflight(cfg, repo_root=repo_root, store=store, registry=registry,
                  tcp_ok=tcp_ok, http_ok=http_ok, allow_existing=True)
        remove_existing_project(cfg, store=store, registry=registry, log=log)
    preflight(cfg, repo_root=repo_root, store=store, registry=registry,
              tcp_ok=tcp_ok, http_ok=http_ok)

    state = RollbackState(project_dir=cfg.project_dir)
    try:
        log(f"▶ проект «{cfg.project_name}» ({cfg.project_dir})")
        Path(cfg.project_dir).mkdir(parents=True)

        project_id = create_project_row(store, cfg)
        state.project_id = project_id

        plans = build_mcp_plans(cfg)
        resolve_mcp_cards(
            McpRepo(store), plans, project_id=project_id,
            project_name=cfg.project_name, log=log,
            created_out=state.created_mcp_ids)
        config = build_env_config(cfg, plans)

        log("▶ окружение проекта")
        for event in install_env(
                config, update=False, register=lambda cfg_: None,
                dump_cf=False, dump_cfe=False, git_init=False,
                db_user=cfg.db_user, db_password=cfg.db_password, prov=prov):
            detail = f" {event.detail}" if event.detail else ""
            log(f"[{event.step}] {event.status}{detail}")

        log("▶ база 1С")
        ensure_base(cfg, prov=prov, log=log)
        for args in base_load_steps(cfg, repo_root):
            batch_run(cfg.project_dir, args, prov=prov, log=log)
        if cfg.one_c_md_url:
            check_mcp_url(cfg.one_c_md_url, http_ok=http_ok, log=log,
                          sleep=sleep)

        log("▶ выгрузка cf/cfe")
        for args in base_dump_steps():
            batch_run(cfg.project_dir, args, prov=prov, log=log)

        log("▶ code_index (native)")
        code_index = launch_index(
            code_index_dir=cfg.code_index_dir,
            catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
            alias=cfg.project_name, port=cfg.code_index_port,
            host=cfg.code_index_host, run=run, log=log)
        state.code_index = code_index

        log("▶ git init")
        commit_init(cfg, prov)

        log("▶ задачи benchmark")
        tasks = import_tasks(project_id=project_id, cfg=cfg,
                             repo_root=repo_root, store=store, log=log)
        state.task_ids = [task.task_id for task in tasks]
        commit_baseline(cfg, tasks, prov)

        log("▶ ожидание индексации code_index")
        wait_index(code_index, wait_minutes=cfg.code_index_wait_minutes,
                   host=cfg.code_index_host, port=cfg.code_index_port,
                   run=run, sleep=sleep, clock=clock, log=log)

        registry.add(name=cfg.project_name, path=cfg.project_dir,
                     backend="local")
        return SetupResult(
            project_id=project_id,
            task_ids=[task.task_id for task in tasks],
            code_index=str(code_index.code_index_dir),
            project_dir=cfg.project_dir,
        )
    except BaseException:
        rollback(state, store=store, run=run, log=log)
        raise
