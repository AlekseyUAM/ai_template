"""Скачивание исходников MCP-серверов из deps/ при первом развёртывании.

Репозитории из `deps/` не входят в состав ai_template (см. `.gitignore`),
поэтому перед сборкой образа нужный исходник клонируется, если его ещё нет.
"""
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
    """Клонирует источник (блокирующе); возвращает {ok, cloned, log}."""
    cmd = clone_cmd(build, repo_root)
    if cmd is None:
        return {"ok": True, "cloned": False, "log": ""}
    log = f"$ {' '.join(cmd)}\n"
    try:
        r = run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return {"ok": False, "cloned": True, "log": log + f"{exc}\n"}
    log += (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "cloned": True, "log": log}
