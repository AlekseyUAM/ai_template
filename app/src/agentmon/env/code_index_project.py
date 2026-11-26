"""Code-index проекта: валидация, порт, карточка MCP, локальное ожидание."""
from __future__ import annotations

import json
import os
import posixpath
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import autostart, code_index_local
from .code_index_docker import deploy as docker_deploy
from .code_index_docker import stop as docker_stop
from .code_index_docker import wait_ready as docker_wait_ready
from .code_index_release import existing_binary
from .config_schema import McpSelection
from .mcp_types import get_type
from .net_probe import default_tcp_ok
from ..paths import same_path

WAIT_MINUTES = 360
STARTUP_GRACE_SEC = 120
PORT_START = 8005
PORT_TRIES = 100
LOCAL_KEY = "code-index"
DOCKER_KEY = "code-index-docker"


class CodeIndexError(RuntimeError):
    """Ошибка code-index (сообщение — для пользователя)."""


@dataclass(frozen=True)
class CodeIndexRequest:
    catalog_dir: str
    code_index_dir: str


def validate_request(backend: str, project_dir: str,
                     request: CodeIndexRequest) -> CodeIndexRequest:
    if backend not in ("local", "docker"):
        raise CodeIndexError(
            "code index поддерживается только для local и docker")
    catalog = (request.catalog_dir or "").strip()
    ci = (request.code_index_dir or "").strip()
    if not catalog or not ci:
        raise CodeIndexError(
            "заполните «Каталог кодовой базы» и «Каталог code_index»")
    if backend == "local":
        if not Path(catalog).is_absolute():
            raise CodeIndexError("«Каталог кодовой базы» должен быть абсолютным")
        if not Path(ci).is_absolute():
            raise CodeIndexError("«Каталог code_index» должен быть абсолютным")
        project = Path(project_dir).resolve()
        ci_real = Path(ci).resolve()
        if ci_real == project or project in ci_real.parents:
            raise CodeIndexError(
                "«Каталог code_index» не должен находиться внутри каталога проекта")
    else:
        if not catalog.startswith("/") or not ci.startswith("/"):
            raise CodeIndexError(
                "для docker пути должны быть абсолютными (начинаться с /)")
        project = posixpath.normpath(project_dir)
        ci_norm = posixpath.normpath(ci)
        if ci_norm == project or ci_norm.startswith(project.rstrip("/") + "/"):
            raise CodeIndexError(
                "«Каталог code_index» не должен находиться внутри каталога проекта")
    return CodeIndexRequest(catalog, ci)


def pick_port(read_port, *, tcp_ok=default_tcp_ok, host_check=True,
              start=PORT_START) -> int:
    port = read_port()
    if port is not None:
        return int(port)
    if not host_check:
        return int(start)
    for port in range(int(start), int(start) + PORT_TRIES):
        if not tcp_ok(f"http://127.0.0.1:{port}"):
            return port
    raise CodeIndexError(
        f"не найден свободный порт в диапазоне {start}-{start + PORT_TRIES - 1}")


def pick_port_for_local(code_index_dir, *, tcp_ok=default_tcp_ok) -> int:
    return pick_port(lambda: code_index_local.read_service_port(code_index_dir),
                     tcp_ok=tcp_ok)


def container_service_port(prov, code_index_dir) -> int | None:
    path = posixpath.join(str(code_index_dir).rstrip("/"), "service.json")
    if not prov.exists(path):
        return None
    try:
        data = json.loads(prov.read_text(path))
    except (OSError, ValueError):
        return None
    port = data.get("port") if isinstance(data, dict) else None
    return port if isinstance(port, int) and 1 <= port <= 65535 else None


def _same_path(backend: str, left, right) -> bool:
    if backend == "docker":
        return (posixpath.normpath(str(left or ""))
                == posixpath.normpath(str(right or "")))
    return same_path(str(left or ""), str(right or ""))


def _connection(port: int) -> str:
    entry = json.dumps({"type": "http",
                        "url": f"http://localhost:{int(port)}/mcp"},
                       ensure_ascii=False)
    return f'"code_index": {entry}'


def _selection(*, backend, request, port, project_name) -> McpSelection:
    return McpSelection(
        id=LOCAL_KEY if backend == "local" else DOCKER_KEY,
        enabled=True,
        mode="managed",
        connection=_connection(port),
        catalog_dir=request.catalog_dir,
        project_name=project_name,
        code_index_dir=request.code_index_dir,
    )


def _unique_name(repo, base: str) -> str:
    names = {row.get("name") for row in repo.list()}
    name, index = base, 2
    while name in names:
        name = f"{base} {index}"
        index += 1
    return name


def _connection_equal(left, right) -> bool:
    try:
        return (json.loads("{" + (left or "") + "}")
                == json.loads("{" + right + "}"))
    except (TypeError, ValueError):
        return (left or "") == right


