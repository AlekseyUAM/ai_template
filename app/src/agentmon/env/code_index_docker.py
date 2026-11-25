"""Нативный code-index внутри docker-контейнера проекта."""
from __future__ import annotations

import json
import shlex
import shutil
import tempfile
import time

from .code_index_release import download_binary
from .code_index_toml import ensure_sections, merge_path

BINARY = "bsl-indexer"
WAIT_MINUTES = 360


def _ci(path) -> str:
    return str(path).rstrip("/")


def _binary(ci: str) -> str:
    return f"{ci}/{BINARY}"


def _stop_processes(prov) -> None:
    try:
        prov.run(["sh", "-c", "pkill -f '[b]sl-indexer' || true"])
    except Exception:                                  # noqa: BLE001
        pass


def _spawn(prov, ci: str, tail: str, log_name: str,
           env: dict | None = None) -> None:
    argv = ["sh", "-c",
            f"cd {shlex.quote(ci)} && ./{BINARY} {tail} "
            f">> {log_name}.log 2>&1"]
    result = prov.exec_detached(argv, env={"CODE_INDEX_HOME": ci, **(env or {})})
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"code-index не запустился ({tail}): "
            f"{(getattr(result, 'stderr', '') or '').strip()}")


def deploy(prov, *, code_index_dir, catalog_dir, alias, port,
           download=download_binary, log=print):
    """Развернуть/обновить сервис code-index внутри контейнера."""
    ci = _ci(code_index_dir)
    prov.mkdirs([ci])
    yield f"▶ code-index в контейнере: {ci} (alias={alias}, порт {port})"
    if not prov.exists(_binary(ci)):
        tmp = tempfile.mkdtemp(prefix="bsl-indexer-")
        try:
            buf = []
            binary = download(tmp, log=buf.append, platform_name="linux")
            yield from buf
            prov.copy_in(str(binary), _binary(ci))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        prov.run(["chmod", "+x", _binary(ci)])
        yield "✓ бинарь установлен в контейнер"
    toml_path = f"{ci}/daemon.toml"
    text = prov.read_text(toml_path) if prov.exists(toml_path) else ""
    text = merge_path(text, alias=alias, path=str(catalog_dir))
    text = ensure_sections(text, int(port))
    prov.write_text(toml_path, text)
    yield f"✓ daemon.toml: alias={alias}, path={catalog_dir}"
    _stop_processes(prov)
    _spawn(prov, ci, "daemon run", "daemon")
    _spawn(prov, ci,
           f"serve --transport http --host 127.0.0.1 --port {int(port)} "
           f"--config {toml_path}", "serve",
           env={"MCP_HTTP_HOST": "127.0.0.1", "MCP_HTTP_PORT": str(int(port))})
    yield f"✓ code-index запущен в контейнере, порт {port}"


def _status(prov, ci: str):
    try:
        res = prov.run([_binary(ci), "daemon", "status", "--json"],
                       env={"CODE_INDEX_HOME": ci})
    except Exception:                                  # noqa: BLE001
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def _alive(prov) -> bool:
    try:
        res = prov.run(["sh", "-c",
                        "pgrep -f '[b]sl-indexer' >/dev/null && echo y"])
    except Exception:                                  # noqa: BLE001
        return False
    return (getattr(res, "stdout", "") or "").strip() == "y"


def _tail(prov, path: str) -> str:
    try:
        res = prov.run(["sh", "-c", 'tail -n 15 "$1" 2>/dev/null', "sh", path])
    except Exception:                                  # noqa: BLE001
        return ""
    return (getattr(res, "stdout", "") or "").strip()


def wait_ready(prov, *, code_index_dir, port, wait_minutes=WAIT_MINUTES,
               status=None, alive=None, log_tail=None,
               sleep=time.sleep, clock=time.monotonic, log=print) -> None:
    """Дождаться готовности индекса внутри контейнера."""
    ci = _ci(code_index_dir)
    status = status or (lambda: _status(prov, ci))
    alive = alive or (lambda: _alive(prov))
    log_tail = log_tail or (lambda name: _tail(prov, f"{ci}/{name}.log"))
    deadline = clock() + wait_minutes * 60
    while True:
        data = status()
        paths = (data or {}).get("paths") or []
        for p in paths:
            if p.get("status") == "error":
                raise RuntimeError(
                    f"code-index: ошибка индексации {p.get('path', '?')}: "
                    f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
        if not alive():
            raise RuntimeError(
                "code-index в контейнере завершился; последние строки логов:\n"
                f"--- serve.log ---\n{log_tail('serve') or '(пусто)'}\n"
                f"--- daemon.log ---\n{log_tail('daemon') or '(пусто)'}")
        ready = bool(paths) and all(p.get("status") == "ready" for p in paths)
        if ready:
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if clock() >= deadline:
            raise RuntimeError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {ci}/daemon.log в контейнере")
        sleep(5)


def stop(prov, code_index_dir) -> None:
    """Погасить bsl-indexer внутри контейнера (best-effort)."""
    _stop_processes(prov)
