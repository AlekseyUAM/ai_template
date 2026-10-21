"""Сборка самодостаточного docker-образа агента ai1c-agent:<версия>.

Образ содержит только платформу 1С (из указанного дистрибутива) и рантайм
агента. Зависимостей от deps/docker_1c_sandbox нет.
"""
import re
import subprocess
from pathlib import Path

AGENT_IMAGE_PREFIX = "ai1c-agent"

# app/src/agentmon/env/docker_image.py → parents[3] == app/
DOCKERFILE_PATH = Path(__file__).resolve().parents[3] / "docker" / "agent-image" / "Dockerfile"


def _docker_argv(docker_host, tail):
    """["docker"] + опциональный -H <host> + tail."""
    return ["docker"] + (["-H", docker_host] if docker_host else []) + tail


def image_tag(platform_version: str) -> str:
    """Тег образа из версии платформы: ai1c-agent:<sanitized>.

    Нормализация: strip + lower, оставляем только [a-z0-9_.-].
    Пустой результат → ai1c-agent:latest.
    """
    safe = re.sub(r"[^a-z0-9_.\-]", "", (platform_version or "").strip().lower())
    return f"{AGENT_IMAGE_PREFIX}:{safe or 'latest'}"


def image_exists(tag: str, docker_host: str | None = None, run=subprocess.run) -> bool:
    """True, если docker images -q <tag> напечатал непустой id."""
    r = run(_docker_argv(docker_host, ["images", "-q", tag]),
            capture_output=True, text=True)
    return r.returncode == 0 and bool((r.stdout or "").strip())
