from dataclasses import dataclass


@dataclass(frozen=True)
class FileRef:
    """Ссылка на файл журнала сессии на целевой машине.

    dir_name и session_id вычисляет бэкенд — ядро не разбирает пути само,
    чтобы не зависеть от разделителя каталогов целевой ОС.
    """
    path: str
    dir_name: str
    session_id: str
    size: int
    mtime: float


@dataclass
class Project:
    id: int | None
    name: str
    path: str
    backend: str                 # "local" | "ssh"
    conn: dict | None            # {host, port, user, key_path} для ssh
    claude_cmd: str | None       # переопределение команды запуска
    created_at: float

    @property
    def host(self) -> str | None:
        return (self.conn or {}).get("host")

    @property
    def key(self) -> str:
        """Уникальный ключ проекта; он же id агента и часть ключа бэкенда."""
        return f"{self.backend}|{self.host or ''}|{self.path}"


@dataclass
class SessionSnapshot:
    session_id: str
    project_path: str
    model: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: float
    last_activity: float
    state: str                   # "generating" | "idle"
    current_phase: str | None


@dataclass
class Task:
    id: int
    project_id: int
    text: str
    status: str                  # "queued" | "running" | "done" | "failed"
    created_at: float
    started_at: float | None
    finished_at: float | None
    session_id: str | None
