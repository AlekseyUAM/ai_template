"""Файловые операции env-слоя на машине проекта.

Env-БД хранит только ``path``; бэкенд (local/ssh/docker) — в реестре. Для
нелокальных проектов файлы задач лежат на другой машине, поэтому операции
идут через provisioner бэкенда, а не через ``Path`` на хосте монитора.
"""
from __future__ import annotations

from types import SimpleNamespace

from ..paths import same_path


def project_backend(registry, path: str) -> tuple[str, dict | None]:
    """(backend, conn) проекта из реестра; без записи — local/None."""
    if registry is not None:
        try:
            entries = registry.list()
        except Exception:                              # noqa: BLE001
            entries = []                               # реестр недоступен → local
        for reg in entries:
            if same_path(reg.path, path):
                return reg.backend or "local", reg.conn
    return "local", None


def project_provisioner(registry, monitor, path: str):
    """Provisioner машины проекта или None для local.

    None означает «делать прежние Path-операции на хосте монитора» — так
    поведение local-проектов не меняется. Для нелокального бэкенда без
    доступа к monitor бросаем ошибку: молча писать в хостовый путь нельзя.
    """
    backend, conn = project_backend(registry, path)
    if backend == "local":
        return None
    if monitor is None or getattr(monitor, "backends", None) is None:
        raise RuntimeError(
            f"нет доступа к бэкенду {backend!r} для проекта {path}")
    from ..models import Project

    probe = Project(id=0, name="probe", path=path, backend=backend,
                    conn=conn or {}, claude_cmd=None, created_at=0.0)
    return monitor.backends.get(probe).provisioner


def project_like(project_row, registry=None, backends=None):
    """Лёгкий объект проекта для Monitor: backend/conn/claude_cmd из реестра.

    project_row — строка ProjectRepo env-БД (id/name/path); бэкенда в ней нет.
    Без записи в реестре — local (прежнее поведение). ``backends`` нужен,
    чтобы вычислить настоящий ключ бэкенда (с токеном docker-хоста).
    """
    backend, conn, claude_cmd = "local", None, None
    if registry is not None:
        try:
            entries = registry.list()
        except Exception:                              # noqa: BLE001
            entries = []
        for reg in entries:
            if same_path(reg.path, project_row["path"]):
                backend = reg.backend or "local"
                conn = reg.conn
                claude_cmd = reg.claude_cmd
                break
    project = SimpleNamespace(
        id=project_row["id"],
        path=project_row["path"],
        name=project_row["name"],
        key=f"{backend}||{project_row['path']}",
        backend=backend,
        conn=conn,
        claude_cmd=claude_cmd,
    )
    if backends is not None:
        try:
            project.key = backends.key_for(project)
        except Exception:                              # noqa: BLE001
            pass
    return project
