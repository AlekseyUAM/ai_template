"""Docker-бэкенд: контейнер как долгоживущая служебная машина.

Агент и команды входят через `docker exec` (см. следующие задачи).
Все команды выполняются через инъектируемый `run=subprocess.run`,
чтобы тесты шли без реального докера.
"""
import hashlib
import logging
import posixpath
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from . import BUFFER_LIMIT, Backend, RunResult, is_cruft
from ..models import FileRef
from .. import pty_process

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "ai1c-agent:latest"


# Коды возврата docker CLI, означающие «демон или контейнер недоступен»:
# 125 — ошибка самого docker CLI до входа в контейнер
# 126 — команда найдена, но не исполняема
# 127 — команда не найдена (exec не смог запустить sh/find/tail)
_CONTAINER_DOWN_RCS = frozenset({125, 126, 127})

# Фразы из stderr docker, однозначно указывающие на недоступность контейнера/демона.
# Совпадение проверяется как case-sensitive подстрока (это точные формулировки docker).
_CONTAINER_DOWN_PHRASES = (
    "No such container",
    "is not running",
    "Cannot connect to the Docker daemon",
    "No such exec",
    "error during connect",
)


def _is_container_down(rc: int, stderr: str) -> bool:
    """Вернуть True, если rc или stderr указывают на аварию контейнера/демона.

    Отличает «контейнер упал / демон недоступен» (→ mark_broken) от
    «каталог не существует / команда завершилась с ошибкой» (→ просто []).

    Критерии:
    - rc ∈ {125, 126, 127}: коды docker CLI для «не удалось войти в контейнер».
    - stderr содержит одну из точных docker-фраз, свидетельствующих о недоступности.
    """
    if rc in _CONTAINER_DOWN_RCS:
        return True
    return any(phrase in stderr for phrase in _CONTAINER_DOWN_PHRASES)


