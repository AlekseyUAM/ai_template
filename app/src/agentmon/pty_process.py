"""Интерактивный процесс в псевдотерминале.

Монитор сам держит агента, без внешнего мультиплексора терминала. Две
реализации с одним интерфейсом — POSIX через stdlib pty, Windows через
pywinpty (ConPTY).
"""

import os
import select
import shlex
import sys

ESC = "\x1b"
READ_CHUNK = 65536


class _PosixPty:
    def __init__(self, cmd, cwd, env=None):
        import pty
        import signal
        import subprocess

        self._signal = signal
        self._subprocess = subprocess
        if not os.path.isdir(cwd):
            raise FileNotFoundError(f"каталог проекта не найден: {cwd}")
        master, slave = pty.openpty()
        try:
            try:
                self._proc = subprocess.Popen(
                    shlex.split(cmd), cwd=cwd, env=env or os.environ.copy(),
                    stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True, close_fds=True,
                )
            except BaseException:
                # Popen упал (нет такой команды, нет прав) — объекта, который
                # закрыл бы master, не появится вовсе, и дескриптор утёк бы.
                # Диспетчер повторяет неудачный старт, так что утечка копится.
                os.close(master)
                raise
        finally:
            os.close(slave)
        self._master = master
        self._master_closed = False
        os.set_blocking(self._master, False)

    def write(self, text):
        os.write(self._master, text.encode("utf-8"))

    def read_available(self):
        chunks = []
        while True:
            try:
                data = os.read(self._master, READ_CHUNK)
            except BlockingIOError:
                break
            except OSError:
                break
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks).decode("utf-8", "replace")

    def _close_master(self):
        # Идемпотентно: закрываем master-дескриптор один раз, повторные
        # вызовы (и гонки с естественным завершением) молча игнорируем.
        if self._master_closed:
            return
        self._master_closed = True
        try:
            os.close(self._master)
        except OSError:
            pass

    def _reap(self, timeout=0.0):
        # Забираем код возврата, чтобы ребёнок не оставался зомби в таблице
        # процессов. Без таймаута — неблокирующий poll(); с таймаутом — ждём,
        # но не дольше отведённого времени, чтобы не подвесить монитор.
        if self._proc.poll() is not None:
            return
        if timeout > 0:
            try:
                self._proc.wait(timeout)
            except self._subprocess.TimeoutExpired:
                pass

    @property
    def alive(self):
        is_alive = self._proc.poll() is None
        if not is_alive:
            # Процесс уже мёртв — закрываем master и на пути естественного
            # завершения, а не только после explicit kill().
            self._close_master()
        return is_alive

    def interrupt(self):
        self.write(ESC)

    def _signal_group(self, sig):
        try:
            os.killpg(os.getpgid(self._proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    def terminate(self):
        self._signal_group(self._signal.SIGTERM)
        # Ребёнок может ещё дожидать SIGTERM — не блокируемся на нём.
        # Дескриптор не закрываем: он может ещё что-то дописывать;
        # закроет его alive, когда увидит смерть процесса.
        self._reap()

    def kill(self):
        self._signal_group(self._signal.SIGKILL)
        # SIGKILL перехватить нельзя — смерть почти мгновенна, короткое
        # ожидание безопасно и гарантирует реапинг здесь и сейчас.
        self._reap(timeout=2.0)
        self._close_master()


class _WinPty:
    def __init__(self, cmd, cwd, env=None):
        try:
            import winpty
        except ImportError as exc:                     # pragma: no cover
            raise RuntimeError(
                "на Windows нужен пакет pywinpty: pip install pywinpty"
            ) from exc
        if not os.path.isdir(cwd):
            raise FileNotFoundError(f"каталог проекта не найден: {cwd}")
        self._pty = winpty.PtyProcess.spawn(cmd, cwd=cwd, env=env)

    def write(self, text):
        self._pty.write(text)

    def read_available(self):
        # winpty.PtyProcess.read — это def read(self, size=1024): kwarg
        # blocking принимает только низкоуровневый winpty.PTY.read, и
        # передача его сюда роняла TypeError на первом же опросе агента
        # (проверено по исходникам pywinpty 2.0.0, 2.0.7, 2.0.15 и 3.0.5).
        #
        # Неблокирующего чтения высокоуровневый API не предлагает вовсе:
        # read() делает recv на сокете, через который внутренний поток
        # отдаёт вывод ConPTY, и ждёт данных. Поэтому спрашиваем готовность
        # сокета публичным fileno() и читаем, только когда данные есть.
        chunks = []
        while True:
            try:
                ready, _, _ = select.select([self._pty.fileno()], [], [], 0)
            except (OSError, ValueError):
                break
            if not ready:
                break
            try:
                data = self._pty.read(READ_CHUNK)
            except (EOFError, OSError):
                break
            if not data:
                break
            chunks.append(data)
        return "".join(chunks)

    @property
    def alive(self):
        return bool(self._pty.isalive())

    def interrupt(self):
        self.write(ESC)

    def terminate(self):
        self._pty.terminate(force=False)

    def kill(self):
        self._pty.terminate(force=True)


def spawn(cmd: str, cwd: str, env: dict | None = None):
    """Запустить команду в псевдотерминале в каталоге cwd."""
    impl = _WinPty if sys.platform == "win32" else _PosixPty
    return impl(cmd, cwd, env)
