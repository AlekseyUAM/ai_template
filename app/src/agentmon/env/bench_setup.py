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
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .config_schema import SCHEMA_VERSION, EnvConfig, McpSelection
from .devbase import _parse_connection, git_commit_all, git_init_project
from .mcp_docker_recipes import container_name, launch_params, recipe_for
from . import mcp_docker
from . import mcp_sources
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


def _connection_http(name: str, url: str) -> str:
    """Фрагмент справочника MCP: `"<имя>": {...}` (без внешних фигурных скобок)."""
    entry = json.dumps({"type": "http", "url": url}, ensure_ascii=False)
    return f'"{name}": {entry}'


def _connection_platform(url: str) -> str:
    """Фрагмент справочника MCP: `"1c_platform": {...}` через stdio-мост."""
    server = json.dumps(
        {
            "type": "stdio",
            "command": "python3",
            "args": [".claude/mcp/sse_stdio_bridge.py", url],
        },
        ensure_ascii=False,
    )
    return f"\"1c_platform\": {server}"


def _url_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname or "", port


def default_tcp_ok(url: str, timeout: float = 3.0) -> bool:
    """True, если TCP-соединение с хостом/портом URL устанавливается."""
    host, port = _url_host_port(url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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
              tcp_ok=default_tcp_ok) -> None:
    """Проверить всё, что можно проверить до создания каталога и записей БД."""
    ok, error = validate_name(cfg.project_name)
    if not ok:
        raise SetupError(f"недопустимое BENCH_PROJECT_NAME: {error}")

    project_dir = Path(cfg.project_dir)
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