DEFAULT_WORKDIR = "/workspace"
DEFAULT_PLATFORM_DIR = "/opt/1cv8/current"
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
        claude_volume: str | None = None,
        claude_home: str = "/root/.claude",
        add_hosts: list[str] | None = None,
        env: dict | None = None,
        run=subprocess.run,
        clock=time.monotonic,
        retry_seconds: float = DEFAULT_RETRY_SECONDS,
        docker_host: str | None = None,
    ):
        """Инициализировать контейнер.

        ``claude_volume`` — имя именованного тома для персистентного ``~/.claude``
        (журналы сессий, авторизация claude). Если задан, при ``docker run``
        монтируется как ``-v {claude_volume}:{claude_home}``.
        ``claude_home`` — путь к ``.claude`` внутри контейнера; по умолчанию
        ``/root/.claude`` — совпадает с ``HOME`` образа при запуске без ``-u``.
        Для образов с непривилегированным пользователем используйте escape-hatch
        ``claude_home=...``.
        ``docker_host`` — адрес удалённого docker-демона (например, ``ssh://user@host``).
        Если задан, все docker-команды будут содержать ``-H <docker_host>`` сразу
        после ``docker``. Если ``None`` — поведение локальное, без изменений.
        """
        self._name = name
        self._image = image
        self._workdir = workdir
        self._volume = volume
        self._claude_volume = claude_volume
        self._claude_home = claude_home
        self._add_hosts = add_hosts if add_hosts is not None else ["host.docker.internal:host-gateway"]
        self._env = {"DISPLAY": ":99", **(env or {})}
        self._run = run
        self._clock = clock
        self._retry_seconds = retry_seconds
        self._docker_host = docker_host
        self._broken_at: float | None = None
        self._ready = False

    @property
    def name(self) -> str:
        """Имя контейнера (публичный доступ для DockerRunner)."""
        return self._name

    @property
    def docker_host(self) -> str | None:
        """Адрес удалённого docker-демона (``-H``); None — локальный демон."""
        return self._docker_host

    def _argv(self, tail: list[str]) -> list[str]:
        """Сформировать argv команды docker с опциональным ``-H`` для удалённого демона.

        При ``docker_host`` задан — вставляет ``-H <docker_host>`` сразу после
        ``docker`` (ssh-helper или TCP-сокет). При ``docker_host=None`` возвращает
        ровно ``["docker"] + tail`` — поведение байт в байт совпадает с прежним.
        """
        return ["docker"] + (["-H", self._docker_host] if self._docker_host else []) + tail

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
        self._ready = False

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
            self._argv(["inspect", "-f", "{{.State.Status}}", self._name]),
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
        if self._ready and not self.broken:
            return

        if self.broken and self._within_retry_window():
            raise RuntimeError(
                f"контейнер {self._name!r} недоступен, следующая попытка позже"
            )

        r_img = self._run(
            self._argv(["images", "-q", self._image]),
            capture_output=True, text=True,
        )
        image_present = r_img.returncode == 0 and bool((r_img.stdout or "").strip())
        if not image_present:
            self._build()

        state = self.status()
        if state == "absent":
            cmd = self._argv([
                "run", "-d",
                "--name", self._name,
                "--restart", "unless-stopped",
            ])
            for h in self._add_hosts:
                cmd.append(f"--add-host={h}")
            cmd += ["-v", f"{self._volume}:{self._workdir}"]
            if self._claude_volume is not None:
                cmd += ["-v", f"{self._claude_volume}:{self._claude_home}"]
            for k, v in self._env.items():
                cmd += ["-e", f"{k}={v}"]
            cmd += [self._image, "sleep", "infinity"]
            r = self._run(cmd, capture_output=True, text=True)
        elif state == "exited":
            r = self._run(
                self._argv(["start", self._name]),
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
            self._argv(["exec", "-d", self._name, "sh", "-c", xvfb_cmd]),
            capture_output=True, text=True,
        )
        self._broken_at = None
        self._ready = True

    # ------------------------------------------------------------------
    # Запуск команд внутри контейнера
    # ------------------------------------------------------------------

    def exec_run(self, argv: list[str], cwd: str | None = None,
                 timeout: float | None = None) -> RunResult:
        """Выполнить команду внутри контейнера через ``docker exec``.

        Возвращает ``RunResult(returncode, stdout, stderr)``.
        При timeout → ``RunResult(124, ..., ...\\n<timeout>)``.
        """
        tail = ["exec"]
        if cwd:
            tail += ["-w", cwd]
        tail.append(self._name)
        tail.extend(argv)
        cmd = self._argv(tail)
        try:
            r = self._run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            return RunResult(124, stdout, stderr + "\n<timeout>")
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
        cmd = self._argv(["exec", "-i", self._name, *argv])
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

    def exec_run_bytes(self, argv: list[str]) -> tuple[int, bytes, str]:
        """Выполнить команду внутри контейнера и вернуть сырые байты stdout и stderr.

        В отличие от ``exec_run``, не декодирует stdout — нужно для
        ``DockerFiles.read_from``, где важна побайтовая точность смещений.
        Возвращает ``(returncode, stdout_bytes, stderr_str)``.
        stderr декодируется из bytes с ``errors="replace"`` или берётся как str.
        """
        cmd = self._argv(["exec", self._name, *argv])
        r = self._run(cmd, capture_output=True)
        rc = r.returncode
        raw = r.stdout if isinstance(r.stdout, bytes) else (r.stdout or b"")
        if isinstance(r.stderr, bytes):
            stderr_str = r.stderr.decode("utf-8", errors="replace")
        else:
            stderr_str = r.stderr or ""
        return rc, raw, stderr_str

    def remove(self) -> None:
        """Принудительно удалить контейнер (``docker rm -f <name>``)."""
        self._run(
            self._argv(["rm", "-f", self._name]),
            capture_output=True,
            text=True,
        )


