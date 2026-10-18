"""Docker-бэкенд: контейнер как долгоживущая служебная машина.

Агент и команды входят через `docker exec` (см. следующие задачи).
Все команды выполняются через инъектируемый `run=subprocess.run`,
чтобы тесты шли без реального докера.
"""
import hashlib
import logging
import re
import subprocess
import time
from pathlib import Path

from . import BUFFER_LIMIT, RunResult, is_cruft  # noqa: F401 — is_cruft/BUFFER_LIMIT нужны позже
from ..env import mcp_docker

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "ai1c-agent:latest"
DEFAULT_WORKDIR = "/workspace"
DEFAULT_RETRY_SECONDS = 10.0


def container_name(path: str) -> str:
    """Детерминированное имя контейнера ``ai1c-<slug>`` из пути к проекту.

    Слаг строится из очищенного basename (только ``[a-z0-9_.-]``) плюс
    короткий хеш полного пути — коллизии исключены даже для проектов с
    одинаковыми именами каталогов.
    """
    base = Path(path).name
    safe_base = re.sub(r"[^a-z0-9_.\-]", "", base.lower())[:24] or "project"
    short_hash = hashlib.sha1(path.encode()).hexdigest()[:8]
    return f"ai1c-{safe_base}-{short_hash}"


class _DockerContainer:
    """Одиночный долгоживущий контейнер для одного проекта.

    Контейнер запускается раз (``ensure``) и живёт до явного ``remove``.
    Агент и команды потом входят через ``exec_run`` / ``docker exec``.
    Паттерн битого окна — идентичен ``_Connection`` в ssh-бэкенде:
    ``mark_broken`` идемпотентен, отсчёт окна не перезапускается.
    """

    def __init__(
        self,
        name: str,
        image: str,
        *,
        workdir: str,
        volume: str,
        add_hosts: list[str] | None = None,
        env: dict | None = None,
        run=subprocess.run,
        clock=time.monotonic,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
    ):
        self._name = name
        self._image = image
        self._workdir = workdir
        self._volume = volume
        self._add_hosts = add_hosts if add_hosts is not None else ["host.docker.internal:host-gateway"]
        self._env = {"DISPLAY": ":99", **(env or {})}
        self._run = run
        self._clock = clock
        self._retry_seconds = retry_seconds
        self._broken_at: float | None = None

    # ------------------------------------------------------------------
    # Состояние «сломан»
    # ------------------------------------------------------------------

    def mark_broken(self) -> None:
        """Пометить контейнер битым.

        Идемпотентно: если уже помечен, отсчёт окна повторных попыток
        не перезапускается — иначе частые вызовы держали бы окно вечно.
        """
        if self.broken:
            return
        self._broken_at = self._clock()

    @property
    def broken(self) -> bool:
        """True, если контейнер помечен битым и окно ещё не истекло."""
        return self._broken_at is not None

    def _within_retry_window(self) -> bool:
        """Находимся ли внутри окна повторных попыток после поломки."""
        if self._broken_at is None:
            return False
        return self._clock() - self._broken_at < self._retry_seconds

    # ------------------------------------------------------------------
    # Статус контейнера
    # ------------------------------------------------------------------

    def status(self) -> str:
        """Состояние контейнера: ``"running"`` | ``"exited"`` | ``"absent"``.

        Используем ``docker inspect -f '{{.State.Status}}'`` напрямую,
        а не ``mcp_docker.status``, чтобы различать ``exited`` и ``absent``.
        """
        r = self._run(
            ["docker", "inspect", "-f", "{{.State.Status}}", self._name],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return "absent"
        raw = (r.stdout or "").strip().lower()
        if raw == "running":
            return "running"
        if raw in ("exited", "created", "paused", "restarting", "removing", "dead"):
            return "exited"
        return "absent"

    # ------------------------------------------------------------------
    # Хук сборки образа (переопределяется в следующих задачах)
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Хук сборки образа. По умолчанию бросает ошибку — образ должен существовать.

        Следующие задачи могут переопределить этот метод реальной сборкой.
        """
        raise RuntimeError(
            f"образ {self._image!r} не найден; "
            f"соберите тулкит-образ из deps/docker_1c_sandbox"
        )

    # ------------------------------------------------------------------
    # Управление жизненным циклом
    # ------------------------------------------------------------------

    def ensure(self) -> None:
        """Убедиться, что контейнер запущен.

        Порядок:
        1. Если образа нет — вызвать хук ``_build`` (по умолчанию исключение).
        2. absent → ``docker run -d --name ... sleep infinity``.
        3. exited → ``docker start <name>``.
        4. running → контейнер уже поднят, но Xvfb всё ещё гарантируется ниже.
        При ненулевом коде docker run/start → ``mark_broken()`` + ``RuntimeError``.
        """
        if not mcp_docker.image_exists(self._image, run=self._run):
            self._build()

        state = self.status()
        if state == "absent":
            cmd = [
                "docker", "run", "-d",
                "--name", self._name,
                "--restart", "unless-stopped",
            ]
            for h in self._add_hosts:
                cmd.append(f"--add-host={h}")
            cmd += ["-v", f"{self._volume}:{self._workdir}"]
            for k, v in self._env.items():
                cmd += ["-e", f"{k}={v}"]
            cmd += [self._image, "sleep", "infinity"]
            r = self._run(cmd, capture_output=True, text=True)
        elif state == "exited":
            r = self._run(
                ["docker", "start", self._name],
                capture_output=True, text=True,
            )
        else:
            r = None  # running — контейнер уже поднят

        if r is not None and r.returncode != 0:
            log = ((r.stdout or "") + (r.stderr or "")).strip()
            self.mark_broken()
            raise RuntimeError(
                f"Не удалось запустить контейнер {self._name!r}: {log}"
            )

        # Xvfb — на каждом ensure (идемпотентно): контейнер мог быть уже
        # запущен, но его Xvfb мог умереть. 1С Конфигуратор требует X-дисплей.
        xvfb_cmd = (
            "pgrep -f 'Xvfb :99' >/dev/null 2>&1 "
            "|| setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1"
        )
        self._run(
            ["docker", "exec", "-d", self._name, "sh", "-c", xvfb_cmd],
            capture_output=True, text=True,
        )

    # ------------------------------------------------------------------
    # Запуск команд внутри контейнера
    # ------------------------------------------------------------------

    def exec_run(self, argv: list[str], cwd: str | None = None) -> RunResult:
        """Выполнить команду внутри контейнера через ``docker exec``.

        Возвращает ``RunResult(returncode, stdout, stderr)``.
        """
        cmd = ["docker", "exec"]
        if cwd:
            cmd += ["-w", cwd]
        cmd.append(self._name)
        cmd.extend(argv)
        r = self._run(cmd, capture_output=True, text=True)
        return RunResult(
            returncode=r.returncode,
            stdout=(r.stdout or ""),
            stderr=(r.stderr or ""),
        )

    def exec_input(self, argv: list[str], data: bytes) -> RunResult:
        """Выполнить команду внутри контейнера, подав ``data`` в stdin.

        Нужно для ``write_bytes`` (следующие задачи): передаёт байты по stdin
        вместо отдельной операции копирования файлов. ``docker exec -i`` держит
        stdin открытым, что позволяет передать данные через ``input=``.
        """
        cmd = ["docker", "exec", "-i", self._name, *argv]
        r = self._run(cmd, input=data, capture_output=True)
        return RunResult(
            returncode=r.returncode,
            stdout=(r.stdout or b"").decode("utf-8", "replace")
            if isinstance(r.stdout, bytes) else (r.stdout or ""),
            stderr=(r.stderr or b"").decode("utf-8", "replace")
            if isinstance(r.stderr, bytes) else (r.stderr or ""),
        )

    # ------------------------------------------------------------------
    # Удаление контейнера
    # ------------------------------------------------------------------

    def remove(self) -> None:
        """Принудительно удалить контейнер (``docker rm -f <name>``)."""
        self._run(
            ["docker", "rm", "-f", self._name],
            capture_output=True,
            text=True,
        )
