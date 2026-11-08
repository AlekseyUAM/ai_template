"""Тесты для run.py: host_plan, ensure_host_pg.

Импорт run.py выполняется через sys.path — аналогично test_docker_create.py /
test_ssh_create.py.  run.py живёт в корне репо (ROOT), а не в src/agentmon.
"""
import subprocess
import sys
from pathlib import Path
from typing import Any

# Вставляем корень репо в путь, чтобы `import run` нашёл run.py
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import run  # noqa: E402


# ---------------------------------------------------------------------------
# host_plan
# ---------------------------------------------------------------------------


class TestHostPlan:
    def test_argv_structure_no_extra(self):
        env = {"AGENTMON_PORT": "8765"}
        argv, returned_env = run.host_plan(env, [])
        assert argv[1:] == ["-m", "agentmon"]
        assert returned_env is env

    def test_argv_structure_with_extra(self):
        env = {}
        argv, _ = run.host_plan(env, ["--debug", "--port", "9000"])
        assert argv[1:] == ["-m", "agentmon", "--debug", "--port", "9000"]

    def test_argv_first_element_is_venv_python(self):
        argv, _ = run.host_plan({}, [])
        assert argv[0] == str(run.venv_python())

    def test_env_returned_as_is(self):
        env = {"KEY": "val"}
        _, returned_env = run.host_plan(env, [])
        assert returned_env is env  # тот же объект, без копирования


# ---------------------------------------------------------------------------
# ensure_host_pg
# ---------------------------------------------------------------------------

class _FakeRun:
    """Минимальный фейк subprocess.run для тестов ensure_host_pg."""

    def __init__(self, rc: int = 0):
        self.calls: list[list[str]] = []
        self._rc = rc

    def __call__(self, cmd, **kwargs) -> Any:
        self.calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, self._rc, stdout=b"", stderr=b"")

    def call_count(self) -> int:
        return len(self.calls)


class TestEnsureHostPg:
    """Тесты ensure_host_pg — без реального PostgreSQL."""

    def _make_datadir(self, tmp_path: Path) -> Path:
        """Создать минимальный datadir с ai1c.port."""
        datadir = tmp_path / ".ai1c" / "pgdata"
        datadir.mkdir(parents=True)
        (datadir / "ai1c.port").write_text("5555")
        return datadir

    def _patch_root(self, monkeypatch, tmp_path: Path) -> None:
        """Переключить run.ROOT и pg_portable.paths() на tmp_path."""
        import pg_portable as pg
        monkeypatch.setattr(run, "ROOT", tmp_path)

        # Переопределяем _pg_portable в модуле run так, чтобы paths() читал tmp_path
        original_paths = pg.paths

        def _patched_paths(root):
            return original_paths(tmp_path)

        monkeypatch.setattr(run._pg_portable, "paths", _patched_paths)

    # ------------------------------------------------------------------
    # pg_mode=host + datadir есть + PG не запущена → start вызван
    # ------------------------------------------------------------------

    def test_host_pg_not_running_calls_start(self, tmp_path, monkeypatch):
        """AI1C_PG_MODE=host, datadir существует, status=False → start вызывается."""
        self._make_datadir(tmp_path)
        self._patch_root(monkeypatch, tmp_path)

        # status возвращает False (rc=1), start — True (rc=0)
        call_log: list[tuple[str, list]] = []

        def fake_run(cmd, **kwargs):
            call_log.append(("run", list(cmd)))
            # первый вызов — status (pg_ctl status) → rc=1 (не запущен)
            # второй вызов — start (pg_ctl start) → rc=0
            rc = 1 if len(call_log) == 1 else 0
            return subprocess.CompletedProcess(cmd, rc, stdout=b"", stderr=b"")

        run.ensure_host_pg({"AI1C_PG_MODE": "host"}, run=fake_run)

        assert len(call_log) == 2, f"Ожидали 2 вызова (status+start), получили: {call_log}"
        # Второй вызов — start
        start_argv = call_log[1][1]
        assert "start" in start_argv
        # порт из ai1c.port = 5555
        assert any("5555" in a for a in start_argv), f"Порт 5555 не найден в argv: {start_argv}"

    # ------------------------------------------------------------------
    # status True → start NOT called
    # ------------------------------------------------------------------

    def test_host_pg_already_running_no_start(self, tmp_path, monkeypatch):
        """AI1C_PG_MODE=host, PG уже запущена (status=True) → start НЕ вызывается."""
        self._make_datadir(tmp_path)
        self._patch_root(monkeypatch, tmp_path)

        fake = _FakeRun(rc=0)  # status → rc=0 → уже запущена
        run.ensure_host_pg({}, run=fake)

        assert fake.call_count() == 1  # только status
        assert "start" not in fake.calls[0]

    # ------------------------------------------------------------------
    # AI1C_PG_MODE=docker → no-op
    # ------------------------------------------------------------------

    def test_docker_pg_mode_noop(self, tmp_path, monkeypatch):
        """AI1C_PG_MODE=docker → status/start не вызываются."""
        self._make_datadir(tmp_path)
        self._patch_root(monkeypatch, tmp_path)

        fake = _FakeRun(rc=0)
        run.ensure_host_pg({"AI1C_PG_MODE": "docker"}, run=fake)

        assert fake.call_count() == 0

    # ------------------------------------------------------------------
    # datadir absent → no-op
    # ------------------------------------------------------------------

    def test_no_datadir_noop(self, tmp_path, monkeypatch):
        """Если datadir не существует — status/start не вызываются."""
        # НЕ создаём datadir
        monkeypatch.setattr(run, "ROOT", tmp_path)
        import pg_portable as pg
        original_paths = pg.paths

        def _patched_paths(root):
            return original_paths(tmp_path)

        monkeypatch.setattr(run._pg_portable, "paths", _patched_paths)

        fake = _FakeRun(rc=0)
        run.ensure_host_pg({}, run=fake)

        assert fake.call_count() == 0

    # ------------------------------------------------------------------
    # start raises → no exception propagates (warning in stderr)
    # ------------------------------------------------------------------

    def test_start_failure_does_not_propagate(self, tmp_path, monkeypatch, capsys):
        """Если start поднимает исключение — оно НЕ прокидывается, WARNING в stderr."""
        self._make_datadir(tmp_path)
        self._patch_root(monkeypatch, tmp_path)

        call_count = [0]

        def fake_run_raises(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # status → rc=1 (не запущена)
                return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"")
            # start → raise
            raise subprocess.CalledProcessError(1, cmd, stderr=b"pg_ctl error")

        # Не должно поднять исключение
        run.ensure_host_pg({}, run=fake_run_raises)

        captured = capsys.readouterr()
        assert "WARNING" in captured.err

    # ------------------------------------------------------------------
    # AI1C_PG_MODE отсутствует → трактуется как host → обрабатывается
    # ------------------------------------------------------------------

    def test_default_pg_mode_is_host(self, tmp_path, monkeypatch):
        """Если AI1C_PG_MODE не задан — дефолт host → обрабатываем."""
        self._make_datadir(tmp_path)
        self._patch_root(monkeypatch, tmp_path)

        call_log: list = []

        def fake_run(cmd, **kwargs):
            call_log.append(list(cmd))
            rc = 1 if len(call_log) == 1 else 0
            return subprocess.CompletedProcess(cmd, rc, stdout=b"", stderr=b"")

        run.ensure_host_pg({}, run=fake_run)  # env без AI1C_PG_MODE

        assert len(call_log) >= 1  # хотя бы status был вызван
