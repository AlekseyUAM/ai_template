import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..models import FileRef
from ..pty_process import spawn as default_spawn
from . import BUFFER_LIMIT, Backend, RunResult

logger = logging.getLogger(__name__)


class LocalProvisioner:
    """Provisioner для той же машины: прямые Path/shutil/subprocess-операции.

    Поведение повторяет прежний код слоя env/ (scaffold/content/checks) —
    рефакторинг не должен менять результат для backend=local.
    """

    _CRUFT_DIRS = {"__pycache__", "build", ".pytest_cache"}

    def mkdirs(self, paths) -> None:
        for p in paths:
            Path(p).mkdir(parents=True, exist_ok=True)

    def exists(self, path) -> bool:
        return Path(path).exists()

    def is_empty_dir(self, path) -> bool:
        if not path:
            return False
        p = Path(path)
        if not p.exists():
            return True
        if not p.is_dir():
            return False
        return not any(p.iterdir())

    def read_text(self, path) -> str:
        return Path(path).read_text(encoding="utf-8")

    def write_text(self, path, content) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    def write_bytes(self, path, data) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)

    def _is_cruft(self, item: Path) -> bool:
        return any(p in self._CRUFT_DIRS or p.endswith(".egg-info")
                   for p in item.parts)

    def put_tree(self, local_src, dst, skip=None) -> None:
        src, dstp = Path(local_src), Path(dst)
        for item in sorted(src.rglob("*")):
            if self._is_cruft(item):
                continue
            rel = item.relative_to(src)
            if skip is not None and skip(rel):
                continue
            target = dstp / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.read_bytes())

    def run(self, cmd, cwd=None) -> RunResult:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    def which(self, tool) -> str | None:
        return shutil.which(tool)

    def python_cmd(self):
        return [sys.executable]

    def venv_python(self, project_dir) -> str:
        base = Path(project_dir) / ".venv"
        if os.name == "nt":
            return str(base / "Scripts" / "python.exe")
        return str(base / "bin" / "python")


class LocalRunner:
    """Агенты — процессы в PTY внутри процесса монитора."""

    def __init__(self, claude_cmd, spawn_fn=default_spawn):
        self.claude_cmd = claude_cmd
        self._spawn = spawn_fn
        self._procs: dict[str, object] = {}
        self._buffers: dict[str, str] = {}

    def start(self, project) -> str:
        agent_id = project.key
        proc = self._procs.get(agent_id)
        if proc is not None and proc.alive:
            return agent_id
        cmd = project.claude_cmd or self.claude_cmd
        self._procs[agent_id] = self._spawn(cmd, project.path)
        self._buffers[agent_id] = ""
        return agent_id

    def _pump(self, agent_id) -> None:
        proc = self._procs.get(agent_id)
        if proc is None:
            return
        chunk = proc.read_available()
        if chunk:
            buf = self._buffers.get(agent_id, "") + chunk
            self._buffers[agent_id] = buf[-BUFFER_LIMIT:]

    def _require(self, agent_id):
        proc = self._procs.get(agent_id)
        if proc is None:
            raise KeyError(f"агент не запущен: {agent_id}")
        return proc

    def send_input(self, agent_id, text) -> None:
        proc = self._require(agent_id)
        self._pump(agent_id)
        # Переводы строк отправили бы ввод раньше времени — схлопываем в пробел.
        clean = text.replace("\r", " ").replace("\n", " ")
        proc.write(clean + "\r")

    def stop(self, agent_id, mode="interrupt") -> None:
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

    def is_alive(self, agent_id) -> bool:
        proc = self._procs.get(agent_id)
        if proc is None:
            return False
        self._pump(agent_id)
        if not proc.alive:
            self._procs.pop(agent_id, None)
            return False
        return True

    def tail_output(self, agent_id, limit=BUFFER_LIMIT) -> str:
        self._pump(agent_id)
        return self._buffers.get(agent_id, "")[-limit:]

    def shutdown_all(self) -> None:
        for agent_id in list(self._procs):
            try:
                self._procs[agent_id].kill()
            except Exception:
                pass
        self._procs.clear()
        self._buffers.clear()


class LocalFiles:
    """Журналы сессий на той же машине — обычная файловая система."""

    def __init__(self, home=None):
        self._home = home or os.path.expanduser("~")

    def home_projects_dir(self) -> str:
        return os.path.join(self._home, ".claude", "projects")

    def list_files(self, projects_dir) -> list[FileRef]:
        refs = []
        if not os.path.isdir(projects_dir):
            return refs
        for entry in os.scandir(projects_dir):
            if not entry.is_dir():
                continue
            try:
                inner = os.scandir(entry.path)
            except OSError as exc:
                # Каталог сессии мог быть удалён в середине обхода — пропускаем
                # его, не роняя обновление всего бэкенда на этом тике.
                logger.warning(
                    "не удалось прочитать каталог сессий %s: %s",
                    entry.path, exc,
                )
                continue
            for f in inner:
                if not f.is_file() or not f.name.endswith(".jsonl"):
                    continue
                try:
                    st = f.stat()
                except OSError as exc:
                    logger.warning(
                        "не удалось получить метаданные файла %s: %s",
                        f.path, exc,
                    )
                    continue
                refs.append(FileRef(
                    path=f.path, dir_name=entry.name,
                    session_id=f.name[: -len(".jsonl")],
                    size=st.st_size, mtime=st.st_mtime,
                ))
        return refs

    def read_from(self, path, offset) -> tuple[bytes, int]:
        try:
            with open(path, "rb") as fh:
                fh.seek(offset)
                data = fh.read()
                return data, offset + len(data)
        except (OSError, ValueError) as exc:
            logger.warning(
                "не удалось прочитать файл %s со смещения %d: %s",
                path, offset, exc,
            )
            return b"", offset


class LocalBackend(Backend):
    key = "local"

    def __init__(self, claude_cmd, spawn_fn=default_spawn, home=None):
        self.runner = LocalRunner(claude_cmd, spawn_fn=spawn_fn)
        self.files = LocalFiles(home=home)
        self.provisioner = LocalProvisioner()

    def check(self) -> None:
        return None