class DockerProvisioner:
    """Provisioner для Docker-контейнера: файловые операции и команды через docker exec.

    Реализует протокол ``Provisioner``: файловые операции идут через
    ``exec_run`` / ``exec_input`` (POSIX-пути внутри контейнера), дерево
    переносится с хоста через ``put_tree`` (обход ``rglob``, фильтр ``is_cruft``).
    Перед каждой операцией вызывает ``_ensure()`` — контейнер поднимается лениво.
    """

    def __init__(self, container: _DockerContainer, workdir: str = DEFAULT_WORKDIR):
        self._container = container
        self._workdir = workdir

    # ------------------------------------------------------------------
    # Вспомогательный метод
    # ------------------------------------------------------------------

    def _ensure(self) -> None:
        """Убедиться, что контейнер запущен (вызывается в начале каждой операции)."""
        self._container.ensure()

    # ------------------------------------------------------------------
    # Файловые операции
    # ------------------------------------------------------------------

    def mkdirs(self, paths: list[str]) -> None:
        """Создать каталоги (рекурсивно) внутри контейнера."""
        self._ensure()
        for p in paths:
            self._container.exec_run(["mkdir", "-p", p])

    def exists(self, path: str) -> bool:
        """True если путь существует внутри контейнера."""
        self._ensure()
        r = self._container.exec_run(["test", "-e", path])
        return r.returncode == 0

    def is_file(self, path: str) -> bool:
        """True если путь — обычный файл внутри контейнера."""
        self._ensure()
        r = self._container.exec_run(["test", "-f", path])
        return r.returncode == 0

    def is_empty_dir(self, path: str) -> bool:
        """True если каталог существует и пуст; False для файла или непустого каталога.

        Семантика идентична ``SshProvisioner.is_empty_dir``:
        - пустая строка пути → False;
        - путь не существует → True (идемпотентная логика «каталог свободен»);
        - путь — файл → False;
        - иначе перечислить содержимое ``ls -A``; True iff вывод пуст.
        """
        if not path:
            return False
        self._ensure()
        if not self.exists(path):
            return True
        if self.is_file(path):
            return False
        r = self._container.exec_run(["sh", "-c", f"ls -A {shlex.quote(path)}"])
        return r.returncode == 0 and r.stdout.strip() == ""

    def read_text(self, path: str) -> str:
        """Прочитать текстовый файл из контейнера через cat."""
        self._ensure()
        r = self._container.exec_run(["cat", path])
        return r.stdout

    def write_bytes(self, path: str, data: bytes) -> None:
        """Записать байты в файл внутри контейнера через stdin (cat >).

        Предварительно создаёт родительский каталог.
        """
        self._ensure()
        self.mkdirs([posixpath.dirname(path)])
        self._container.exec_input(
            ["sh", "-c", f"cat > {shlex.quote(path)}"],
            data,
        )

    def write_text(self, path: str, content: str) -> None:
        """Записать текстовый файл внутри контейнера (UTF-8)."""
        self.write_bytes(path, content.encode("utf-8"))

    def put_tree(self, local_src: str, dst: str, skip=None) -> None:
        """Перенести дерево каталогов с хоста в контейнер.

        Обходит ``local_src`` через ``rglob("*")``, пропускает служебные
        каталоги (``is_cruft``) и пути, для которых ``skip(rel)`` вернёт True.
        Каталоги создаются через ``mkdirs``, файлы — через ``write_bytes``.
        Симметрично ``SshProvisioner.put_tree``.
        """
        self._ensure()
        src = Path(local_src)
        for item in sorted(src.rglob("*")):
            rel = item.relative_to(src)
            if is_cruft(rel):
                continue
            if skip is not None and skip(rel):
                continue
            target = f"{dst}/{rel.as_posix()}"
            if item.is_dir():
                self.mkdirs([target])
            else:
                self.write_bytes(target, item.read_bytes())

    # ------------------------------------------------------------------
    # Запуск команд
    # ------------------------------------------------------------------

    def run(self, cmd: list[str], cwd: str | None = None,
            timeout: float | None = None) -> RunResult:
        """Выполнить команду внутри контейнера. При timeout → RunResult(124, ..., ...\\n<timeout>)."""
        self._ensure()
        return self._container.exec_run(cmd, cwd, timeout=timeout)

    def which(self, tool: str) -> str | None:
        """Найти исполняемый файл в контейнере через ``command -v``."""
        self._ensure()
        r = self._container.exec_run(["command", "-v", tool])
        path = r.stdout.strip()
        return path or None

    def python_cmd(self) -> list[str]:
        """Команда для запуска Python 3 в контейнере."""
        return ["python3"]

    def venv_python(self, project_dir: str) -> str:
        """Путь к интерпретатору виртуального окружения в контейнере."""
        return f"{project_dir}/.venv/bin/python"

    def tempdir(self) -> str:
        """Временный каталог внутри контейнера."""
        return "/tmp"


