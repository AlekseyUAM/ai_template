import logging
import os
import shlex
import stat
import time

from ..models import FileRef
from . import BUFFER_LIMIT, Backend

logger = logging.getLogger(__name__)

DEFAULT_PORT = 22
DEFAULT_RETRY_SECONDS = 10.0


class SshUnavailable(RuntimeError):
    """Хост недоступен: нет связи, отказ аутентификации, оборванный канал."""


def _real_connect(conn: dict):
    import paramiko

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # paramiko тильду не разворачивает, а форма ввода предлагает именно
    # "~/.ssh/id_ed25519" — без expanduser такой путь заведомо не найдётся.
    key_path = conn.get("key_path") or None
    if key_path:
        key_path = os.path.expanduser(key_path)
    client.connect(
        hostname=conn["host"],
        port=int(conn.get("port") or DEFAULT_PORT),
        username=conn.get("user") or None,
        key_filename=key_path,
        look_for_keys=True,
        allow_agent=True,
        timeout=10,
    )
    return client


class _Connection:
    """Одно SSH-соединение на хост; каналы агентов и SFTP живут поверх него."""

    def __init__(self, conn, connect_fn, clock, retry_seconds):
        self._conn = conn
        self._connect_fn = connect_fn
        self._clock = clock
        self._retry_seconds = retry_seconds
        self._client = None
        self._sftp = None
        self._broken_at = None

    def mark_broken(self):
        """Пометить соединение битым.

        Идемпотентно: если соединение уже помечено битым, отсчёт окна
        повторных попыток не перезапускается — иначе частые вызовы (например,
        из tail_output на мёртвом агенте) держали бы окно открытым вечно.
        """
        if self.broken:
            return
        self._broken_at = self._clock()
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._sftp = None

    @property
    def broken(self):
        return self._client is None and self._broken_at is not None

    def transport_alive(self) -> bool:
        """Жив ли сам транспорт соединения.

        Нужно, чтобы отличить отказ одного канала от отказа всего хоста:
        агент, вышедший секунду назад, даёт OSError на своём канале, и
        помечать по этому поводу всё соединение битым нельзя — иначе один
        мёртвый агент уносит с собой всех остальных агентов того же хоста.
        """
        client = self._client
        if client is None:
            return False
        try:
            transport = client.get_transport()
            return transport is not None and bool(transport.is_active())
        except Exception:
            return False

    def client(self):
        if self._client is not None:
            return self._client
        if self._broken_at is not None and \
                self._clock() - self._broken_at < self._retry_seconds:
            raise SshUnavailable(
                f"хост {self._conn.get('host')} недоступен, следующая попытка позже")
        try:
            self._client = self._connect_fn(self._conn)
        except Exception as exc:
            self._broken_at = self._clock()
            raise SshUnavailable(
                f"не удалось подключиться к {self._conn.get('host')}: {exc}") from exc
        self._broken_at = None
        return self._client

    def sftp(self):
        if self._sftp is None:
            try:
                self._sftp = self.client().open_sftp()
            except SshUnavailable:
                raise
            except Exception as exc:
                self.mark_broken()
                raise SshUnavailable(f"SFTP недоступен: {exc}") from exc
        return self._sftp

    def close(self):
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._sftp = None
        self._broken_at = None


class SshRunner:
    def __init__(self, connection, claude_cmd):
        self._c = connection
        self.claude_cmd = claude_cmd
        self._channels: dict[str, object] = {}
        self._buffers: dict[str, str] = {}

    def start(self, project) -> str:
        agent_id = project.key
        if self.is_alive(agent_id):
            return agent_id
        cmd = project.claude_cmd or self.claude_cmd
        try:
            chan = self._c.client().get_transport().open_session()
            chan.get_pty(term="xterm-256color", width=200, height=50)
            chan.exec_command(f"cd {shlex.quote(project.path)} && exec {cmd}")
        except SshUnavailable:
            raise
        except Exception as exc:
            self._c.mark_broken()
            raise SshUnavailable(f"не удалось запустить агента: {exc}") from exc
        self._channels[agent_id] = chan
        self._buffers[agent_id] = ""
        return agent_id

    def _require(self, agent_id):
        chan = self._channels.get(agent_id)
        if chan is None:
            raise KeyError(f"агент не запущен: {agent_id}")
        return chan

    def _forget(self, agent_id) -> None:
        """Убрать агента из обоих словарей: канал непригоден, забываем его."""
        self._channels.pop(agent_id, None)
        self._buffers.pop(agent_id, None)

    def _channel_failed(self, agent_id) -> None:
        """Канал агента отказал: забыть его, а соединение — только если оно и
        правда пропало.

        Отказ канала и отказ хоста — разные события. Пока транспорт жив,
        виноват один канал (обычно агент только что вышел), и mark_broken
        тут объявил бы мёртвыми агентов всех остальных проектов на этом
        хосте: диспетчер вернул бы их задачи в очередь и убил бы агентов.
        """
        if not self._c.transport_alive():
            self._c.mark_broken()
        self._forget(agent_id)

    def _pump(self, agent_id) -> None:
        chan = self._channels.get(agent_id)
        if chan is None:
            return
        chunks = []
        try:
            while chan.recv_ready():
                data = chan.recv(BUFFER_LIMIT)
                if not data:
                    break
                chunks.append(data)
        except Exception:
            self._channel_failed(agent_id)
            return
        if chunks:
            text = b"".join(chunks).decode("utf-8", "replace")
            self._buffers[agent_id] = (self._buffers.get(agent_id, "") + text)[-BUFFER_LIMIT:]

    def send_input(self, agent_id, text) -> None:
        chan = self._require(agent_id)
        self._pump(agent_id)
        clean = text.replace("\r", " ").replace("\n", " ")
        try:
            chan.send((clean + "\r").encode("utf-8"))
        except Exception as exc:
            self._channel_failed(agent_id)
            raise SshUnavailable(f"канал агента оборван: {exc}") from exc

    def stop(self, agent_id, mode="interrupt") -> None:
        chan = self._require(agent_id)
        try:
            if mode == "kill":
                try:
                    chan.close()
                finally:
                    # Забыть агента нужно даже если close() бросил —
                    # канал в любом случае больше не пригоден.
                    self._forget(agent_id)
            else:
                chan.send(b"\x1b")
        except Exception as exc:
            self._channel_failed(agent_id)
            raise SshUnavailable(f"канал агента оборван: {exc}") from exc

    def is_alive(self, agent_id) -> bool:
        chan = self._channels.get(agent_id)
        if chan is None:
            return False
        if self._c.broken:
            return False
        try:
            if chan.exit_status_ready():
                self._forget(agent_id)
                return False
        except Exception:
            self._channel_failed(agent_id)
            return False
        self._pump(agent_id)
        return True

    def tail_output(self, agent_id, limit=BUFFER_LIMIT) -> str:
        # Пока соединение битое, канал трогать нельзя: is_alive делает ту же
        # проверку до всякого касания канала, иначе окно повторных попыток
        # (см. _Connection.mark_broken) никогда не истекало бы при частом
        # опросе мёртвых агентов.
        if not self._c.broken:
            self._pump(agent_id)
        return self._buffers.get(agent_id, "")[-limit:]

    def shutdown_all(self) -> None:
        for agent_id, chan in list(self._channels.items()):
            try:
                chan.close()
            except Exception:
                pass
        self._channels.clear()
        self._buffers.clear()


