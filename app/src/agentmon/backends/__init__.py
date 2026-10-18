"""Абстракция целевой машины.

Бэкенд решает две независимые задачи, поэтому и протоколов два: процессами
управляет AgentRunner, журналы сессий читает SessionFiles. Для SSH их
реализации принципиально разные (канал с PTY против SFTP), и тестировать их
удобнее порознь.
"""

from dataclasses import dataclass
from typing import Protocol

from ..models import FileRef, Project


class AgentRunner(Protocol):
    def start(self, project: Project) -> str: ...
    def send_input(self, agent_id: str, text: str) -> None: ...
    def stop(self, agent_id: str, mode: str) -> None: ...
    def is_alive(self, agent_id: str) -> bool: ...
    def tail_output(self, agent_id: str, limit: int = 65536) -> str: ...
    def shutdown_all(self) -> None: ...


class SessionFiles(Protocol):
    def home_projects_dir(self) -> str: ...
    def list_files(self, projects_dir: str) -> list[FileRef]: ...
    def read_from(self, path: str, offset: int) -> tuple[bytes, int]: ...


@dataclass
class RunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Provisioner(Protocol):
    """Операции над файловой системой целевой машины и запуск команд на ней.

    Позволяет развернуть проект на любой цели (локальная ФС, удалённый хост по
    SFTP, контейнер) одним и тем же кодом слоя `env/`. put_tree читает дерево с
    машины монитора (local_src всегда локален) и переносит его на цель.
    """

    def mkdirs(self, paths: list[str]) -> None: ...
    def exists(self, path: str) -> bool: ...
    def is_empty_dir(self, path: str) -> bool: ...
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, content: str) -> None: ...
    def write_bytes(self, path: str, data: bytes) -> None: ...
    def put_tree(self, local_src: str, dst: str, skip=None) -> None: ...
    def run(self, cmd: list[str], cwd: str | None = None) -> "RunResult": ...
    def which(self, tool: str) -> str | None: ...
    def python_cmd(self) -> list[str]: ...
    def venv_python(self, project_dir: str) -> str: ...


class Backend:
    """Пара «исполнитель + доступ к журналам» для одной целевой машины."""

    key: str
    runner: AgentRunner
    files: SessionFiles
    provisioner: "Provisioner"

    @property
    def is_broken(self) -> bool:
        """Потеряна ли связь с машиной.

        Бэкенды, отказ которых невозможен (local), оставляют False. Монитор
        спрашивает это после каждого обхода: SSH-бэкенд глушит ошибки внутри
        (list_files возвращает [], is_alive — False), и без явного вопроса
        недоступный хост выглядел бы в интерфейсе как просто незапущенный.
        """
        return False

    def check(self) -> None:
        """Проверить доступность машины. Бросает исключение при отказе."""

    def close(self) -> None:
        self.runner.shutdown_all()


BUFFER_LIMIT = 65536