class DockerRunner:
    """Агент claude запускается внутри контейнера через ``docker exec -it``.

    PTY живёт на хосте — docker CLI пробрасывает терминал внутрь контейнера.
    Буферизация, накачка и жизненный цикл процессов — как у ``LocalRunner``;
    различие только в формировании команды и использовании хостового cwd.
    """

    def __init__(
        self,
        container,
        claude_cmd: str,
        workdir: str = DEFAULT_WORKDIR,
        spawn_fn=pty_process.spawn,
        host_cwd: str | None = None,
    ):
        self._container = container
        self.claude_cmd = claude_cmd
        self._workdir = workdir
        self._spawn = spawn_fn
        # cwd для spawn должен быть валиден на ХОСТЕ; project.path — путь
        # внутри контейнера и хостовой ФС не существует. Используем tempdir.
        self._host_cwd = host_cwd or tempfile.gettempdir()
        self._procs: dict[str, object] = {}
        self._buffers: dict[str, str] = {}

    def start(self, project) -> str:
        """Запустить агента в контейнере через ``docker exec -it``.

        Идемпотентен: если процесс уже жив, возвращает тот же agent_id.
        Перед запуском гарантирует, что контейнер поднят (``container.ensure``).
        Рабочий каталог внутри контейнера задаётся флагом ``-w``.
        """
        agent_id = project.key
        proc = self._procs.get(agent_id)
        if proc is not None and proc.alive:
            return agent_id
        self._container.ensure()
        cmd = project.claude_cmd or self.claude_cmd
        wrapped = (
            f"docker exec -it"
            f" -w {shlex.quote(self._workdir)}"
            f" {shlex.quote(self._container.name)}"
            f" {cmd}"
        )
        self._procs[agent_id] = self._spawn(wrapped, self._host_cwd)
        self._buffers[agent_id] = ""
        return agent_id

    def _pump(self, agent_id: str) -> None:
        """Вычитать доступный вывод процесса и дописать в буфер."""
        proc = self._procs.get(agent_id)
        if proc is None:
            return
        chunk = proc.read_available()
        if chunk:
            buf = self._buffers.get(agent_id, "") + chunk
            self._buffers[agent_id] = buf[-BUFFER_LIMIT:]

    def _require(self, agent_id: str):
        """Вернуть процесс или бросить KeyError, если агент не запущен."""
        proc = self._procs.get(agent_id)
        if proc is None:
            raise KeyError(f"агент не запущен: {agent_id}")
        return proc

    def send_input(self, agent_id: str, text: str) -> None:
        """Передать текст агенту в PTY.

        Переводы строк схлопываются в пробел — иначе они отправили бы ввод
        раньше времени. Строка завершается ``\\r`` (Enter в терминале).
        """
        proc = self._require(agent_id)
        self._pump(agent_id)
        clean = text.replace("\r", " ").replace("\n", " ")
        proc.write(clean + "\r")

    def stop(self, agent_id: str, mode: str = "interrupt") -> None:
        """Остановить агента.

        ``kill``   — убивает локальный PTY-процесс ``docker exec`` (контейнер
                     не трогаем) и убирает запись.
        ``interrupt`` — шлёт Escape; при записи в мёртвый PTY ловим OSError
                        и тихо забываем агента — как в ``LocalRunner``.
        """
        proc = self._require(agent_id)
        if mode == "kill":
            proc.kill()
            self._procs.pop(agent_id, None)
            self._buffers.pop(agent_id, None)
        else:
            try:
                proc.interrupt()
            except OSError as exc:
                # Запись в PTY мёртвого процесса — EIO/EBADF. Считаем агента
                # уже умершим и забываем его, как это делает ветка kill.
                logger.warning(
                    "не удалось прервать агента %s: процесс уже мёртв (%s)",
                    agent_id, exc,
                )
                self._procs.pop(agent_id, None)
                self._buffers.pop(agent_id, None)

    def is_alive(self, agent_id: str) -> bool:
        """Жив ли агент; мёртвые процессы убираются из словаря."""
        proc = self._procs.get(agent_id)
        if proc is None:
            return False
        self._pump(agent_id)
        if not proc.alive:
            self._procs.pop(agent_id, None)
            return False
        return True

    def tail_output(self, agent_id: str, limit: int = BUFFER_LIMIT) -> str:
        """Последние ``limit`` байт буфера вывода агента."""
        self._pump(agent_id)
        return self._buffers.get(agent_id, "")[-limit:]

    def shutdown_all(self) -> None:
        """Убить все запущенные агенты (docker exec PTY-процессы)."""
        for agent_id in list(self._procs):
            try:
                self._procs[agent_id].kill()
            except Exception:
                pass
        self._procs.clear()
        self._buffers.clear()


