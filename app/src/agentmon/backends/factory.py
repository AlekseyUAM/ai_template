from .local import LocalBackend
from .ssh import DEFAULT_PORT, SshBackend


class BackendRegistry:
    """Кеш бэкендов по ключу подключения.

    Все локальные проекты делят один бэкенд; все проекты одного пользователя на
    одном хосте делят одно SSH-соединение.
    """

    def __init__(self, claude_cmd, local_factory=None, ssh_factory=None):
        self.claude_cmd = claude_cmd
        self._local_factory = local_factory or (lambda: LocalBackend(claude_cmd))
        self._ssh_factory = ssh_factory or (
            lambda conn: SshBackend(conn, claude_cmd))
        self._cache: dict[str, object] = {}

    def key_for(self, project) -> str:
        if project.backend == "local":
            return "local"
        if project.backend == "ssh":
            conn = project.conn or {}
            user = conn.get("user") or ""
            port = int(conn.get("port") or DEFAULT_PORT)
            return f"ssh|{user}@{conn.get('host')}:{port}"
        raise ValueError(f"неизвестный backend: {project.backend!r}")

    def get(self, project):
        key = self.key_for(project)
        backend = self._cache.get(key)
        if backend is None:
            backend = (self._local_factory() if project.backend == "local"
                       else self._ssh_factory(project.conn or {}))
            self._cache[key] = backend
        return backend

    def invalidate(self, key) -> None:
        backend = self._cache.pop(key, None)
        if backend is not None:
            try:
                backend.close()
            except Exception:
                pass

    def items(self):
        return list(self._cache.items())

    def close_all(self) -> None:
        for key in list(self._cache):
            self.invalidate(key)
