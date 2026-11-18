"""Скачивание исходников MCP-серверов из deps/ при первом развёртывании.

Репозитории из `deps/` не входят в состав ai_template (см. `.gitignore`),
поэтому перед сборкой образа нужный исходник клонируется, если его ещё нет.
"""
import shutil
import subprocess
from pathlib import Path

from .mcp_docker_recipes import BuildSpec


def clone_cmd(build: BuildSpec | None, repo_root) -> list[str] | None:
    """Команда `git clone` для отсутствующего каталога исходников.

    None — если источника нет, задано только одно из полей repo_dir/repo_url
    или каталог уже существует.
    """
    if build is None or not build.repo_dir or not build.repo_url:
        return None
    dest = Path(repo_root) / build.repo_dir
    if dest.exists():
        return None
    return ["git", "clone", "--depth", "1", build.repo_url, str(dest)]


def checkout_cmd(build: BuildSpec | None, repo_root) -> list[str] | None:
    """Команда переключения на запиненный коммит (None, если пина нет)."""
    if build is None or not (build.repo_sha and build.repo_dir and build.repo_url):
        return None
    dest = Path(repo_root) / build.repo_dir
    return ["git", "-C", str(dest), "checkout", "--detach", build.repo_sha]


def fetch_pin_cmd(build: BuildSpec | None, repo_root) -> list[str] | None:
    """Команда дотягивания пина в shallow-клон (None, если пина нет)."""
    if build is None or not (build.repo_sha and build.repo_dir and build.repo_url):
        return None
    dest = Path(repo_root) / build.repo_dir
    return ["git", "-C", str(dest), "fetch", "--depth", "1",
            "origin", build.repo_sha]


def _run_logged(cmd, run, log: str) -> tuple[bool, str]:
    """Выполняет команду, дописывая её и вывод в лог. Возвращает (ok, log)."""
    log += f"$ {' '.join(cmd)}\n"
    try:
        r = run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return False, log + f"{exc}\n"
    log += (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return getattr(r, "returncode", 1) == 0, log


def clone(build: BuildSpec | None, repo_root, run=subprocess.run) -> dict:
    """Клонирует источник (блокирующе); возвращает {ok, cloned, log}.

    Если задан repo_sha, после клона переключаемся на этот коммит. Сборка идёт
    из pinned-состояния: компрометация main не подменяет контекст docker build.
    """
    cmd = clone_cmd(build, repo_root)
    if cmd is None:
        return {"ok": True, "cloned": False, "log": ""}
    log = f"$ {' '.join(cmd)}\n"
    try:
        r = run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return {"ok": False, "cloned": True, "log": log + f"{exc}\n"}
    log += (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    if getattr(r, "returncode", 1) != 0:
        return {"ok": False, "cloned": True, "log": log}

    checkout = checkout_cmd(build, repo_root)
    if checkout is not None:
        dest = Path(repo_root) / build.repo_dir
        ok, log = _run_logged(checkout, run, log)
        if not ok:
            # `--depth 1` приносит только tip ветки: если пин — предок, объекта
            # нет. Дотягиваем нужный коммит явно (GitHub отдаёт SHA по запросу).
            fetch = fetch_pin_cmd(build, repo_root)
            ok, log = _run_logged(fetch, run, log)
            if ok:
                ok, log = _run_logged(checkout, run, log)
        if not ok:
            shutil.rmtree(dest, ignore_errors=True)   # не собирать чужой HEAD
            return {"ok": False, "cloned": True, "log": log}
    return {"ok": True, "cloned": True, "log": log}