class DockerFiles:
    """Доступ к журналам сессий claude внутри Docker-контейнера.

    Домашний каталог пользователя внутри контейнера определяется лениво —
    угадывать его молча небезопасно: промах неотличим от «сессий пока нет»
    (``list_files`` тихо вернёт []). Поэтому при отсутствии явного ``home``
    он определяется при первом реальном обращении через
    ``docker exec <c> sh -c 'echo $HOME'`` и кешируется. Неудача не
    кешируется, чтобы определение повторилось, когда контейнер восстановится.
    """

    def __init__(self, container: _DockerContainer, home: str | None = None, guess: str = "/root"):
        self._container = container
        self._resolved_home: str | None = home
        self._guess = guess

    # ------------------------------------------------------------------
    # Ленивое определение домашнего каталога
    # ------------------------------------------------------------------

    def _resolve_home(self) -> str:
        """Вернуть домашний каталог пользователя внутри контейнера.

        Если ``home`` задан явно — возвращает его без exec.
        Иначе выполняет ``sh -c 'echo $HOME'`` и кеширует при успехе.
        При неудаче логирует предупреждение и возвращает ``guess`` БЕЗ
        кеширования, чтобы следующий вызов повторил попытку.
        """
        if self._resolved_home is not None:
            return self._resolved_home
        try:
            res = self._container.exec_run(["sh", "-c", "echo $HOME"])
        except Exception as exc:
            logger.warning(
                "не удалось определить домашний каталог в контейнере %s: %s, "
                "использую догадку %s",
                self._container.name, exc, self._guess,
            )
            return self._guess
        candidate = res.stdout.strip()
        if res.returncode == 0 and candidate and candidate.startswith("/"):
            self._resolved_home = candidate
            return candidate
        logger.warning(
            "не удалось определить домашний каталог в контейнере %s "
            "(rc=%d, stdout=%r), использую догадку %s",
            self._container.name, res.returncode, res.stdout, self._guess,
        )
        return self._guess

    # ------------------------------------------------------------------
    # SessionFiles protocol
    # ------------------------------------------------------------------

    def home_projects_dir(self) -> str:
        """Вернуть путь к каталогу проектов claude внутри контейнера."""
        try:
            home = self._resolve_home()
        except Exception:
            home = self._guess
        return f"{home.rstrip('/')}/.claude/projects"

    def list_files(self, projects_dir: str) -> list[FileRef]:
        """Перечислить журналы сессий (``*.jsonl``) в каталоге ``projects_dir``.

        Выполняет ``find <dir> -name '*.jsonl' -printf '%p\\t%s\\t%T@\\n'``
        внутри контейнера и разбирает вывод в список ``FileRef``.

        Ветки обработки результата:
        - ``rc == 0`` → разобрать строки в ``FileRef``.
        - ``rc != 0`` и ``_is_container_down(rc, stderr)`` → ``mark_broken()``
          и вернуть ``[]`` (контейнер упал или демон недоступен).
        - ``rc != 0`` иначе → вернуть ``[]`` без ``mark_broken``
          (каталог не существует, сессий ещё нет — штатная ситуация).
        - ``Exception`` → ``mark_broken()`` и ``[]`` (нельзя достучаться до
          контейнера вообще).
        """
        try:
            res = self._container.exec_run(
                ["find", projects_dir, "-name", "*.jsonl", "-printf", "%p\t%s\t%T@\n"]
            )
        except Exception as exc:
            logger.warning(
                "ошибка find в контейнере %s: %s",
                self._container.name, exc,
            )
            self._container.mark_broken()
            return []

        if res.returncode != 0:
            if _is_container_down(res.returncode, res.stderr or ""):
                logger.warning(
                    "контейнер %s недоступен (rc=%d, stderr=%r)",
                    self._container.name, res.returncode, res.stderr,
                )
                self._container.mark_broken()
            return []

        refs: list[FileRef] = []
        for line in res.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            path, size_s, mtime_s = parts
            if not path or not size_s or not mtime_s:
                continue
            try:
                size = int(size_s)
                mtime = float(mtime_s)
            except ValueError:
                continue
            filename = posixpath.basename(path)
            if not filename.endswith(".jsonl"):
                continue
            dir_name = posixpath.basename(posixpath.dirname(path))
            session_id = filename[: -len(".jsonl")]
            refs.append(FileRef(
                path=path,
                dir_name=dir_name,
                session_id=session_id,
                size=size,
                mtime=mtime,
            ))
        return refs

    def read_from(self, path: str, offset: int) -> tuple[bytes, int]:
        """Прочитать хвост файла начиная с байтового смещения ``offset``.

        Использует ``tail -c +N`` (1-индексированный), поэтому смещение
        ``offset`` преобразуется в ``offset + 1``. Возвращает
        ``(data_bytes, offset + len(data_bytes))``.

        Ветки обработки:
        - ``rc == 0`` → ``(data, offset + len(data))``.
        - ``rc != 0`` и ``_is_container_down(rc, stderr)`` → ``mark_broken()``
          и ``(b"", offset)``.
        - ``rc != 0`` иначе → ``(b"", offset)`` без ``mark_broken``
          (файл исчез, смещение вне диапазона — не авария контейнера).
        - ``Exception`` → ``mark_broken()`` и ``(b"", offset)``.
        """
        cmd = ["sh", "-c", f"tail -c +{offset + 1} {shlex.quote(path)}"]
        try:
            rc, data, stderr = self._container.exec_run_bytes(cmd)
        except Exception as exc:
            logger.warning(
                "ошибка read_from %s в контейнере %s: %s",
                path, self._container.name, exc,
            )
            self._container.mark_broken()
            return b"", offset
        if rc != 0:
            if _is_container_down(rc, stderr):
                logger.warning(
                    "контейнер %s недоступен при read_from %s (rc=%d, stderr=%r)",
                    self._container.name, path, rc, stderr,
                )
                self._container.mark_broken()
            return b"", offset
        return data, offset + len(data)


