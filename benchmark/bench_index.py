"""Свежесть индекса code_index и его перезапуск между задачами benchmark."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_CONTAINER = "ai1c-mcp-code_index"
_SKIP_DIRS = {".code-index", ".git", "__pycache__", "node_modules"}


def index_db_path(project_dir: Path) -> Path:
    return project_dir / "src" / "cf" / ".code-index" / "index.db"


def newest_source_mtime(root: Path) -> float | None:
    """Новейший mtime среди файлов и каталогов дерева ``root``.

    Каталоги учитываются наравне с файлами: удаление и переименование
    исходника меняют mtime каталога, а не оставшихся файлов, — иначе
    устаревший индекс оставался бы «свежим».
    """
    try:
        newest = root.stat().st_mtime
    except OSError:
        newest = None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        paths = [Path(dirpath, name) for name in (*dirnames, *filenames)]
        for path in paths:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if newest is None or mtime > newest:
                newest = mtime
    return newest


def index_is_stale(project_dir: Path) -> bool:
    root = project_dir / "src" / "cf"
    db = index_db_path(project_dir)
    if not root.is_dir() or not db.is_file():
        return False
    newest = newest_source_mtime(root)
    if newest is None:
        return False
    try:
        return newest > db.stat().st_mtime
    except OSError:
        return False


def _daemon_status(container: str, run) -> dict | None:
    # CODE_INDEX_HOME=/data/code-index-home — каталог из Docker-рецепта
    # code_index (app/src/agentmon/env/mcp_docker_recipes.py); без него
    # daemon status ищет индекс по умолчанию и не видит данные контейнера.
    try:
        result = run(
            ["docker", "exec", container, "env",
             "CODE_INDEX_HOME=/data/code-index-home",
             "bsl-indexer", "daemon", "status", "--json"],
            capture_output=True, text=True)
    except OSError:
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(result, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def refresh_index(project_dir: Path, *, enabled: bool = True,
                  container: str = DEFAULT_CONTAINER,
                  run=subprocess.run, sleep=time.sleep,
                  clock=time.monotonic, timeout_sec: float = 900,
                  log=print) -> str:
    """Обновить индекс, если он отстал от исходников. Возвращает статус."""
    if not enabled:
        return "disabled"
    if not index_is_stale(project_dir):
        return "fresh"
    if shutil.which("docker") is None:
        log("⚠ индекс code_index устарел, но docker не найден — пропускаю")
        return "skipped"
    try:
        restart = run(["docker", "restart", container],
                      capture_output=True, text=True)
    except OSError as exc:
        log(f"⚠ не удалось перезапустить code_index: {exc}")
        return "failed"
    if getattr(restart, "returncode", 1) != 0:
        log("⚠ не удалось перезапустить контейнер code_index: "
            + (getattr(restart, "stderr", "") or "").strip()[:300])
        return "failed"
    deadline = clock() + timeout_sec
    while clock() < deadline:
        data = _daemon_status(container, run)
        paths = (data or {}).get("paths") or []
        if paths and all(item.get("status") == "ready" for item in paths):
            return "ready"
        sleep(5)
    log(f"⚠ code_index не стал ready за {timeout_sec:.0f} с")
    return "failed"