class SshFiles:
    """Доступ к журналам сессий по SFTP.

    Домашний каталог пользователя на удалённой машине не всегда лежит по
    стандартному пути (/root или /home/<user>) — угадывать его молча
    небезопасно: промах неотличим от "сессий пока нет" (list_files тихо
    вернёт []). Поэтому при отсутствии явного home он определяется лениво,
    при первом реальном обращении, через SFTP `normalize(".")`, и
    кешируется. Неудачная попытка не кешируется, чтобы определение
    повторилось, когда связь восстановится.
    """

    def __init__(self, connection, host, home=None, guess="/root"):
        self._c = connection
        self._host = host
        self._resolved_home = home
        self._guess = guess

    def _resolve_home(self) -> str:
        if self._resolved_home is not None:
            return self._resolved_home
        try:
            real = self._c.sftp().normalize(".")
        except Exception as exc:
            logger.warning(
                "не удалось определить домашний каталог на %s: %s, "
                "использую догадку %s", self._host, exc, self._guess,
            )
            return self._guess
        self._resolved_home = real
        return real

    def home_projects_dir(self) -> str:
        try:
            home = self._resolve_home()
        except Exception:
            home = self._guess
        return f"{home.rstrip('/')}/.claude/projects"

    def list_files(self, projects_dir) -> list[FileRef]:
        try:
            sftp = self._c.sftp()
            entries = sftp.listdir_attr(projects_dir)
        except SshUnavailable:
            return []
        except FileNotFoundError:
            return []
        except Exception:
            self._c.mark_broken()
            return []

        refs = []
        for entry in entries:
            if not stat.S_ISDIR(entry.st_mode):
                continue
            sub = f"{projects_dir.rstrip('/')}/{entry.filename}"
            try:
                files = sftp.listdir_attr(sub)
            except Exception:
                continue
            for f in files:
                if stat.S_ISDIR(f.st_mode) or not f.filename.endswith(".jsonl"):
                    continue
                refs.append(FileRef(
                    path=f"{sub}/{f.filename}", dir_name=entry.filename,
                    session_id=f.filename[: -len(".jsonl")],
                    size=int(f.st_size), mtime=float(f.st_mtime),
                ))
        return refs

    def read_from(self, path, offset) -> tuple[bytes, int]:
        try:
            sftp = self._c.sftp()
            fh = sftp.open(path, "rb")
        except (SshUnavailable, FileNotFoundError, IOError):
            return b"", offset
        except Exception:
            self._c.mark_broken()
            return b"", offset
        try:
            fh.seek(offset)
            data = fh.read()
        except Exception:
            return b"", offset
        finally:
            try:
                fh.close()
            except Exception:
                pass
        return data, offset + len(data)


class SshBackend(Backend):
    def __init__(self, conn, claude_cmd, connect_fn=None, clock=time.time,
                 retry_seconds=DEFAULT_RETRY_SECONDS, home=None):
        self.conn = conn
        user = conn.get("user") or ""
        port = int(conn.get("port") or DEFAULT_PORT)
        self.key = f"ssh|{user}@{conn['host']}:{port}"
        self._connection = _Connection(conn, connect_fn or _real_connect,
                                       clock, retry_seconds)
        self.runner = SshRunner(self._connection, claude_cmd)
        guess = f"/home/{user}" if user and user != "root" else "/root"
        # home=None означает "не угадано явно" — SshFiles определит его сам
        # через SFTP normalize(".") при первом обращении; если home задан
        # явно, запроса не будет вовсе.
        self.files = SshFiles(self._connection, conn.get("host"), home=home, guess=guess)

    def mark_broken(self) -> None:
        self._connection.mark_broken()

    @property
    def is_broken(self) -> bool:
        return self._connection.broken

    def check(self) -> None:
        self._connection.client()

    def close(self) -> None:
        self.runner.shutdown_all()
        self._connection.close()