class DockerBackend(Backend):
    """Бэкенд Docker: один долгоживущий контейнер на один проект.

    Контейнер живёт до явного удаления; перезапуск монитора его не трогает.
    ``key`` включает полный путь к проекту, поэтому два проекта в разных
    каталогах всегда получают разные контейнеры и разные ключи в реестре.
    """

    def __init__(
        self,
        project_path: str,
        *,
        claude_cmd: str,
        image: str = DEFAULT_IMAGE,
        workdir: str = DEFAULT_WORKDIR,
        run=subprocess.run,
        spawn_fn=pty_process.spawn,
        home: str | None = None,
    ):
        name = container_name(project_path)
        volume = f"{name}-work"
        claude_volume = f"{name}-claude"
        self.key = f"docker||{project_path}"
        self._container = _DockerContainer(
            name,
            image,
            workdir=workdir,
            volume=volume,
            claude_volume=claude_volume,
            run=run,
        )
        self.runner = DockerRunner(self._container, claude_cmd, workdir=workdir, spawn_fn=spawn_fn)
        self.files = DockerFiles(self._container, home=home)
        self.provisioner = DockerProvisioner(self._container, workdir=workdir)

    @property
    def is_broken(self) -> bool:
        """True если контейнер помечен битым."""
        return self._container.broken

    def check(self) -> None:
        """Убедиться, что контейнер запущен; бросает исключение при ошибке."""
        self._container.ensure()

    def close(self) -> None:
        """Убить все PTY-процессы агентов. Контейнер НЕ удаляется — он переживает перезапуск монитора."""
        self.runner.shutdown_all()