def resolve_card(mcp_repo, *, project_id: int, project_name: str,
                 backend: str, request: CodeIndexRequest,
                 port: int) -> tuple[int, McpSelection, bool]:
    key = LOCAL_KEY if backend == "local" else DOCKER_KEY
    kind = "local" if backend == "local" else "docker"
    connection = _connection(port)
    for row in mcp_repo.list():
        if row.get("standard_key") != key:
            continue
        if not _connection_equal(row.get("connection_json"), connection):
            continue
        if not _same_path(backend, row.get("catalog_dir"), request.catalog_dir):
            continue
        if (row.get("project_name") or "") != project_name:
            continue
        if not _same_path(backend, row.get("code_index_dir"),
                          request.code_index_dir):
            continue
        selection = _selection(backend=backend, request=request, port=port,
                               project_name=project_name)
        return row["id"], selection, False
    mid = mcp_repo.add(
        name=_unique_name(mcp_repo, f"{project_name}: code_index"),
        purpose=get_type(LOCAL_KEY).defaults["purpose"],
        kind=kind, standard_key=key, connection_json=connection,
        port=int(port), mcp_name="code_index", url="localhost",
        catalog_dir=request.catalog_dir, project_name=project_name,
        code_index_dir=request.code_index_dir,
    )
    selection = _selection(backend=backend, request=request, port=port,
                           project_name=project_name)
    return mid, selection, True


def service_is_new(backend: str, *, prov=None, code_index_dir) -> bool:
    if backend == "docker":
        return container_service_port(prov, code_index_dir) is None
    return code_index_local.read_service_port(code_index_dir) is None


def deploy(backend: str, *, prov=None, code_index_dir, catalog_dir,
           project_name, port, mid=None, log=print):
    if backend == "local":
        return code_index_local.deploy_local(
            code_index_dir=code_index_dir, catalog_dir=catalog_dir,
            project_name=project_name, port=port, mid=mid)
    return docker_deploy(prov, code_index_dir=code_index_dir,
                         catalog_dir=catalog_dir, alias=project_name,
                         port=port, log=log)


def local_status(code_index_dir, *, binary_finder=existing_binary,
                 run=subprocess.run):
    binary = binary_finder(Path(code_index_dir))
    if binary is None:
        return None
    env = {**os.environ, "CODE_INDEX_HOME": str(code_index_dir)}
    try:
        res = run([str(binary), "daemon", "status", "--json"],
                  env=env, capture_output=True, text=True)
    except OSError:
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def _daemon_alive(code_index_dir) -> bool | None:
    """Жив ли демон (None — PID ещё не записан)."""
    try:
        from .code_index_bench import _daemon_state_pid, _is_our_process
        pid = _daemon_state_pid(code_index_dir)
    except Exception:                                  # noqa: BLE001
        return None
    if pid is None:
        return None
    return _is_our_process(pid)


def _log_tail(path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-15:])


def wait_ready_local(code_index_dir, *, port, wait_minutes=WAIT_MINUTES,
                     status=local_status, tcp_ok=default_tcp_ok,
                     alive=_daemon_alive, log_tail=None,
                     grace_seconds=STARTUP_GRACE_SEC,
                     sleep=time.sleep, clock=time.monotonic, log=print) -> None:
    ci = Path(code_index_dir)
    log_tail = log_tail or (lambda name: _log_tail(ci / f"{name}.log"))
    started = clock()
    deadline = started + wait_minutes * 60
    seen_alive = False
    while True:
        data = status(code_index_dir)
        paths = (data or {}).get("paths") or []
        daemon_alive = alive(code_index_dir)
        now = clock()
        if daemon_alive:
            seen_alive = True
        # После перезапуска демона (deploy_local) daemon.json ещё хранит PID
        # прежнего процесса: это не повод падать, ждём старта в grace-окне.
        # Если демон был жив и умер — падаем сразу.
        if (daemon_alive is False
                and (seen_alive or now - started > grace_seconds)):
            raise CodeIndexError(
                "code-index завершился; последние строки логов:\n"
                f"--- serve.log ---\n{log_tail('serve') or '(пусто)'}\n"
                f"--- daemon.log ---\n{log_tail('daemon') or '(пусто)'}")
        if daemon_alive:
            for p in paths:
                if p.get("status") == "error":
                    raise CodeIndexError(
                        f"code-index: ошибка индексации {p.get('path', '?')}: "
                        f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
            ready = bool(paths) and all(
                p.get("status") == "ready" for p in paths)
            if ready and tcp_ok(f"http://127.0.0.1:{int(port)}"):
                log("✓ code-index готов: " + ", ".join(
                    p.get("path", "?") for p in paths))
                return
        if data is None and now - started > grace_seconds:
            raise CodeIndexError(
                "code-index не запустился за "
                f"{grace_seconds} с; смотрите {ci}/daemon.log:\n"
                f"{log_tail('daemon') or '(пусто)'}")
        if now >= deadline:
            raise CodeIndexError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {ci}/daemon.log")
        sleep(5)


def wait_ready(backend: str, *, prov=None, code_index_dir, port,
               wait_minutes=WAIT_MINUTES, log=print) -> None:
    if backend == "docker":
        docker_wait_ready(prov, code_index_dir=code_index_dir, port=port,
                          wait_minutes=wait_minutes, log=log)
    else:
        wait_ready_local(code_index_dir, port=port,
                         wait_minutes=wait_minutes, log=log)


def stop_new_service(backend: str, *, prov=None, code_index_dir) -> None:
    if backend == "docker":
        docker_stop(prov, code_index_dir)
        return
    daemon_name, serve_name = code_index_local.service_names(code_index_dir)
    for name in (serve_name, daemon_name):
        try:
            autostart.stop(name, state_dir=str(code_index_dir))
        except Exception:                              # noqa: BLE001
            pass
    try:
        (Path(code_index_dir) / code_index_local.SERVICE_FILE).unlink()
    except OSError:
        pass
