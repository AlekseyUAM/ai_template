"""Сборка самодостаточного docker-образа агента ai1c-agent:<версия>.

Образ содержит только платформу 1С (из указанного дистрибутива) и рантайм
агента. Зависимостей от deps/docker_1c_sandbox нет.
"""
import os
import re
import shutil
import subprocess
import tempfile
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


def build_agent_image(distr_path, platform_version, docker_host=None,
                      popen=subprocess.Popen):
    """Собрать образ ai1c-agent:<версия> из дистрибутива платформы.

    Генератор: построчно отдаёт вывод docker build. По завершении при
    ненулевом коде — RuntimeError. Некорректный дистрибутив — ValueError.
    """
    if not distr_path or not os.path.isfile(distr_path):
        raise ValueError(f"дистрибутив не найден: {distr_path!r}")
    if not distr_path.lower().endswith(".zip"):
        raise ValueError(f"дистрибутив должен быть .zip: {distr_path!r}")

    tag = image_tag(platform_version)
    ctx = tempfile.mkdtemp(prefix="ai1c-build-")
    try:
        staged = os.path.join(ctx, "distr.zip")
        try:
            os.link(distr_path, staged)      # дёшево: без копирования многогиг .zip
        except OSError:
            shutil.copy2(distr_path, staged)  # другой раздел (EXDEV) — копируем
        argv = _docker_argv(docker_host, [
            "build", "-t", tag, "-f", str(DOCKERFILE_PATH), ctx,
        ])
        proc = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
        if proc.stdout is not None:
            for line in proc.stdout:
                yield line
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"docker build вернул код {rc} (образ {tag})")
    finally:
        shutil.rmtree(ctx, ignore_errors=True)
