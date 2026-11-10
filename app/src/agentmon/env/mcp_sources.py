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

    sha = getattr(build, "repo_sha", None)
    if sha:
        dest = Path(repo_root) / build.repo_dir
        checkout = ["git", "-C", str(dest), "checkout", "--detach", sha]
        log += f"$ {' '.join(checkout)}\n"
        try:
            rc = run(checkout, capture_output=True, text=True)
        except OSError as exc:
            return {"ok": False, "cloned": True, "log": log + f"{exc}\n"}
        log += (getattr(rc, "stdout", "") or "") + (getattr(rc, "stderr", "") or "")
        if getattr(rc, "returncode", 1) != 0:
            shutil.rmtree(dest, ignore_errors=True)   # не собирать чужой HEAD
            return {"ok": False, "cloned": True, "log": log}
    return {"ok": True, "cloned": True, "log": log}
