"""Нативный code-index для benchmark: detached daemon/serve + PID-файл."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .code_index_release import download_binary
from .code_index_toml import render_daemon_toml
from .net_probe import default_tcp_ok

PID_FILE = "benchmark-pids.json"
STOP_TIMEOUT_SEC = 10.0
LEGACY_CONTAINER = "ai1c-mcp-code_index"


@dataclass(frozen=True)
class NativeIndex:
    code_index_dir: Path
    binary: Path
    daemon_pid: int
    serve_pid: int


def _pid_path(code_index_dir) -> Path:
    return Path(code_index_dir) / PID_FILE


def _read_pids(code_index_dir) -> list[int]:
    try:
        data = json.loads(_pid_path(code_index_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [int(v) for v in (data.get("daemon"), data.get("serve"))
            if isinstance(v, int)]


def _write_pids(code_index_dir, daemon: int,
                serve: int | None = None) -> None:
    path = _pid_path(code_index_dir)
    path.write_text(json.dumps({"daemon": int(daemon), "serve": serve}) + "\n",
                    encoding="utf-8")


def _is_our_process(pid: int, run=subprocess.run) -> bool:
    if os.name == "nt":
        try:
            res = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                      capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return "bsl-indexer" in (getattr(res, "stdout", "") or "").lower()
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    return "bsl-indexer" in raw.decode("utf-8", "replace")


def _spawn_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)}
    return {"start_new_session": True}


def _wait_exit(pids, *, check, clock, sleep, timeout) -> list[int]:
    """PID, которые остались живы после ожидания в пределах timeout."""
    deadline = clock() + timeout
    alive = list(pids)
    while alive:
        if clock() >= deadline:
            return alive
        alive = [pid for pid in alive if check(pid)]
        if alive:
            sleep(0.2)
    return alive


def stop_code_index(code_index_dir, *, run=subprocess.run, kill=os.kill,
                    sleep=time.sleep, clock=time.monotonic, log=print,
                    wait=_wait_exit) -> None:
    pids = [pid for pid in _read_pids(code_index_dir)
            if _is_our_process(pid, run)]
    for pid in pids:
        if os.name == "nt":
            try:
                run(["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, text=True, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
    alive = wait(pids, check=lambda pid: _is_our_process(pid, run),
                 clock=clock, sleep=sleep, timeout=STOP_TIMEOUT_SEC)
    if os.name != "nt":
        for pid in alive:
            try:
                kill(pid, signal.SIGKILL)
            except (OSError, ValueError):
                pass
    try:
        _pid_path(code_index_dir).unlink()
    except OSError:
        pass


def clean_code_index(code_index_dir, catalog_dir, *, run=subprocess.run,
                     log=print) -> None:
    stop_code_index(code_index_dir, run=run, log=log)
    if Path(code_index_dir).exists():
        shutil.rmtree(code_index_dir, ignore_errors=False)
    index_dir = Path(catalog_dir) / ".code-index"
    if index_dir.exists():
        shutil.rmtree(index_dir, ignore_errors=False)
    if shutil.which("docker"):
        try:
            run(["docker", "rm", "-f", LEGACY_CONTAINER],
                capture_output=True, text=True)
            log(f"✓ legacy Docker-контейнер {LEGACY_CONTAINER} удалён "
                "(если был)")
        except OSError:
            pass


def start_code_index(*, code_index_dir, catalog_dir, alias, port,
                     host="127.0.0.1", download=download_binary,
                     popen=subprocess.Popen, run=subprocess.run,
                     log=print) -> NativeIndex:
    clean_code_index(code_index_dir, catalog_dir, run=run, log=log)
    ci = Path(code_index_dir)
    ci.mkdir(parents=True, exist_ok=True)
    binary = download(str(ci), log=log)
    toml_path = ci / "daemon.toml"
    toml_path.write_text(
        render_daemon_toml(alias, str(Path(catalog_dir).resolve()), int(port)),
        encoding="utf-8")
    env = {**os.environ, "CODE_INDEX_HOME": str(ci)}
    with (ci / "daemon.log").open("ab") as daemon_log:
        daemon = popen([str(binary), "daemon", "run"], cwd=str(ci),
                       env=env, stdout=daemon_log, stderr=subprocess.STDOUT,
                       **_spawn_kwargs())
    # PID демона пишется до spawn serve: если serve не стартует, демон
    # не останется сиротой без PID-файла.
    _write_pids(ci, daemon.pid)
    serve_env = {**env, "MCP_HTTP_HOST": host, "MCP_HTTP_PORT": str(port)}
    try:
        with (ci / "serve.log").open("ab") as serve_log:
            serve = popen([str(binary), "serve", "--transport", "http",
                           "--host", host, "--port", str(port),
                           "--config", str(toml_path)],
                          cwd=str(ci), env=serve_env, stdout=serve_log,
                          stderr=subprocess.STDOUT, **_spawn_kwargs())
    except BaseException:
        stop_code_index(ci, run=run, log=log)
        raise
    _write_pids(ci, daemon.pid, serve.pid)
    log(f"✓ code-index запущен: daemon pid={daemon.pid}, "
        f"serve pid={serve.pid}, порт {port}")
    return NativeIndex(ci, Path(binary), daemon.pid, serve.pid)


def _daemon_status(index: NativeIndex, run=subprocess.run):
    env = {**os.environ, "CODE_INDEX_HOME": str(index.code_index_dir)}
    try:
        res = run([str(index.binary), "daemon", "status", "--json"],
                  env=env, capture_output=True, text=True)
    except OSError:
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def wait_code_index_ready(index: NativeIndex, *, wait_minutes: int, host: str,
                          port: int, run=subprocess.run, sleep=time.sleep,
                          clock=time.monotonic, tcp_ok=default_tcp_ok,
                          log=print) -> None:
    # Локальный импорт: bench_setup будет импортировать этот модуль —
    # импорт на уровне модуля дал бы цикл.
    from .bench_setup import SetupError
    deadline = clock() + wait_minutes * 60
    while True:
        data = _daemon_status(index, run)
        paths = (data or {}).get("paths") or []
        for p in paths:
            if p.get("status") == "error":
                raise SetupError(
                    f"code-index: ошибка индексации {p.get('path', '?')}: "
                    f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
        ready = bool(paths) and all(p.get("status") == "ready"
                                    for p in paths)
        if ready and tcp_ok(f"http://{host}:{port}"):
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if not _is_our_process(index.daemon_pid, run) or \
                not _is_our_process(index.serve_pid, run):
            raise SetupError("native code-index завершился; смотрите "
                             f"{index.code_index_dir}/daemon.log и serve.log")
        if clock() >= deadline:
            raise SetupError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {index.code_index_dir}/daemon.log")
        sleep(5)