def build_mcp_plans(cfg: BenchConfig) -> list[McpPlan]:
    bsl_host, bsl_port = _url_host_port(cfg.bsl_ls_url)
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
    plans.append(McpPlan(
        standard_key="code-index", mcp_name="code_index", kind="docker",
        connection_json=_connection_http(
            "code_index",
            f"http://{cfg.code_index_host}:{cfg.code_index_port}/mcp"),
        purpose=("Полнотекстовый поиск по функциям и классам, граф вызовов, "
                 "паспорт объекта"),
        url=cfg.code_index_host, port=cfg.code_index_port,
        catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
        project_name=cfg.project_name,
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
            if plan.standard_key == "code-index":
                if not same_path(row.get("catalog_dir") or "", plan.catalog_dir or ""):
                    continue
                if (row.get("project_name") or "") != (plan.project_name or ""):
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


def run_batch_step(project_dir: str, args: list[str], *, prov, log=print) -> None:
    """Выполнить команду 1c-batch интерпретатором .venv проекта."""
    script = (Path(project_dir) / ".claude" / "skills" / "1c-batch"
              / "scripts" / "1c-batch.py")
    cmd = [_venv_python(project_dir), str(script), *args]
    res = prov.run(cmd, cwd=project_dir)
    if res.returncode != 0:
        tail = ((res.stdout or "") + (res.stderr or "")).strip()[-2000:]
        raise SetupError(
            f"1c-batch {' '.join(args)} завершился с кодом "
            f"{res.returncode}:\n{tail}")
    log(f"✓ 1c-batch {args[0]}")


def default_http_ok(url: str, timeout: float = 5.0) -> bool:
    """Любой HTTP-ответ (включая 4xx) означает, что сервис слушает."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "ai1c-agentmon"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def check_mcp_url(url: str, *, http_ok=default_http_ok, log=print) -> None:
    if not http_ok(url):
        raise SetupError(f"1c-md недоступен по адресу {url}")
    log(f"✓ 1c-md доступен: {url}")


@dataclass(frozen=True)
class ImportedTask:
    identifier: str
    task_id: int
    folder: str


_TASK_HEADER_RE = re.compile(r"^(# Задача .+?) \(#\d+\):", re.MULTILINE)


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
        identifier = str(data.get("identifier") or "").strip()
        if not identifier:
            identifier = source.name.removeprefix("task#")

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
            max_minutes=int(data.get("max_minutes") or 60),
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


CODE_INDEX_CONTAINER = "ai1c-mcp-code_index"


def _image_absent(image: str, run) -> bool:
    """Отсутствие образа: docker-опрос тем же `run`, что и остальные команды."""
    return not mcp_docker.image_exists(image, run=run)


def _build_code_index_image(repo_root: Path, *, run, log=print) -> None:
    recipe = recipe_for("code-index")
    build = recipe.build
    if build is None:
        raise SetupError(f"образ {recipe.image} отсутствует, а сборка недоступна")
    cloned = mcp_sources.clone(build, str(repo_root), run=run)
    if not cloned["ok"]:
        raise SetupError("не удалось скачать исходники code-index:\n"
                         + cloned.get("log", ""))
    built = mcp_docker.build(
        recipe.image, str(repo_root / build.dockerfile),
        str(repo_root / build.context), run=run)
    if not built["ok"]:
        raise SetupError("не удалось собрать образ code-index:\n"
                         + built.get("log", ""))
    log(f"✓ образ code-index собран: {recipe.image}")


def launch_code_index(cfg: BenchConfig, *, repo_root: Path, mid: int,
                      run=subprocess.run, image_exists=_image_absent,
                      launch=mcp_docker.launch, build_image=None,
                      log=print) -> str:
    """Пересоздать контейнер code_index и вернуть его имя."""
    name = container_name({"mcp_name": "code_index"})
    run(["docker", "rm", "-f", "-v", name], capture_output=True, text=True)

    state_dir = Path(repo_root) / ".ai1c" / "mcp-state" / str(mid)
    params = launch_params(
        "code-index",
        port=cfg.code_index_port,
        catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
        state_dir=str(state_dir),
        project_name=cfg.project_name,
    )
    if not image_exists(params["image"]):
        if build_image is None:
            _build_code_index_image(repo_root, run=run, log=log)
        else:
            build_image()

    result = launch(
        name=name,
        image=params["image"],
        port=cfg.code_index_port,
        internal_port=params["internal_port"],
        env=params["env"],
        volumes=params["volumes"],
        network=params.get("network"),
        run=run,
    )
    if not result.get("ok"):
        raise SetupError(
            f"не удалось запустить контейнер {name}:\n{result.get('log', '')}")
    log(f"✓ контейнер code_index запущен: {name} "
        f"(порт {cfg.code_index_port})")
    return name


def _daemon_status(name: str, run):
    result = run(
        ["docker", "exec", name, "env",
         "CODE_INDEX_HOME=/data/code-index-home",
         "bsl-indexer", "daemon", "status", "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError):
        return None


def wait_code_index_ready(name: str, *, cfg: BenchConfig,
                          run=subprocess.run, sleep=time.sleep,
                          clock=time.monotonic, log=print) -> None:
    """Дождаться статуса ready для всех путей (полная первичная индексация)."""
    deadline = clock() + cfg.code_index_wait_minutes * 60
    last_state = None
    while True:
        data = _daemon_status(name, run)
        if data:
            paths = data.get("paths") or []
            errors = [p for p in paths if p.get("status") == "error"]
            if errors:
                raise SetupError(
                    "code_index завершился с ошибкой: "
                    + ", ".join(f"{p.get('path')}: {p.get('status')}"
                                for p in errors))
            if paths and all(p.get("status") == "ready" for p in paths):
                log("✓ индекс code_index готов: "
                    + ", ".join(p.get("path", "?") for p in paths))
                return
            state = ", ".join(
                f"{p.get('path')}: {p.get('status')}" for p in paths)
            if state != last_state:
                log(f"… индексация code_index: {state or 'нет данных'}")
                last_state = state
        if clock() >= deadline:
            raise SetupError(
                "code_index не проиндексировал базу за "
                f"{cfg.code_index_wait_minutes} мин; увеличьте "
                "CODE_INDEX_WAIT_MINUTES")
        sleep(15)
