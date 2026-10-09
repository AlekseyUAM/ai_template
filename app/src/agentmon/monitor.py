"""Монитор detached-агентов.

Агент запускается отдельным процессом (`runner`), его прогон фиксируется в
`store` (таблица runs). Слежение — по PID (жив/мёртв) и коду выхода; метрики
(модель, токены, фаза) берутся из JSONL-журналов `claude` через наблюдателя.
Детач-модель переживает перезапуск монитора: прогоны лежат в БД, а процессы
агентов монитору не принадлежат.

`store`/`runner` необязательны: без `store` управление агентами выключено
(is_alive → False, sessions → []), что удобно в тестах, конструирующих монитор
только ради HTTP-ручек.
"""

import logging
import os
import shlex
import threading
import time
import uuid
from pathlib import Path

from . import config
from . import runner_detached
from .observer import Observer

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, registry, backends, store=None, runner=None,
                 generating_window=config.GENERATING_WINDOW, now_fn=time.time,
                 claude_cmd=config.CLAUDE_CMD):
        self.registry = registry
        self.backends = backends
        self.store = store
        self.runner = runner if runner is not None else runner_detached
        self.generating_window = generating_window
        self.now_fn = now_fn
        self.claude_cmd = claude_cmd
        self._observers: dict[str, Observer] = {}
        self._errors: dict[str, str] = {}
        self._backend_errors: dict[str, str] = {}
        # Наблюдение — чтение-изменение-запись курсоров журналов из нескольких
        # мест (тик диспетчера, push сессий). Блокировка на весь цикл; RLock,
        # т.к. sessions() вызывает refresh().
        self._lock = threading.RLock()

    # ── наблюдатель/файлы ─────────────────────────────────────────────────────
    def _observer(self, project) -> Observer:
        key = self.backends.key_for(project)
        backend = self.backends.get(project)
        obs = self._observers.get(key)
        if obs is None or obs.files is not backend.files:
            obs = Observer(backend.files, generating_window=self.generating_window)
            self._observers[key] = obs
        return obs

    def _ok(self, project):
        self._errors.pop(project.key, None)

    def _fail(self, project, exc):
        self._errors[project.key] = str(exc)

    def last_error(self, project) -> str | None:
        err = self._errors.get(project.key)
        if err:
            return err
        try:
            return self._backend_errors.get(self.backends.key_for(project))
        except ValueError:
            return None

    def forget(self, project) -> None:
        self._errors.pop(project.key, None)

    def backend_key(self, project) -> str | None:
        try:
            return self.backends.key_for(project)
        except ValueError:
            return None

    def invalidate_backend(self, project) -> None:
        try:
            key = self.backends.key_for(project)
        except ValueError:
            return
        self.backends.invalidate(key)
        with self._lock:
            self._observers.pop(key, None)
        self._backend_errors.pop(key, None)

    def release_backend(self, project) -> None:
        key = self.backend_key(project)
        if key is None:
            return
        for other in self.registry.list():
            if self.backend_key(other) == key:
                return
        self.invalidate_backend(project)

    # ── запуск/слежение агента ────────────────────────────────────────────────
    def _cmd_for(self, project, prompt) -> list:
        cmd = project.claude_cmd or self.claude_cmd
        # shlex корректно разбивает аргументы/пути с пробелами (naive .split()
        # их ломал); posix=False на Windows — чтобы не съедать бэкслеши путей.
        base = shlex.split(cmd, posix=(os.name != "nt"))
        if base and base[-1] == ".":
            base = base[:-1]          # хвостовой "." — аргумент интерактивного режима
        return base + ["-p", prompt]

    def _run_paths(self, project):
        token = uuid.uuid4().hex
        d = Path(project.path) / ".agentmon" / "runs"
        return str(d / f"{token}.log"), str(d / f"{token}.exit")

    def start(self, project, prompt="", task_id=None, cmd=None) -> str:
        """Запустить агента отдельным процессом (`claude -p "<prompt>"`).

        Если `cmd` передан явно — запускает эту команду напрямую; иначе строит
        команду через `_cmd_for(project, prompt)`.
        """
        if self.store is None:
            raise RuntimeError("store не сконфигурирован: запуск агентов недоступен")
        try:
            log_file, exit_file = self._run_paths(project)
            actual_cmd = cmd if cmd is not None else self._cmd_for(project, prompt)
            pid = self.runner.launch(actual_cmd,
                                     cwd=project.path, log_file=log_file,
                                     exit_file=exit_file)
        except Exception as exc:
            self._fail(project, exc)
            raise
        try:
            run_id = self.store.add(project.id, pid, task_id=task_id,
                                    log_file=log_file, exit_file=exit_file)
        except Exception as exc:
            try:
                self.runner.terminate(pid)
            except Exception:
                pass
            self._fail(project, exc)
            raise
        self._ok(project)
        return str(run_id)

    def stop(self, project, mode="interrupt") -> None:
        if self.store is None:
            return
        try:
            for run in self.store.running(project.id):
                self.runner.terminate(run["pid"])
                self.store.finish(run["id"], "failed")
        except Exception as exc:
            self._fail(project, exc)
            raise
        self._ok(project)

    def is_alive(self, project) -> bool:
        if self.store is None:
            return False
        try:
            return any(self.runner.is_running(r["pid"])
                       for r in self.store.running(project.id))
        except Exception as exc:
            self._fail(project, exc)
            return False

    def _read_exit(self, exit_file):
        if not exit_file:
            return None
        try:
            return int(Path(exit_file).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def reconcile(self) -> None:
        """Довести до финала прогоны, чьи процессы завершились."""
        if self.store is None:
            return
        for run in self.store.running():
            if self.runner.is_running(run["pid"]):
                continue
            code = self._read_exit(run.get("exit_file"))
            self.store.finish(run["id"], "done" if code == 0 else "failed",
                              exit_code=code)

    def enforce_timeout(self, task_id, max_minutes) -> bool:
        """Жёсткий таймаут: если последний прогон задачи выполняется дольше
        max_minutes, снять его процесс (SIGTERM→SIGKILL в runner) и пометить
        прогон failed. Возвращает True, если прогон был прерван.

        Опирается на wall-clock started_at прогона и now_fn монитора — проверка
        переживает перезапуск монитора (started_at лежит в БД). Идемпотентна:
        для уже завершённого прогона возвращает False.
        """
        if self.store is None or not max_minutes:
            return False
        run = self.store.latest_for_task(task_id)
        if run is None or run["status"] != "running":
            return False
        started = run.get("started_at")
        if started is None:
            return False
        if self.now_fn() - started <= max_minutes * 60:
            return False
        # Превышен лимит: снимаем процесс и фиксируем провал даже если
        # terminate бросит — прогон не должен остаться «вечно running».
        try:
            self.runner.terminate(run["pid"])
        finally:
            self.store.finish(run["id"], "failed")
        logger.warning("задача id=%s прервана по таймауту (%s мин)",
                       task_id, max_minutes)
        return True

    def task_status(self, task_id) -> str | None:
        """Статус последнего прогона задачи: running|done|failed|None."""
        if self.store is None:
            return None
        run = self.store.latest_for_task(task_id)
        if run is None:
            return None
        if run["status"] == "running":
            return "running"
        return run["status"]

    def check(self, project) -> None:
        try:
            self.backends.get(project).check()
        except Exception as exc:
            self._fail(project, exc)
            raise
        self._ok(project)

    def capture(self, project) -> str:
        if self.store is None:
            return ""
        runs = self.store.running(project.id)
        if not runs:
            return ""
        log_file = runs[-1].get("log_file")
        if not log_file:
            return ""
        try:
            return Path(log_file).read_text(encoding="utf-8", errors="replace")[-65536:]
        except OSError:
            return ""

    # ── наблюдение ──────────────────────────────────────────────────────────
    def _refresh_backend(self, project, key) -> str | None:
        try:
            self._observer(project).refresh()
        except Exception as exc:
            logger.warning("refresh бэкенда %s не удался: %s", key, exc)
            return str(exc)
        try:
            broken = self.backends.get(project).is_broken
        except Exception:
            broken = False
        if broken:
            host = project.host or key
            logger.warning("нет связи с хостом %s", host)
            return (f"нет связи с хостом {host}: журналы и агенты недоступны, "
                    f"проверьте доступность машины")
        return None

    def refresh(self) -> None:
        with self._lock:
            self.reconcile()
            checked: dict[str, str | None] = {}
            for project in self.registry.list():
                try:
                    key = self.backends.key_for(project)
                except ValueError as exc:
                    self._fail(project, exc)
                    continue
                if key not in checked:
                    checked[key] = self._refresh_backend(project, key)
                error = checked[key]
                if error is None:
                    self._backend_errors.pop(key, None)
                else:
                    self._backend_errors[key] = error

    def state(self, project) -> str | None:
        with self._lock:
            try:
                return self._observer(project).state(project.path, self.now_fn())
            except Exception as exc:
                self._fail(project, exc)
                return None

    def transcript(self, project) -> list[dict]:
        with self._lock:
            try:
                return self._observer(project).transcript(project.path)
            except Exception as exc:
                self._fail(project, exc)
                return []

    def sessions(self) -> list[dict]:
        """Живые агенты и только они: прогон с мёртвым PID агентом не считается."""
        with self._lock:
            return self._sessions()

    def _sessions(self) -> list[dict]:
        self.refresh()
        if self.store is None:
            return []
        now = self.now_fn()
        live_projects = set()
        for run in self.store.running():
            if self.runner.is_running(run["pid"]):
                live_projects.add(run["project_id"])
        out = []
        for project in self.registry.list():
            if project.id not in live_projects:
                continue
            try:
                snap = self._observer(project).snapshot(project.path, now)
            except Exception as exc:
                self._fail(project, exc)
                snap = None
            row = {
                "project_id": project.id,
                "name": project.name,
                "project_path": project.path,
                "backend": project.backend,
                "host": project.host,
                "session_id": None,
                "model": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "cost_usd": 0.0,
                "last_activity": 0.0,
                "state": "idle",
                "current_phase": None,
            }
            if snap is not None:
                row.update({
                    "session_id": snap.session_id,
                    "model": snap.model,
                    "input_tokens": snap.input_tokens,
                    "output_tokens": snap.output_tokens,
                    "cache_read_tokens": snap.cache_read_tokens,
                    "cache_creation_tokens": snap.cache_creation_tokens,
                    "cost_usd": snap.cost_usd,
                    "last_activity": snap.last_activity,
                    "state": snap.state,
                    "current_phase": snap.current_phase,
                })
            out.append(row)
        out.sort(key=lambda r: r["last_activity"], reverse=True)
        return out

    def shutdown(self) -> None:
        # Detached-агенты монитору не принадлежат и переживают его остановку —
        # их НЕ убиваем. Закрываем только файловые бэкенды/наблюдатели.
        self.backends.close_all()
        self._observers.clear()
