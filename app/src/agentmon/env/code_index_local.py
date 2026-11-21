"""Нативное развёртывание code-index: один сервис на code_index_dir."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import autostart
from .code_index_release import download_binary as _download
from .code_index_toml import ensure_sections, merge_path, render_daemon_toml
from .net_probe import default_tcp_ok

SERVICE_FILE = "service.json"


def service_id(code_index_dir) -> str:
    raw = str(Path(code_index_dir).resolve()).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]


def service_names(code_index_dir) -> tuple[str, str]:
    sid = service_id(code_index_dir)
    return (f"ai1c-code-index-daemon-{sid}",
            f"ai1c-code-index-mcp-{sid}")


def read_service_port(code_index_dir) -> int | None:
    try:
        data = json.loads((Path(code_index_dir) / SERVICE_FILE)
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port = data.get("port")
    return port if isinstance(port, int) and 1 <= port <= 65535 else None


def write_service_port(code_index_dir, port: int) -> None:
    path = Path(code_index_dir) / SERVICE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"port": int(port), "version": 1}) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _find_binary(code_index_dir) -> Path | None:
    for name in ("bsl-indexer.exe", "bsl-indexer"):
        for path in Path(code_index_dir).rglob(name):
            if path.is_file():
                return path
    return None


def _reload_daemon(binary, code_index_dir, run) -> str | None:
    env = {**os.environ, "CODE_INDEX_HOME": str(code_index_dir)}
    try:
        res = run([str(binary), "daemon", "reload"], env=env,
                  capture_output=True, text=True)
    except OSError as exc:
        return str(exc)
    if getattr(res, "returncode", 1) != 0:
        return ((getattr(res, "stderr", "") or "")
                + (getattr(res, "stdout", "") or "")).strip()
    return None


def _restore_daemon_toml(toml_path: Path, previous_text: str | None) -> None:
    """Откатить daemon.toml к состоянию до первой установки."""
    try:
        if previous_text is None:
            toml_path.unlink(missing_ok=True)
            return
        tmp = toml_path.with_name(toml_path.name + ".tmp")
        tmp.write_text(previous_text, encoding="utf-8")
        tmp.replace(toml_path)
    except OSError:
        pass


def deploy_local(*, code_index_dir, catalog_dir, project_name, port,
                 mid=None, home=None, download=_download,
                 install=autostart.install_and_start,
                 restart=autostart.restart, stop=autostart.stop,
                 run=subprocess.run, tcp_ok=default_tcp_ok):
    ci = Path(code_index_dir)
    ci.mkdir(parents=True, exist_ok=True)
    existing_port = read_service_port(ci)
    if existing_port is not None and int(port) != existing_port:
        raise ValueError(
            f"сервис {ci} уже использует порт {existing_port}; "
            f"укажите его вместо {port}")
    effective_port = existing_port or int(port)
    first = existing_port is None
    if first and tcp_ok(f"http://127.0.0.1:{effective_port}"):
        # Перенос code_index_dir — не миграция: старый сервис остаётся на
        # порту и новый не сможет слушать. Падаем до любых установок.
        raise ValueError(
            f"порт {effective_port} уже занят; остановите старый code-index "
            "или выберите другой порт")
    yield (f"▶ code-index: {ci} (alias={project_name}, "
           f"порт {effective_port}, {'новый сервис' if first else 'добавление базы'})")

    binary = _find_binary(ci)
    if binary is None:
        buf = []
        binary = download(str(ci), log=buf.append)
        yield from buf
    toml_path = ci / "daemon.toml"
    previous_text = (toml_path.read_text(encoding="utf-8")
                     if toml_path.is_file() else None)
    text = previous_text or ""
    text = merge_path(text, alias=project_name, path=str(catalog_dir))
    text = ensure_sections(text, effective_port)
    toml_path.write_text(text, encoding="utf-8")
    yield f"✓ daemon.toml: alias={project_name}, path={catalog_dir}"

    daemon_name, serve_name = service_names(ci)
    home_env = {"CODE_INDEX_HOME": str(ci)}
    serve_env = {**home_env, "MCP_HTTP_HOST": "127.0.0.1",
                 "MCP_HTTP_PORT": str(effective_port)}
    serve_argv = [str(binary), "serve", "--transport", "http",
                  "--host", "127.0.0.1", "--port", str(effective_port),
                  "--config", str(toml_path)]

    if first:
        # legacy services must be stopped BEFORE the new serve binds the port
        if mid is not None:
            for legacy in (f"ai1c-code-index-daemon-{mid}",
                           f"ai1c-code-index-mcp-{mid}"):
                try:
                    yield from stop(legacy, state_dir=str(ci), home=home)
                except Exception as exc:                       # noqa: BLE001
                    yield f"⚠ legacy {legacy}: {exc}"
        installed = []
        try:
            installed.append(daemon_name)
            yield from install(daemon_name, [str(binary), "daemon", "run"],
                               env=home_env, state_dir=str(ci))
            installed.append(serve_name)
            yield from install(serve_name, serve_argv, env=serve_env,
                               state_dir=str(ci))
        except Exception:
            # Roll back a half-installed service so a retry starts clean.
            for name in reversed(installed):
                try:
                    yield from stop(name, state_dir=str(ci), home=home)
                except Exception:                              # noqa: BLE001
                    pass
            _restore_daemon_toml(toml_path, previous_text)
            raise
        write_service_port(ci, effective_port)
    else:
        error = _reload_daemon(binary, ci, run)
        if error:
            yield f"⚠ daemon reload: {error}"
        else:
            yield "✓ daemon reload"
        yield from restart(serve_name, state_dir=str(ci), home=home)

    yield (f"✓ code-index готов: {ci}, alias={project_name}, "
           f"порт {effective_port}")
