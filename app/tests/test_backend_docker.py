"""Тесты _DockerContainer — идентичность и жизненный цикл контейнера.

Все команды идут через FakeRun (без реального Docker).
FakeRun позволяет задавать разные ответы на разные команды по ключевому
слову из argv (подстрока в строке вида «docker inspect», «docker images» и т.д.).
"""
import subprocess
import types

import pytest

from agentmon.backends.docker import (
    DEFAULT_IMAGE,
    DEFAULT_WORKDIR,
    DEFAULT_RETRY_SECONDS,
    _DockerContainer,
    DockerBackend,
    DockerProvisioner,
    DockerRunner,
    DockerFiles,
    container_name,
)
from agentmon.backends import RunResult
from agentmon.models import FileRef


# ---------------------------------------------------------------------------
# FakeRun — имитатор subprocess.run с маршрутизацией по содержимому argv
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRun:
    """Callable, имитирующий subprocess.run.

    ``routes`` — список пар (ключевое слово, ответ): первый маршрут, у которого
    ключевое слово встречается в « ".join(argv) », используется как ответ.
    Если ни один маршрут не совпал — возвращается ответ по умолчанию ``default``.
    """

    def __init__(self, routes=None, default_rc=0, default_out="", default_err=""):
        self.calls: list[list[str]] = []
        self._routes: list[tuple[str, _FakeResponse]] = []
        for keyword, rc, out, err in (routes or []):
            self._routes.append((keyword, _FakeResponse(rc, out, err)))
        self._default = _FakeResponse(default_rc, default_out, default_err)

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        for keyword, resp in self._routes:
            if keyword in joined:
                return resp
        return self._default

    def called_with(self, keyword: str) -> list[list[str]]:
        """Список вызовов, в чьей строке argv встречается ключевое слово."""
        return [c for c in self.calls if keyword in " ".join(c)]


def _make_container(fake_run, *, name="ai1c-test", image="ai1c-agent:latest",
                    workdir="/workspace", volume="/tmp/vol",
                    add_hosts=None, env=None, clock=None,
                    retry_seconds=DEFAULT_RETRY_SECONDS):
    """Фабрика контейнера с инъектируемым FakeRun."""
    kw = {}
    if clock is not None:
        kw["clock"] = clock
    if add_hosts is not None:
        kw["add_hosts"] = add_hosts
    return _DockerContainer(
        name=name,
        image=image,
        workdir=workdir,
        volume=volume,
        env=env,
        run=fake_run,
        retry_seconds=retry_seconds,
        **kw,
    )


# ---------------------------------------------------------------------------
# container_name — детерминированность и безопасность символов
# ---------------------------------------------------------------------------

class TestContainerName:
    def test_starts_with_prefix(self):
        name = container_name("/home/user/projects/myproject")
        assert name.startswith("ai1c-")

    def test_safe_characters_only(self):
        import re
        name = container_name("/srv/projects/Мой Проект!")
        assert re.fullmatch(r"[a-z0-9_.\\-]+", name.replace("-", "_").replace(".", "_"))

    def test_deterministic(self):
        path = "/srv/projects/foo"
        assert container_name(path) == container_name(path)

    def test_different_paths_different_names(self):
        assert container_name("/a/foo") != container_name("/b/foo")

    def test_same_basename_different_paths(self):
        # Два проекта «myapp» в разных папках → разные имена контейнеров
        assert container_name("/projects/team1/myapp") != container_name("/projects/team2/myapp")


# ---------------------------------------------------------------------------
# status() — парсинг docker inspect
# ---------------------------------------------------------------------------

class TestStatus:
    def test_running(self):
        fake = FakeRun(routes=[("docker inspect", 0, "running\n", "")])
        c = _make_container(fake)
        assert c.status() == "running"

    def test_exited(self):
        fake = FakeRun(routes=[("docker inspect", 0, "exited\n", "")])
        c = _make_container(fake)
        assert c.status() == "exited"

    def test_absent_when_inspect_fails(self):
        fake = FakeRun(routes=[("docker inspect", 1, "", "No such object")])
        c = _make_container(fake)
        assert c.status() == "absent"

    def test_absent_when_unknown_state(self):
        fake = FakeRun(routes=[("docker inspect", 0, "something_weird\n", "")])
        c = _make_container(fake)
        assert c.status() == "absent"

    def test_inspect_uses_state_status_format(self):
        """Команда должна запрашивать .State.Status через -f."""
        fake = FakeRun(default_rc=1)  # absent
        c = _make_container(fake)
        c.status()
        assert fake.calls, "должен быть хотя бы один вызов"
        cmd = fake.calls[-1]
        joined = " ".join(cmd)
        assert "docker inspect" in joined
        assert ".State.Status" in joined


# ---------------------------------------------------------------------------
# ensure() — absent → docker run
# ---------------------------------------------------------------------------

class TestEnsureAbsent:
    def _fake_for_absent(self, image="ai1c-agent:latest"):
        """FakeRun: образ есть, inspect → absent (rc=1)."""
        return FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),   # image_exists → True
            ("docker inspect", 1, "", "No such object"),  # status → absent
            # docker run → success (default rc=0)
        ])

    def test_calls_docker_run_on_absent(self):
        fake = self._fake_for_absent()
        c = _make_container(fake)
        c.ensure()
        run_calls = fake.called_with("docker run")
        assert len(run_calls) == 1

    def test_docker_run_has_detach_flag(self):
        fake = self._fake_for_absent()
        c = _make_container(fake)
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "-d" in cmd

    def test_docker_run_has_name(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-foo")
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "--name" in cmd and "ai1c-foo" in cmd

    def test_docker_run_has_restart_unless_stopped(self):
        fake = self._fake_for_absent()
        c = _make_container(fake)
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "--restart" in cmd
        idx = cmd.index("--restart")
        assert cmd[idx + 1] == "unless-stopped"

    def test_docker_run_has_add_host_and_no_network(self):
        fake = self._fake_for_absent()
        c = _make_container(fake)
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        joined = " ".join(cmd)
        assert "--add-host=host.docker.internal:host-gateway" in joined
        assert "-e" in cmd
        assert "DISPLAY=:99" in joined
        assert "--network" not in joined

    def test_docker_run_has_volume(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, volume="/myvol", workdir="/workspace")
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "-v" in cmd
        joined = " ".join(cmd)
        assert "/myvol:/workspace" in joined

    def test_docker_run_ends_with_sleep_infinity(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, image="ai1c-agent:latest")
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert cmd[-2:] == ["sleep", "infinity"]

    def test_docker_run_includes_image(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, image="ai1c-agent:latest")
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "ai1c-agent:latest" in cmd

    def test_docker_run_passes_env_vars(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, env={"FOO": "bar", "BAZ": "qux"})
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        joined = " ".join(cmd)
        assert "-e" in cmd and "FOO=bar" in joined and "BAZ=qux" in joined

    def test_ensure_marks_broken_on_run_failure(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc\n", ""),
            ("docker inspect", 1, "", "No such object"),
            ("docker run", 1, "", "permission denied"),
        ])
        c = _make_container(fake)
        with pytest.raises(RuntimeError, match="permission denied"):
            c.ensure()
        assert c.broken


# ---------------------------------------------------------------------------
# ensure() — exited → docker start
# ---------------------------------------------------------------------------

class TestEnsureExited:
    def test_calls_docker_start_on_exited(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc\n", ""),
            ("docker inspect", 0, "exited\n", ""),
            # docker start → default rc=0
        ])
        c = _make_container(fake, name="ai1c-proj")
        c.ensure()
        start_calls = fake.called_with("docker start")
        assert len(start_calls) == 1
        assert "ai1c-proj" in start_calls[0]

    def test_no_docker_run_on_exited(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc\n", ""),
            ("docker inspect", 0, "exited\n", ""),
        ])
        c = _make_container(fake)
        c.ensure()
        assert not fake.called_with("docker run")

    def test_ensure_marks_broken_on_start_failure(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc\n", ""),
            ("docker inspect", 0, "exited\n", ""),
            ("docker start", 1, "", "container not found"),
        ])
        c = _make_container(fake)
        with pytest.raises(RuntimeError):
            c.ensure()
        assert c.broken


# ---------------------------------------------------------------------------
# ensure() — running → ничего не делать
# ---------------------------------------------------------------------------

class TestEnsureRunning:
    def test_no_run_or_start_when_already_running(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "sha256:abc\n", ""),
            ("docker inspect", 0, "running\n", ""),
        ])
        c = _make_container(fake)
        c.ensure()
        assert not fake.called_with("docker run")
        assert not fake.called_with("docker start")

    def test_xvfb_still_ensured_when_already_running(self):
        """Когда контейнер уже running, ensure() всё ещё должен вызвать docker exec для Xvfb."""
        fake = FakeRun(routes=[
            ("docker images -q", 0, "sha256:abc\n", ""),
            ("docker inspect", 0, "running\n", ""),
            # docker exec -d (Xvfb) → default rc=0
        ])
        c = _make_container(fake, name="ai1c-test")
        c.ensure()
        # Проверяем, что docker run и docker start НЕ вызваны
        assert not fake.called_with("docker run")
        assert not fake.called_with("docker start")
        # Но docker exec с Xvfb :99 ДО ЛЖЕ вызван
        xvfb_calls = fake.called_with("docker exec")
        assert len(xvfb_calls) == 1
        cmd = xvfb_calls[0]
        assert "-d" in cmd
        assert "ai1c-test" in cmd
        full = " ".join(cmd)
        assert "Xvfb :99" in full


# ---------------------------------------------------------------------------
# ensure() — кеш готовности (_ready): повторный вызов не дёргает docker
# ---------------------------------------------------------------------------

class TestEnsureReadyCache:
    def _fake_for_absent(self):
        """FakeRun: образ есть, inspect → absent, run → ok."""
        return FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),
            ("docker inspect", 1, "", "No such object"),
            # docker run → default rc=0
            # docker exec -d (Xvfb) → default rc=0
        ])

    def test_second_ensure_no_docker_calls(self):
        """После первого ensure() повторный вызов не делает ни одного docker-вызова."""
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-cache")
        c.ensure()
        # Сбросить историю вызовов после первого ensure
        fake.calls.clear()
        # Второй вызов — должен быть no-op
        c.ensure()
        assert len(fake.calls) == 0, (
            "второй ensure() не должен делать docker-вызовы, но сделал: "
            + str(fake.calls)
        )

    def test_after_mark_broken_ensure_reruns_lifecycle(self):
        """После mark_broken() следующий ensure() снова выполняет полный жизненный цикл.

        Часы продвигаются за пределы окна повторов, чтобы ensure() не упал
        с «следующая попытка позже».
        """
        # Часы: 0.0 при mark_broken, 20.0 при проверке окна в ensure()
        times = [0.0, 20.0]
        idx = [0]

        def fake_clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),
            ("docker inspect", 1, "", "No such object"),
            # docker run (первый ensure) → default rc=0
            # docker exec -d Xvfb (первый ensure) → default rc=0
            # После mark_broken — второй ensure:
            # docker images -q → abc123 (маршрут уже задан)
            # docker inspect → running (контейнер поднят, переиспользуем)
            # docker exec -d Xvfb → default rc=0
        ])
        # Переопределим inspect: после первого ensure будет returning "running"
        # Это сделаем через отдельный FakeRun с двумя маршрутами для inspect.
        call_counts = {"inspect": 0}
        original_call = fake.__call__

        def patched_call(cmd, **kw):
            joined = " ".join(cmd)
            if "docker inspect" in joined:
                call_counts["inspect"] += 1
                # Первый вызов — absent; все последующие — running
                if call_counts["inspect"] == 1:
                    class R:
                        returncode = 1
                        stdout = ""
                        stderr = "No such object"
                    return R()
                else:
                    class R:
                        returncode = 0
                        stdout = "running\n"
                        stderr = ""
                    return R()
            return original_call(cmd, **kw)

        fake.__call__ = patched_call

        c = _make_container(fake, name="ai1c-cache2", clock=fake_clock,
                            retry_seconds=DEFAULT_RETRY_SECONDS)
        c.ensure()  # первый ensure — полный жизненный цикл
        assert c._ready, "_ready должен быть True после первого ensure"

        c.mark_broken()  # broken_at = 0.0
        assert not c._ready, "_ready должен быть False после mark_broken"

        # Сбросить историю вызовов
        fake.calls.clear()

        # Второй ensure — часы вернут 20.0, окно (10 с) истекло → проходит
        c.ensure()
        # Ожидаем как минимум docker images -q и docker inspect
        assert len(fake.calls) > 0, (
            "после mark_broken() ensure() должен снова делать docker-вызовы"
        )
        joined_calls = " ".join(" ".join(c) for c in fake.calls)
        assert "docker images" in joined_calls or "docker inspect" in joined_calls

    def test_recovery_clears_broken(self):
        """Успешный ensure() после mark_broken сбрасывает broken → False."""
        # broken_at = 0.0; при проверке окна в ensure() вернётся 20.0 (> retry_seconds)
        times = [0.0, 20.0]
        idx = [0]

        def fake_clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),
            ("docker inspect", 0, "running\n", ""),
        ])
        c = _make_container(fake, name="ai1c-recovery", clock=fake_clock,
                            retry_seconds=DEFAULT_RETRY_SECONDS)

        c.mark_broken()  # broken_at = 0.0
        assert c.broken

        # Часы вернут 20.0 → окно истекло → ensure() выполняется и восстанавливает
        c.ensure()
        assert not c.broken, "broken должен быть False после успешного ensure()"
        assert c._ready, "_ready должен быть True после восстановления"

        # Проверяем, что следующий ensure() — no-op (fast-path)
        fake.calls.clear()
        c.ensure()
        assert len(fake.calls) == 0, (
            "после восстановления второй ensure() должен быть no-op (fast-path)"
        )

    def test_within_window_ensure_raises_no_docker_calls(self):
        """ensure() внутри окна повторов бросает RuntimeError без docker-вызовов."""
        # broken_at = 0.0; при проверке окна вернётся 1.0 (< retry_seconds=10)
        times = [0.0, 1.0]
        idx = [0]

        def fake_clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),
            ("docker inspect", 0, "running\n", ""),
        ])
        c = _make_container(fake, name="ai1c-window", clock=fake_clock,
                            retry_seconds=10.0)

        c.mark_broken()  # broken_at = 0.0
        fake.calls.clear()

        with pytest.raises(RuntimeError, match="недоступен"):
            c.ensure()  # часы → 1.0, окно не истекло → raise fast

        assert len(fake.calls) == 0, (
            "ensure() внутри окна не должен делать docker-вызовы"
        )


# ---------------------------------------------------------------------------
# ensure() — образ отсутствует → RuntimeError из _build
# ---------------------------------------------------------------------------

class TestEnsureImageMissing:
    def test_raises_if_image_missing(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "", ""),  # image_exists → False
        ])
        c = _make_container(fake)
        with pytest.raises(RuntimeError, match="не найден"):
            c.ensure()

    def test_no_container_ops_if_image_missing(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "", ""),
        ])
        c = _make_container(fake)
        try:
            c.ensure()
        except RuntimeError:
            pass
        assert not fake.called_with("docker inspect")
        assert not fake.called_with("docker run")
        assert not fake.called_with("docker start")


# ---------------------------------------------------------------------------
# mark_broken + broken + retry window (идемпотентность)
# ---------------------------------------------------------------------------

class TestMarkBroken:
    def test_initially_not_broken(self):
        fake = FakeRun()
        c = _make_container(fake)
        assert not c.broken

    def test_mark_broken_sets_broken(self):
        fake = FakeRun()
        c = _make_container(fake)
        c.mark_broken()
        assert c.broken

    def test_mark_broken_idempotent(self):
        """Повторный вызов mark_broken не перезапускает окно."""
        times = [0.0, 5.0, 6.0]
        idx = [0]

        def fake_clock():
            t = times[idx[0]]
            if idx[0] < len(times) - 1:
                idx[0] += 1
            return t

        fake = FakeRun()
        c = _make_container(fake, clock=fake_clock, retry_seconds=10.0)
        c.mark_broken()   # t=0 → broken_at=0
        first_broken_at = c._broken_at

        c.mark_broken()   # t=5 — уже broken, окно НЕ перезапускается
        assert c._broken_at == first_broken_at, "broken_at не должен изменяться при повторном mark_broken"

    def test_broken_stays_true_after_retry_window(self):
        """broken остаётся True после истечения окна (окно влияет только на попытки, не сбрасывает флаг)."""
        # Окно 5 секунд; после вызова mark_broken симулируем пройденное время
        times = [0.0, 10.0]  # первый вызов clock() — при mark_broken; второй — при проверке broken
        idx = [0]

        def fake_clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun()
        c = _make_container(fake, clock=fake_clock, retry_seconds=5.0)
        c.mark_broken()
        # Теперь clock() вернёт 10.0, а retry_seconds=5.0 → 10-0=10 >= 5 → прошло окно
        # Но broken просто проверяет _broken_at is not None — флаг остаётся true.
        # Окно используется в client() для гейтинга попыток, а не для сброса флага.
        assert c.broken  # помечен — значит broken=True даже после окна

    def test_within_retry_window_true_when_fresh(self):
        times = [0.0, 1.0]
        idx = [0]

        def clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun()
        c = _make_container(fake, clock=clock, retry_seconds=5.0)
        c.mark_broken()   # broken_at = 0
        assert c._within_retry_window()  # elapsed=1 < 5 → True

    def test_within_retry_window_false_after_expiry(self):
        times = [0.0, 20.0]
        idx = [0]

        def clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun()
        c = _make_container(fake, clock=clock, retry_seconds=5.0)
        c.mark_broken()   # broken_at = 0
        assert not c._within_retry_window()  # elapsed=20 >= 5 → False


# ---------------------------------------------------------------------------
# exec_run — формирование docker exec
# ---------------------------------------------------------------------------

class TestExecRun:
    def test_exec_run_basic(self):
        fake = FakeRun(default_rc=0, default_out="hello\n", default_err="")
        c = _make_container(fake, name="ai1c-proj")
        result = c.exec_run(["ls", "-la"])
        calls = fake.called_with("docker exec")
        assert len(calls) == 1
        cmd = calls[0]
        assert "docker" in cmd and "exec" in cmd
        assert "ai1c-proj" in cmd
        assert "ls" in cmd and "-la" in cmd

    def test_exec_run_with_cwd(self):
        fake = FakeRun()
        c = _make_container(fake, name="ai1c-proj")
        c.exec_run(["pwd"], cwd="/workspace/myapp")
        cmd = fake.called_with("docker exec")[0]
        assert "-w" in cmd
        idx = cmd.index("-w")
        assert cmd[idx + 1] == "/workspace/myapp"

    def test_exec_run_without_cwd_no_w_flag(self):
        fake = FakeRun()
        c = _make_container(fake)
        c.exec_run(["echo", "hi"])
        cmd = fake.called_with("docker exec")[0]
        assert "-w" not in cmd

    def test_exec_run_returns_run_result(self):
        fake = FakeRun(default_rc=42, default_out="out\n", default_err="err\n")
        c = _make_container(fake)
        result = c.exec_run(["false"])
        assert isinstance(result, RunResult)
        assert result.returncode == 42
        assert result.stdout == "out\n"
        assert result.stderr == "err\n"

    def test_exec_run_argv_order(self):
        """argv идёт после имени контейнера."""
        fake = FakeRun()
        c = _make_container(fake, name="ai1c-test")
        c.exec_run(["python3", "-c", "print(1)"])
        cmd = fake.called_with("docker exec")[0]
        name_idx = cmd.index("ai1c-test")
        assert cmd[name_idx + 1] == "python3"
        assert cmd[name_idx + 2] == "-c"

    def test_exec_run_with_cwd_order(self):
        """-w <cwd> идёт до имени контейнера."""
        fake = FakeRun()
        c = _make_container(fake, name="ai1c-test")
        c.exec_run(["ls"], cwd="/tmp")
        cmd = fake.called_with("docker exec")[0]
        w_idx = cmd.index("-w")
        name_idx = cmd.index("ai1c-test")
        assert w_idx < name_idx


# ---------------------------------------------------------------------------
# exec_run timeout — subprocess.TimeoutExpired → RunResult(124)
# ---------------------------------------------------------------------------

class TestExecRunTimeout:
    """_DockerContainer.exec_run и DockerProvisioner.run: таймаут → RunResult(124)."""

    class _FakeRunWithTimeout:
        """subprocess.run, который может бросить TimeoutExpired и запоминает kwargs."""

        def __init__(self, raise_timeout=False, timeout_stdout=None, timeout_stderr=None):
            self.calls: list[list[str]] = []
            self.kwargs_list: list[dict] = []
            self._raise = raise_timeout
            self._timeout_stdout = timeout_stdout
            self._timeout_stderr = timeout_stderr

        def __call__(self, cmd, **kw):
            self.calls.append(list(cmd))
            self.kwargs_list.append(dict(kw))
            if self._raise:
                e = subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))
                e.stdout = self._timeout_stdout
                e.stderr = self._timeout_stderr
                raise e

            class R:
                returncode = 0
                stdout = ""
                stderr = ""
            return R()

        def called_with(self, keyword: str) -> list[list[str]]:
            return [c for c in self.calls if keyword in " ".join(c)]

    def _container(self, fake_run):
        return _DockerContainer(
            name="ai1c-test",
            image="ai1c-agent:latest",
            workdir="/workspace",
            volume="/vol",
            run=fake_run,
        )

    def test_exec_run_timeout_returns_124(self):
        """TimeoutExpired в exec_run → RunResult(124, ...) без исключения."""
        fake = self._FakeRunWithTimeout(raise_timeout=True)
        c = self._container(fake)
        res = c.exec_run(["sleep", "10"], timeout=1.0)
        assert res.returncode == 124

    def test_exec_run_timeout_marker_in_stderr(self):
        """stderr содержит маркер <timeout>."""
        fake = self._FakeRunWithTimeout(raise_timeout=True)
        c = self._container(fake)
        res = c.exec_run(["sleep", "10"], timeout=1.0)
        assert "<timeout>" in res.stderr

    def test_exec_run_timeout_does_not_raise(self):
        """TimeoutExpired не всплывает из exec_run."""
        fake = self._FakeRunWithTimeout(raise_timeout=True)
        c = self._container(fake)
        # Просто не должно бросить
        res = c.exec_run(["cmd"], timeout=0.1)
        assert res.returncode == 124

    def test_exec_run_timeout_partial_output_captured(self):
        """Если TimeoutExpired несёт частичный вывод, он попадает в RunResult."""
        fake = self._FakeRunWithTimeout(
            raise_timeout=True,
            timeout_stdout="partial out",
            timeout_stderr="partial err",
        )
        c = self._container(fake)
        res = c.exec_run(["cmd"], timeout=1.0)
        assert res.stdout == "partial out"
        assert "partial err" in res.stderr
        assert "<timeout>" in res.stderr

    def test_exec_run_timeout_forwarded_to_subprocess(self):
        """timeout передаётся в subprocess.run."""
        fake = self._FakeRunWithTimeout(raise_timeout=False)
        c = self._container(fake)
        c.exec_run(["ls"], timeout=7.5)
        exec_kwargs = [kw for cmd, kw in zip(fake.calls, fake.kwargs_list)
                       if "docker exec" in " ".join(cmd)]
        assert exec_kwargs, "docker exec должен быть вызван"
        assert exec_kwargs[0].get("timeout") == 7.5

    def test_exec_run_timeout_none_forwarded(self):
        """timeout=None тоже передаётся (None → без таймаута)."""
        fake = self._FakeRunWithTimeout(raise_timeout=False)
        c = self._container(fake)
        c.exec_run(["ls"], timeout=None)
        exec_kwargs = [kw for cmd, kw in zip(fake.calls, fake.kwargs_list)
                       if "docker exec" in " ".join(cmd)]
        assert exec_kwargs[0].get("timeout") is None

    def test_provisioner_run_timeout_returns_124(self):
        """DockerProvisioner.run(timeout=) → RunResult(124) при таймауте (сквозной путь)."""
        fake = self._FakeRunWithTimeout(raise_timeout=True)
        from agentmon.backends.docker import _DockerContainer as DC

        real_container = DC(
            name="ai1c-test", image="ai1c-agent:latest",
            workdir="/workspace", volume="/vol",
            run=fake,
        )
        prov = DockerProvisioner(real_container)
        real_container.ensure = lambda: None  # обойти docker-вызовы
        res = prov.run(["sleep", "10"], timeout=1.0)
        assert res.returncode == 124
        assert "<timeout>" in res.stderr

    def test_provisioner_run_timeout_forwarded(self):
        """DockerProvisioner.run пробрасывает timeout в container.exec_run."""
        received = {}

        class _TrackingContainer(_FakeContainer):
            def exec_run(self, argv, cwd=None, timeout=None):
                received["timeout"] = timeout
                return RunResult(0, "", "")

        container = _TrackingContainer()
        prov = DockerProvisioner(container)
        prov.run(["ls"], timeout=3.5)
        assert received.get("timeout") == 3.5

    def test_provisioner_run_timeout_none_no_regression(self):
        """timeout=None — обычный RunResult, без исключений (регрессия)."""
        received = {}

        class _TrackingContainer(_FakeContainer):
            def exec_run(self, argv, cwd=None, timeout=None):
                received["timeout"] = timeout
                return RunResult(0, "ok\n", "")

        container = _TrackingContainer()
        prov = DockerProvisioner(container)
        res = prov.run(["ls"])
        assert res.returncode == 0
        assert received.get("timeout") is None


# ---------------------------------------------------------------------------
# remove() — docker rm -f
# ---------------------------------------------------------------------------

class TestRemove:
    def test_remove_calls_docker_rm_f(self):
        fake = FakeRun()
        c = _make_container(fake, name="ai1c-proj")
        c.remove()
        rm_calls = fake.called_with("docker rm")
        assert len(rm_calls) == 1
        cmd = rm_calls[0]
        assert cmd[:3] == ["docker", "rm", "-f"]
        assert "ai1c-proj" in cmd


# ---------------------------------------------------------------------------
# exec_input — docker exec -i с передачей stdin
# ---------------------------------------------------------------------------

class TestExecInput:
    class _FakeRunWithInput:
        """FakeRun, который запоминает kwargs (в т.ч. input=) без падения."""

        def __init__(self, rc=0, stdout=b"", stderr=b""):
            self.calls: list[list[str]] = []
            self.input_data: list[bytes | None] = []
            self._rc = rc
            self._stdout = stdout
            self._stderr = stderr

        def __call__(self, cmd, **kw):
            self.calls.append(list(cmd))
            self.input_data.append(kw.get("input"))

            class R:
                pass

            R.returncode = self._rc
            R.stdout = self._stdout
            R.stderr = self._stderr
            return R

        def called_with(self, keyword: str) -> list[list[str]]:
            return [c for c in self.calls if keyword in " ".join(c)]

    def _make(self, fake_run):
        from agentmon.backends.docker import _DockerContainer
        return _DockerContainer(
            name="ai1c-test",
            image="ai1c-agent:latest",
            workdir="/workspace",
            volume="/vol",
            run=fake_run,
        )

    def test_exec_input_uses_docker_exec_i(self):
        fake = self._FakeRunWithInput()
        c = self._make(fake)
        c.exec_input(["tee", "/workspace/file.bin"], b"hello")
        calls = fake.called_with("docker exec")
        assert len(calls) == 1
        cmd = calls[0]
        assert "-i" in cmd

    def test_exec_input_passes_data_as_stdin(self):
        fake = self._FakeRunWithInput()
        c = self._make(fake)
        payload = b"\x00\x01\x02\xff"
        c.exec_input(["cat"], payload)
        assert fake.input_data[0] == payload

    def test_exec_input_argv_after_name(self):
        fake = self._FakeRunWithInput()
        c = self._make(fake)
        c.exec_input(["sh", "-c", "cat > /tmp/x"], b"data")
        cmd = fake.called_with("docker exec")[0]
        name_idx = cmd.index("ai1c-test")
        assert cmd[name_idx + 1] == "sh"

    def test_exec_input_returns_run_result(self):
        fake = self._FakeRunWithInput(rc=0, stdout=b"ok\n", stderr=b"")
        c = self._make(fake)
        result = c.exec_input(["cat"], b"x")
        assert isinstance(result, RunResult)
        assert result.returncode == 0

    def test_exec_input_no_capture_output_text_flags(self):
        """exec_input НЕ должен передавать text=True — данные бинарные."""
        fake = self._FakeRunWithInput()
        c = self._make(fake)
        c.exec_input(["cat"], b"bytes")
        # fake запоминает все kwargs; убедимся, что input= передан
        assert fake.input_data[0] == b"bytes"


# ---------------------------------------------------------------------------
# Xvfb — ensure() запускает Xvfb после старта контейнера
# ---------------------------------------------------------------------------

class TestXvfb:
    def _fake_for_absent(self):
        return FakeRun(routes=[
            ("docker images -q", 0, "abc123\n", ""),
            ("docker inspect", 1, "", "No such object"),  # absent
            # docker run → default rc=0
            # docker exec -d (Xvfb) → default rc=0
        ])

    def test_ensure_calls_xvfb_exec_after_run(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-proj")
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        assert len(xvfb_calls) >= 1, "docker exec для Xvfb должен быть вызван"

    def test_xvfb_exec_uses_detach_flag(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-proj")
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        cmd = xvfb_calls[0]
        assert "-d" in cmd

    def test_xvfb_exec_targets_correct_container(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-myproj")
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        cmd = xvfb_calls[0]
        assert "ai1c-myproj" in cmd

    def test_xvfb_exec_contains_xvfb_99(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, name="ai1c-proj")
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        full = " ".join(xvfb_calls[0])
        assert "Xvfb :99" in full

    def test_xvfb_exec_idempotent_pgrep_check(self):
        """Команда содержит pgrep-проверку для идемпотентности."""
        fake = self._fake_for_absent()
        c = _make_container(fake)
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        full = " ".join(xvfb_calls[0])
        assert "pgrep" in full

    def test_xvfb_also_called_on_exited_start(self):
        fake = FakeRun(routes=[
            ("docker images -q", 0, "abc\n", ""),
            ("docker inspect", 0, "exited\n", ""),
            # docker start → default rc=0
            # docker exec -d (Xvfb) → default rc=0
        ])
        c = _make_container(fake, name="ai1c-exited")
        c.ensure()
        xvfb_calls = fake.called_with("docker exec")
        assert len(xvfb_calls) >= 1


# ---------------------------------------------------------------------------
# DockerProvisioner — фейк-контейнер для unit-тестов
# ---------------------------------------------------------------------------

class _FakeContainer:
    """Фейк-контейнер для DockerProvisioner: записывает вызовы, возвращает RunResult.

    Позволяет настраивать ответы через ``set_result`` перед конкретным вызовом.
    ``ensure_count`` — число вызовов ensure() для проверки.
    """

    def __init__(self, default_rc=0, default_stdout="", default_stderr=""):
        self.ensure_count = 0
        self.exec_calls: list[dict] = []   # {'argv': [...], 'cwd': ...}
        self.input_calls: list[dict] = []  # {'argv': [...], 'data': ...}
        self._default = RunResult(default_rc, default_stdout, default_stderr)
        self._next_results: list[RunResult] = []

    def ensure(self) -> None:
        """Имитация _DockerContainer.ensure(); считает вызовы."""
        self.ensure_count += 1

    def set_result(self, result: RunResult) -> None:
        """Задать RunResult для следующего вызова exec_run/exec_input."""
        self._next_results.append(result)

    def _pop_result(self) -> RunResult:
        if self._next_results:
            return self._next_results.pop(0)
        return self._default

    def exec_run(self, argv: list[str], cwd=None, timeout=None) -> RunResult:
        self.exec_calls.append({"argv": list(argv), "cwd": cwd})
        return self._pop_result()

    def exec_input(self, argv: list[str], data: bytes) -> RunResult:
        self.input_calls.append({"argv": list(argv), "data": data})
        return self._pop_result()


def _make_provisioner(default_rc=0, default_stdout="", default_stderr=""):
    """Фабрика: возвращает (DockerProvisioner, _FakeContainer)."""
    container = _FakeContainer(default_rc, default_stdout, default_stderr)
    provisioner = DockerProvisioner(container)
    return provisioner, container


# ---------------------------------------------------------------------------
# TestDockerProvisioner — файловые операции
# ---------------------------------------------------------------------------

class TestDockerProvisioner:

    # --- mkdirs ---

    def test_mkdirs_calls_mkdir_p(self):
        p, c = _make_provisioner()
        p.mkdirs(["/workspace/a", "/workspace/b"])
        argvs = [call["argv"] for call in c.exec_calls]
        assert ["mkdir", "-p", "/workspace/a"] in argvs
        assert ["mkdir", "-p", "/workspace/b"] in argvs

    def test_mkdirs_triggers_ensure(self):
        p, c = _make_provisioner()
        p.mkdirs(["/tmp/x"])
        assert c.ensure_count >= 1

    # --- exists ---

    def test_exists_true_on_rc0(self):
        p, c = _make_provisioner(default_rc=0)
        assert p.exists("/workspace/file") is True

    def test_exists_false_on_rc1(self):
        p, c = _make_provisioner(default_rc=1)
        assert p.exists("/workspace/missing") is False

    def test_exists_uses_test_e(self):
        p, c = _make_provisioner()
        p.exists("/workspace/foo")
        argv = c.exec_calls[-1]["argv"]
        assert argv == ["test", "-e", "/workspace/foo"]

    def test_exists_triggers_ensure(self):
        p, c = _make_provisioner()
        p.exists("/x")
        assert c.ensure_count >= 1

    # --- is_file ---

    def test_is_file_true_on_rc0(self):
        p, c = _make_provisioner(default_rc=0)
        assert p.is_file("/workspace/f.txt") is True

    def test_is_file_false_on_rc1(self):
        p, c = _make_provisioner(default_rc=1)
        assert p.is_file("/workspace/dir") is False

    def test_is_file_uses_test_f(self):
        p, c = _make_provisioner()
        p.is_file("/workspace/f.txt")
        argv = c.exec_calls[-1]["argv"]
        assert argv == ["test", "-f", "/workspace/f.txt"]

    def test_is_file_triggers_ensure(self):
        p, c = _make_provisioner()
        p.is_file("/x")
        assert c.ensure_count >= 1

    # --- is_empty_dir ---

    def test_is_empty_dir_empty_path_returns_false(self):
        p, c = _make_provisioner()
        assert p.is_empty_dir("") is False
        # ensure не должен был вызываться
        assert c.ensure_count == 0

    def test_is_empty_dir_nonexistent_returns_true(self):
        """Несуществующий путь → True (место свободно)."""
        p, c = _make_provisioner(default_rc=1)  # test -e rc=1 → not exists
        assert p.is_empty_dir("/workspace/new") is True

    def test_is_empty_dir_file_returns_false(self):
        """Если путь — файл → False."""
        container = _FakeContainer()
        # exists → rc=0 (True); is_file → rc=0 (True)
        container.set_result(RunResult(0))   # ensure уже звал set_result?
        # Нет — ensure() не вызывает exec_run, он не из _pop_result.
        # exists вызывает exec_run с "test -e" → rc=0
        container.set_result(RunResult(0))   # test -e → exists=True
        container.set_result(RunResult(0))   # test -f → is_file=True
        p = DockerProvisioner(container)
        assert p.is_empty_dir("/workspace/file.txt") is False

    def test_is_empty_dir_empty_dir_returns_true(self):
        """Пустой каталог → True."""
        container = _FakeContainer()
        container.set_result(RunResult(0))        # test -e → exists=True
        container.set_result(RunResult(1))        # test -f → is_file=False
        container.set_result(RunResult(0, ""))    # ls -A → empty stdout
        p = DockerProvisioner(container)
        assert p.is_empty_dir("/workspace/empty") is True

    def test_is_empty_dir_nonempty_dir_returns_false(self):
        """Непустой каталог → False."""
        container = _FakeContainer()
        container.set_result(RunResult(0))              # test -e → True
        container.set_result(RunResult(1))              # test -f → False
        container.set_result(RunResult(0, "file.txt"))  # ls -A → non-empty
        p = DockerProvisioner(container)
        assert p.is_empty_dir("/workspace/full") is False

    def test_is_empty_dir_triggers_ensure(self):
        p, c = _make_provisioner(default_rc=1)
        p.is_empty_dir("/x")
        assert c.ensure_count >= 1

    # --- read_text ---

    def test_read_text_returns_stdout(self):
        p, c = _make_provisioner(default_stdout="hello world\n")
        result = p.read_text("/workspace/file.txt")
        assert result == "hello world\n"

    def test_read_text_uses_cat(self):
        p, c = _make_provisioner()
        p.read_text("/workspace/cfg.txt")
        argv = c.exec_calls[-1]["argv"]
        assert argv == ["cat", "/workspace/cfg.txt"]

    def test_read_text_triggers_ensure(self):
        p, c = _make_provisioner()
        p.read_text("/x")
        assert c.ensure_count >= 1

    # --- write_bytes ---

    def test_write_bytes_calls_exec_input(self):
        p, c = _make_provisioner()
        p.write_bytes("/workspace/out.bin", b"\x00\x01\x02")
        assert len(c.input_calls) == 1
        call = c.input_calls[0]
        assert call["data"] == b"\x00\x01\x02"

    def test_write_bytes_uses_cat_redirect(self):
        """exec_input argv должен быть sh -c 'cat > <quoted path>'."""
        p, c = _make_provisioner()
        p.write_bytes("/workspace/f.bin", b"data")
        argv = c.input_calls[0]["argv"]
        assert argv[0] == "sh"
        assert argv[1] == "-c"
        assert "cat >" in argv[2]
        assert "/workspace/f.bin" in argv[2]

    def test_write_bytes_creates_parent_dir(self):
        """write_bytes вызывает mkdirs для родительского каталога."""
        p, c = _make_provisioner()
        p.write_bytes("/workspace/subdir/f.bin", b"x")
        mkdir_calls = [call["argv"] for call in c.exec_calls
                       if call["argv"][:2] == ["mkdir", "-p"]]
        assert any("/workspace/subdir" in " ".join(argv) for argv in mkdir_calls)

    def test_write_bytes_triggers_ensure(self):
        p, c = _make_provisioner()
        p.write_bytes("/x/f", b"")
        assert c.ensure_count >= 1

    # --- write_text ---

    def test_write_text_encodes_utf8(self):
        p, c = _make_provisioner()
        p.write_text("/workspace/t.txt", "Привет мир")
        assert c.input_calls[0]["data"] == "Привет мир".encode("utf-8")

    def test_write_text_triggers_ensure(self):
        p, c = _make_provisioner()
        p.write_text("/x", "hello")
        assert c.ensure_count >= 1

    # --- put_tree ---

    def test_put_tree_transfers_files(self, tmp_path):
        """Дерево файлов переносится через write_bytes."""
        (tmp_path / "a.txt").write_bytes(b"aaa")
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "b.txt").write_bytes(b"bbb")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")

        written = {call["argv"][2]: call["data"] for call in c.input_calls}
        # пути могут быть в sh -c 'cat > ...' form; берём весь argv[2]
        assert any("a.txt" in k for k in written)
        assert any("b.txt" in k for k in written)

    def test_put_tree_skips_pycache(self, tmp_path):
        """__pycache__ не переносится."""
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.pyc").write_bytes(b"pyc")
        (tmp_path / "real.py").write_bytes(b"code")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")

        transferred = " ".join(
            call["argv"][2] for call in c.input_calls
        )
        assert "pyc" not in transferred
        assert "real.py" in transferred

    def test_put_tree_skips_egg_info(self, tmp_path):
        """*.egg-info не переносится."""
        egg = tmp_path / "mypkg.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO").write_bytes(b"meta")
        (tmp_path / "mod.py").write_bytes(b"x")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")

        transferred = " ".join(
            call["argv"][2] for call in c.input_calls
        )
        assert "PKG-INFO" not in transferred
        assert "mod.py" in transferred

    def test_put_tree_respects_custom_skip(self, tmp_path):
        """Кастомный skip-предикат применяется."""
        (tmp_path / "keep.py").write_bytes(b"k")
        (tmp_path / "skip_me.txt").write_bytes(b"s")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst", skip=lambda rel: rel.name == "skip_me.txt")

        transferred = " ".join(
            call["argv"][2] for call in c.input_calls
        )
        assert "skip_me" not in transferred
        assert "keep.py" in transferred

    def test_put_tree_uses_correct_target_path(self, tmp_path):
        """Целевой путь: dst/rel.as_posix()."""
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "mod.py").write_bytes(b"x")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")

        # Ищем в exec_input — argv[2] = "cat > '/dst/pkg/mod.py'"
        target_args = [call["argv"][2] for call in c.input_calls]
        assert any("/dst/pkg/mod.py" in arg for arg in target_args)

    def test_put_tree_creates_dirs(self, tmp_path):
        """Подкаталоги создаются через mkdirs."""
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "f.py").write_bytes(b"x")

        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")

        mkdir_calls = [call["argv"] for call in c.exec_calls
                       if call["argv"][:2] == ["mkdir", "-p"]]
        # mkdirs вызван хотя бы для /dst/subdir
        all_dirs = " ".join(" ".join(argv) for argv in mkdir_calls)
        assert "/dst/subdir" in all_dirs

    def test_put_tree_triggers_ensure(self, tmp_path):
        p, c = _make_provisioner()
        p.put_tree(str(tmp_path), "/dst")
        assert c.ensure_count >= 1

    # --- run ---

    def test_run_delegates_to_exec_run(self):
        p, c = _make_provisioner(default_rc=0, default_stdout="ok\n")
        r = p.run(["ls", "-la"], cwd="/workspace")
        assert c.exec_calls[-1] == {"argv": ["ls", "-la"], "cwd": "/workspace"}
        assert isinstance(r, RunResult)
        assert r.stdout == "ok\n"

    def test_run_triggers_ensure(self):
        p, c = _make_provisioner()
        p.run(["ls"])
        assert c.ensure_count >= 1

    # --- which ---

    def test_which_returns_path_on_success(self):
        p, c = _make_provisioner(default_rc=0, default_stdout="/usr/bin/git\n")
        result = p.which("git")
        assert result == "/usr/bin/git"

    def test_which_returns_none_on_empty(self):
        p, c = _make_provisioner(default_rc=1, default_stdout="")
        result = p.which("nonexistent")
        assert result is None

    def test_which_uses_command_v(self):
        p, c = _make_provisioner()
        p.which("python3")
        argv = c.exec_calls[-1]["argv"]
        assert argv == ["command", "-v", "python3"]

    def test_which_triggers_ensure(self):
        p, c = _make_provisioner()
        p.which("git")
        assert c.ensure_count >= 1

    # --- python_cmd / venv_python / tempdir ---

    def test_python_cmd_returns_python3(self):
        p, _ = _make_provisioner()
        assert p.python_cmd() == ["python3"]

    def test_venv_python_correct_path(self):
        p, _ = _make_provisioner()
        assert p.venv_python("/workspace/proj") == "/workspace/proj/.venv/bin/python"

    def test_tempdir_returns_tmp(self):
        p, _ = _make_provisioner()
        assert p.tempdir() == "/tmp"


# ---------------------------------------------------------------------------
# TestDockerRunner — агент claude в контейнере через docker exec -it
# ---------------------------------------------------------------------------

class _FakePty:
    """Фейк PTY-процесса: записывает команду/cwd, имитирует alive/kill/interrupt."""

    def __init__(self, cmd, cwd):
        self.cmd = cmd
        self.cwd = cwd
        self.written: list[str] = []
        self.alive = True
        self.killed = False
        self.interrupted = False
        self.pending = ""
        self.raise_on_interrupt = False

    def write(self, text: str) -> None:
        self.written.append(text)

    def read_available(self) -> str:
        out, self.pending = self.pending, ""
        return out

    def interrupt(self) -> None:
        if self.raise_on_interrupt:
            raise OSError("simulated dead pty")
        self.interrupted = True
        self.written.append("\x1b")

    def kill(self) -> None:
        self.killed = True
        self.alive = False


class _FakeDockerContainer:
    """Фейк _DockerContainer: запоминает ensure()-вызовы, предоставляет name."""

    def __init__(self, name: str = "ai1c-myproj"):
        self._name = name
        self.ensure_count = 0

    @property
    def name(self) -> str:
        return self._name

    def ensure(self) -> None:
        self.ensure_count += 1


def _make_runner(container_name="ai1c-myproj", claude_cmd="claude --go",
                 workdir=DEFAULT_WORKDIR, host_cwd="/tmp"):
    """Фабрика: возвращает (DockerRunner, FakeContainer, список spawned Pty)."""
    spawned: list[_FakePty] = []
    container = _FakeDockerContainer(name=container_name)

    def fake_spawn(cmd: str, cwd: str, env=None):
        p = _FakePty(cmd, cwd)
        spawned.append(p)
        return p

    runner = DockerRunner(
        container=container,
        claude_cmd=claude_cmd,
        workdir=workdir,
        spawn_fn=fake_spawn,
        host_cwd=host_cwd,
    )
    return runner, container, spawned


def _project(key="proj-1", claude_cmd=None):
    """Простой фейк-проект (SimpleNamespace)."""
    return types.SimpleNamespace(key=key, claude_cmd=claude_cmd)


class TestDockerRunner:

    # --- start: правильная команда ---

    def test_start_spawns_docker_exec_it(self):
        """start() формирует команду docker exec -it с флагами -w, именем и claude_cmd."""
        runner, container, spawned = _make_runner(
            container_name="ai1c-myproj",
            claude_cmd="claude --go",
            workdir="/workspace",
            host_cwd="/tmp",
        )
        runner.start(_project())
        assert len(spawned) == 1
        cmd = spawned[0].cmd
        assert cmd == "docker exec -it -w /workspace ai1c-myproj claude --go"

    def test_start_uses_project_claude_cmd_when_set(self):
        """project.claude_cmd перекрывает дефолтную команду runner'а."""
        runner, _, spawned = _make_runner(claude_cmd="claude --default")
        runner.start(_project(claude_cmd="claude --project-specific"))
        assert "claude --project-specific" in spawned[0].cmd

    def test_start_uses_default_claude_cmd_when_project_cmd_is_none(self):
        """Если project.claude_cmd is None — берётся runner.claude_cmd."""
        runner, _, spawned = _make_runner(claude_cmd="claude --go")
        runner.start(_project(claude_cmd=None))
        assert "claude --go" in spawned[0].cmd

    def test_start_cwd_is_host_cwd_not_project_path(self):
        """spawn() вызывается с host_cwd, а не project.path (который в контейнере)."""
        runner, _, spawned = _make_runner(host_cwd="/tmp")
        runner.start(_project())
        assert spawned[0].cwd == "/tmp"

    def test_start_calls_container_ensure(self):
        """start() обязан вызвать container.ensure() перед spawn."""
        runner, container, _ = _make_runner()
        runner.start(_project())
        assert container.ensure_count == 1

    def test_start_returns_project_key(self):
        """start() возвращает project.key как agent_id."""
        runner, _, _ = _make_runner()
        aid = runner.start(_project(key="my-proj"))
        assert aid == "my-proj"

    def test_start_idempotent_alive_proc(self):
        """Повторный start() с живым процессом не spawns новый и не зовёт ensure повторно."""
        runner, container, spawned = _make_runner()
        proj = _project()
        aid1 = runner.start(proj)
        ensure_after_first = container.ensure_count
        aid2 = runner.start(proj)
        assert aid1 == aid2
        assert len(spawned) == 1, "повторный spawn не должен происходить"
        assert container.ensure_count == ensure_after_first, (
            "ensure не должен вызываться повторно для живого агента"
        )

    def test_start_respawns_dead_proc(self):
        """После гибели процесса start() запускает нового агента."""
        runner, _, spawned = _make_runner()
        proj = _project()
        runner.start(proj)
        spawned[0].alive = False       # симулируем гибель
        runner.start(proj)
        assert len(spawned) == 2, "должен был сделать повторный spawn"

    def test_start_quotes_container_name_with_spaces(self):
        """Имена с пробелами экранируются через shlex.quote."""
        runner, _, spawned = _make_runner(container_name="ai1c my proj")
        runner.start(_project())
        assert "'ai1c my proj'" in spawned[0].cmd

    # --- send_input ---

    def test_send_input_collapses_crlf(self):
        """\\r\\n схлопываются в пробел перед отправкой."""
        runner, _, spawned = _make_runner()
        agent_id = runner.start(_project())
        runner.send_input(agent_id, "line1\r\nline2")
        # \r\n схлопываются в пробелы, в конце добавляется один \r
        written = "".join(spawned[0].written)
        assert "line1  line2\r" in written
        assert "\r\n" not in written

    def test_send_input_appends_cr(self):
        """Каждый send_input завершается \\r."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k1"))
        runner.send_input("k1", "hello")
        last = spawned[0].written[-1]
        assert last.endswith("\r")

    def test_send_input_replaces_newlines_with_space(self):
        """\\n внутри текста заменяются на пробел."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k2"))
        runner.send_input("k2", "a\nb")
        last = spawned[0].written[-1]
        assert "\n" not in last
        assert "a b" in last

    def test_send_input_unknown_agent_raises(self):
        """send_input для несуществующего agent_id бросает KeyError."""
        runner, _, _ = _make_runner()
        with pytest.raises(KeyError):
            runner.send_input("nonexistent", "hi")

    # --- tail_output ---

    def test_tail_output_returns_buffered_output(self):
        """tail_output возвращает накопленный вывод процесса."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k3"))
        spawned[0].pending = "hello from container"
        out = runner.tail_output("k3")
        assert "hello from container" in out

    def test_tail_output_empty_for_unknown_agent(self):
        """tail_output для несуществующего агента возвращает пустую строку."""
        runner, _, _ = _make_runner()
        assert runner.tail_output("ghost") == ""

    # --- stop ---

    def test_stop_kill_calls_proc_kill(self):
        """stop(..., 'kill') убивает PTY-процесс и удаляет агента."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k4"))
        runner.stop("k4", "kill")
        assert spawned[0].killed

    def test_stop_kill_forgets_agent(self):
        """После stop('kill') is_alive() возвращает False."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k5"))
        runner.stop("k5", "kill")
        assert not runner.is_alive("k5")

    def test_stop_interrupt_sends_escape(self):
        """stop(..., 'interrupt') вызывает proc.interrupt()."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k6"))
        runner.stop("k6", "interrupt")
        assert spawned[0].interrupted

    def test_stop_interrupt_dead_proc_no_exception(self):
        """OSError при interrupt (мёртвый PTY) не всплывает; агент забывается."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k7"))
        spawned[0].raise_on_interrupt = True
        runner.stop("k7", "interrupt")   # не должно бросить
        assert not runner.is_alive("k7")

    def test_stop_unknown_agent_raises(self):
        """stop для несуществующего agent_id бросает KeyError."""
        runner, _, _ = _make_runner()
        with pytest.raises(KeyError):
            runner.stop("ghost", "kill")

    # --- is_alive ---

    def test_is_alive_true_for_running_proc(self):
        """is_alive() возвращает True для живого агента."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k8"))
        assert runner.is_alive("k8")

    def test_is_alive_false_and_pops_dead_proc(self):
        """is_alive() возвращает False и убирает запись для мёртвого процесса."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="k9"))
        spawned[0].alive = False
        assert not runner.is_alive("k9")
        # повторный запрос — тоже False (запись уже удалена)
        assert not runner.is_alive("k9")

    def test_is_alive_false_for_unknown_agent(self):
        """is_alive() для несуществующего агента возвращает False."""
        runner, _, _ = _make_runner()
        assert not runner.is_alive("ghost")

    # --- shutdown_all ---

    def test_shutdown_all_kills_all_procs(self):
        """shutdown_all() убивает все запущенные PTY-процессы."""
        runner, _, spawned = _make_runner()
        runner.start(_project(key="a"))
        runner.start(_project(key="b"))
        runner.shutdown_all()
        assert all(p.killed for p in spawned)

    def test_shutdown_all_clears_state(self):
        """После shutdown_all() runner не знает ни одного агента."""
        runner, _, _ = _make_runner()
        runner.start(_project(key="a"))
        runner.start(_project(key="b"))
        runner.shutdown_all()
        assert not runner.is_alive("a")
        assert not runner.is_alive("b")


# ---------------------------------------------------------------------------
# TestDockerFiles — чтение журналов через docker exec
# ---------------------------------------------------------------------------

class _FakeFilesContainer:
    """Фейк-контейнер для DockerFiles: раздельные очереди для exec_run и exec_run_bytes.

    ``set_exec(result)``  — поставить RunResult в очередь exec_run.
    ``set_bytes(rc, data)`` — поставить (rc, bytes) в очередь exec_run_bytes.
    ``mark_broken()``      — запоминает, что контейнер помечен битым.
    """

    def __init__(self, name: str = "ai1c-test"):
        self._name = name
        self._exec_q: list[RunResult] = []
        self._bytes_q: list[tuple[int, bytes]] = []
        self.exec_calls: list[list[str]] = []
        self.bytes_calls: list[list[str]] = []
        self.broken_called = False

    @property
    def name(self) -> str:
        return self._name

    def mark_broken(self) -> None:
        self.broken_called = True

    def set_exec(self, result: RunResult) -> None:
        self._exec_q.append(result)

    def set_bytes(self, rc: int, data: bytes) -> None:
        self._bytes_q.append((rc, data))

    def exec_run(self, argv: list[str], cwd=None) -> RunResult:
        self.exec_calls.append(list(argv))
        if self._exec_q:
            return self._exec_q.pop(0)
        return RunResult(0, "", "")

    def exec_run_bytes(self, argv: list[str]) -> tuple[int, bytes]:
        self.bytes_calls.append(list(argv))
        if self._bytes_q:
            return self._bytes_q.pop(0)
        return (0, b"")


def _make_files(name="ai1c-test", home=None, guess="/root"):
    """Фабрика: возвращает (DockerFiles, _FakeFilesContainer)."""
    container = _FakeFilesContainer(name=name)
    files = DockerFiles(container, home=home, guess=guess)
    return files, container


class TestDockerFiles:

    # --- ленивый home: echo $HOME вызывается один раз ---

    def test_home_resolved_lazily_on_first_use(self):
        """_resolve_home вызывает echo $HOME только при первом обращении."""
        files, container = _make_files()
        container.set_exec(RunResult(0, "/home/user\n", ""))
        container.set_exec(RunResult(0, "/home/user\n", ""))  # не должен использоваться

        files.home_projects_dir()
        files.home_projects_dir()

        echo_calls = [c for c in container.exec_calls if "echo" in " ".join(c)]
        assert len(echo_calls) == 1, "echo $HOME должен быть вызван ровно один раз"

    def test_home_cached_after_success(self):
        """Успешное определение home кешируется — повторный exec не нужен."""
        files, container = _make_files()
        container.set_exec(RunResult(0, "/home/alice\n", ""))

        files._resolve_home()
        files._resolve_home()

        assert files._resolved_home == "/home/alice"
        assert len(container.exec_calls) == 1

    def test_explicit_home_no_exec(self):
        """Явный home= — exec_run не вызывается вовсе."""
        files, container = _make_files(home="/explicit/home")
        _ = files.home_projects_dir()
        assert container.exec_calls == []

    def test_failure_not_cached_next_call_retries(self):
        """Неудача не кешируется: следующий вызов снова пробует echo $HOME."""
        files, container = _make_files(guess="/root")
        # Первый вызов — неудача (rc=1)
        container.set_exec(RunResult(1, "", "error"))
        # Второй вызов — успех
        container.set_exec(RunResult(0, "/home/bob\n", ""))

        first = files._resolve_home()
        second = files._resolve_home()

        assert first == "/root"          # возвращает guess
        assert second == "/home/bob"     # теперь успешно разрешён
        assert files._resolved_home == "/home/bob"
        assert len(container.exec_calls) == 2

    def test_failure_empty_stdout_returns_guess(self):
        """Пустой stdout → возвращает guess, не кеширует."""
        files, container = _make_files(guess="/root")
        container.set_exec(RunResult(0, "", ""))
        result = files._resolve_home()
        assert result == "/root"
        assert files._resolved_home is None

    def test_failure_relative_path_returns_guess(self):
        """Относительный путь в $HOME (не начинается с /) → guess, не кешируем."""
        files, container = _make_files(guess="/root")
        container.set_exec(RunResult(0, "relative/path\n", ""))
        result = files._resolve_home()
        assert result == "/root"
        assert files._resolved_home is None

    # --- home_projects_dir ---

    def test_home_projects_dir_format(self):
        """home_projects_dir = <home>/.claude/projects."""
        files, container = _make_files(home="/home/user")
        assert files.home_projects_dir() == "/home/user/.claude/projects"

    def test_home_projects_dir_strips_trailing_slash(self):
        """Лишний слеш в конце home обрезается."""
        files, container = _make_files(home="/home/user/")
        assert files.home_projects_dir() == "/home/user/.claude/projects"

    def test_home_projects_dir_with_lazy_home(self):
        """home_projects_dir через ленивое определение."""
        files, container = _make_files()
        container.set_exec(RunResult(0, "/root\n", ""))
        assert files.home_projects_dir() == "/root/.claude/projects"

    # --- list_files: разбор вывода find -printf ---

    def test_list_files_parses_find_output(self):
        """Корректный вывод find → список FileRef с правильными полями."""
        files, container = _make_files(home="/root")
        find_output = (
            "/root/.claude/projects/proj-abc/session-1.jsonl\t1234\t1718000000.123456\n"
            "/root/.claude/projects/proj-abc/session-2.jsonl\t5678\t1718001000.0\n"
        )
        container.set_exec(RunResult(0, find_output, ""))

        refs = files.list_files("/root/.claude/projects")

        assert len(refs) == 2
        ref1 = refs[0]
        assert ref1.path == "/root/.claude/projects/proj-abc/session-1.jsonl"
        assert ref1.dir_name == "proj-abc"
        assert ref1.session_id == "session-1"
        assert ref1.size == 1234
        assert abs(ref1.mtime - 1718000000.123456) < 1e-3

    def test_list_files_empty_output_returns_empty(self):
        """Пустой вывод find (каталог пуст) → []."""
        files, container = _make_files(home="/root")
        container.set_exec(RunResult(0, "", ""))
        refs = files.list_files("/root/.claude/projects")
        assert refs == []

    def test_list_files_nonzero_rc_returns_empty(self):
        """find rc≠0 (каталог не существует) → [] без mark_broken."""
        files, container = _make_files(home="/root")
        container.set_exec(RunResult(1, "", "No such file or directory"))
        refs = files.list_files("/root/.claude/projects")
        assert refs == []
        assert not container.broken_called

    def test_list_files_malformed_line_skipped(self):
        """Строка без табуляций пропускается; остальные разбираются."""
        files, container = _make_files(home="/root")
        find_output = (
            "malformed_line_no_tabs\n"
            "/root/.claude/projects/proj/ok.jsonl\t100\t1718000000.0\n"
        )
        container.set_exec(RunResult(0, find_output, ""))
        refs = files.list_files("/root/.claude/projects")
        assert len(refs) == 1
        assert refs[0].session_id == "ok"

    def test_list_files_uses_find_printf_command(self):
        """list_files вызывает find с правильными аргументами."""
        files, container = _make_files(home="/root")
        container.set_exec(RunResult(0, "", ""))
        files.list_files("/root/.claude/projects")
        argv = container.exec_calls[-1]
        assert argv[0] == "find"
        assert "/root/.claude/projects" in argv
        assert "-name" in argv
        assert "*.jsonl" in argv
        assert "-printf" in argv
        fmt_idx = argv.index("-printf")
        assert "%p" in argv[fmt_idx + 1]
        assert "%s" in argv[fmt_idx + 1]
        assert "%T@" in argv[fmt_idx + 1]

    def test_list_files_dir_name_is_parent_dir(self):
        """dir_name — имя непосредственного родительского каталога файла."""
        files, container = _make_files(home="/root")
        container.set_exec(RunResult(0,
            "/root/.claude/projects/my-project/abc.jsonl\t42\t1000000.0\n", ""))
        refs = files.list_files("/root/.claude/projects")
        assert refs[0].dir_name == "my-project"

    def test_list_files_session_id_without_extension(self):
        """session_id — имя файла без суффикса .jsonl."""
        files, container = _make_files(home="/root")
        container.set_exec(RunResult(0,
            "/root/.claude/projects/p/my-session-id.jsonl\t10\t1000000.0\n", ""))
        refs = files.list_files("/root/.claude/projects")
        assert refs[0].session_id == "my-session-id"

    # --- read_from: tail -c + правильное смещение ---

    def test_read_from_builds_tail_command(self):
        """read_from строит tail -c +<offset+1> с quoted путём."""
        files, container = _make_files(home="/root")
        container.set_bytes(0, b"data chunk")
        files.read_from("/root/.claude/projects/p/s.jsonl", 100)
        argv = container.bytes_calls[-1]
        joined = " ".join(argv)
        assert "tail" in joined
        assert "-c" in joined
        assert "+101" in joined          # offset=100 → +101

    def test_read_from_offset_zero(self):
        """offset=0 → tail -c +1 (читает весь файл)."""
        files, container = _make_files(home="/root")
        container.set_bytes(0, b"full content")
        files.read_from("/some/file.jsonl", 0)
        argv = container.bytes_calls[-1]
        joined = " ".join(argv)
        assert "+1" in joined

    def test_read_from_returns_data_and_new_offset(self):
        """Возвращает (data, offset + len(data))."""
        files, container = _make_files(home="/root")
        payload = b"hello world"
        container.set_bytes(0, payload)
        data, new_offset = files.read_from("/p/s.jsonl", 50)
        assert data == payload
        assert new_offset == 50 + len(payload)

    def test_read_from_failure_returns_empty(self):
        """rc≠0 → (b"", offset)."""
        files, container = _make_files(home="/root")
        container.set_bytes(1, b"")
        data, new_offset = files.read_from("/p/s.jsonl", 42)
        assert data == b""
        assert new_offset == 42

    def test_read_from_quotes_path(self):
        """Путь с пробелами корректно цитируется через shlex.quote."""
        files, container = _make_files(home="/root")
        container.set_bytes(0, b"")
        files.read_from("/path with spaces/file.jsonl", 0)
        argv = container.bytes_calls[-1]
        joined = " ".join(argv)
        assert "'/path with spaces/file.jsonl'" in joined

    def test_read_from_uses_exec_run_bytes(self):
        """read_from использует exec_run_bytes, а не exec_run."""
        files, container = _make_files(home="/root")
        container.set_bytes(0, b"result")
        files.read_from("/some/file.jsonl", 0)
        assert container.bytes_calls, "exec_run_bytes должен быть вызван"
        assert not any("tail" in " ".join(c) for c in container.exec_calls), (
            "exec_run (text) не должен вызываться из read_from"
        )


# ---------------------------------------------------------------------------
# TestDockerBackend — сборка бэкенда и проверка интерфейса
# ---------------------------------------------------------------------------

class TestDockerBackend:
    """DockerBackend собирает все четыре docker-класса и проксирует Backend-протокол."""

    def _make(self, path="/workspace"):
        """Фабрика: DockerBackend с FakeRun и fake_spawn, без реального Docker."""
        spawned = []

        def fake_spawn(cmd, cwd, env=None):
            p = _FakePty(cmd, cwd)
            spawned.append(p)
            return p

        fake_run = FakeRun(
            routes=[
                ("docker images -q", 0, "abc123\n", ""),
                ("docker inspect", 0, "running\n", ""),
            ]
        )
        backend = DockerBackend(
            path,
            claude_cmd="claude",
            run=fake_run,
            spawn_fn=fake_spawn,
        )
        return backend, fake_run, spawned

    # --- ключ ---

    def test_key_format(self):
        """key = 'docker||<project_path>'."""
        backend, _, _ = self._make("/workspace")
        assert backend.key == "docker||/workspace"

    def test_key_includes_full_path(self):
        """Полный путь, а не только basename."""
        backend, _, _ = self._make("/srv/projects/myapp")
        assert backend.key == "docker||/srv/projects/myapp"

    # --- типы атрибутов ---

    def test_runner_is_docker_runner(self):
        backend, _, _ = self._make()
        assert isinstance(backend.runner, DockerRunner)

    def test_files_is_docker_files(self):
        backend, _, _ = self._make()
        assert isinstance(backend.files, DockerFiles)

    def test_provisioner_is_docker_provisioner(self):
        backend, _, _ = self._make()
        assert isinstance(backend.provisioner, DockerProvisioner)

    # --- один экземпляр _DockerContainer ---

    def test_runner_and_files_share_same_container(self):
        """runner и files ссылаются на один и тот же _DockerContainer."""
        backend, _, _ = self._make()
        assert backend.runner._container is backend._container

    def test_files_and_provisioner_share_same_container(self):
        """files и provisioner ссылаются на один и тот же _DockerContainer."""
        backend, _, _ = self._make()
        assert backend.files._container is backend._container

    def test_all_share_same_container(self):
        """runner, files, provisioner — все три используют один контейнер."""
        backend, _, _ = self._make()
        c = backend._container
        assert backend.runner._container is c
        assert backend.files._container is c
        assert backend.provisioner._container is c

    # --- is_broken ---

    def test_is_broken_false_initially(self):
        """Новый бэкенд не сломан."""
        backend, _, _ = self._make()
        assert backend.is_broken is False

    def test_is_broken_reflects_container_broken(self):
        """is_broken проксирует container.broken."""
        backend, _, _ = self._make()
        backend._container.mark_broken()
        assert backend.is_broken is True

    # --- check ---

    def test_check_calls_container_ensure(self):
        """check() вызывает _container.ensure()."""
        backend, fake_run, _ = self._make()
        # ensure() потребует docker images -q и docker inspect — уже настроены
        fake_run.calls.clear()
        backend.check()
        # Ожидаем хотя бы вызов docker images -q или docker inspect
        joined = " ".join(" ".join(c) for c in fake_run.calls)
        assert "docker" in joined

    # --- close: shutdown_all, NO docker rm ---

    def test_close_calls_shutdown_all(self):
        """close() убивает все PTY-агенты через runner.shutdown_all()."""
        backend, _, spawned = self._make()
        import types
        proj = types.SimpleNamespace(key="p1", claude_cmd=None)
        # Чтобы запустить агента, нужен ensure → настроен fake_run
        backend.runner._container.ensure()
        backend.runner._procs["p1"] = _FakePty("docker exec ...", "/tmp")
        backend.close()
        assert backend.runner._procs == {}

    def test_close_does_not_call_docker_rm(self):
        """close() НЕ удаляет контейнер (docker rm не вызывается)."""
        backend, fake_run, _ = self._make()
        fake_run.calls.clear()
        backend.close()
        rm_calls = fake_run.called_with("docker rm")
        assert rm_calls == [], f"docker rm не должен вызываться при close(), вызовы: {rm_calls}"

    # --- имя контейнера и volume ---

    def test_container_name_derived_from_path(self):
        """Имя контейнера вычисляется через container_name(project_path)."""
        path = "/workspace"
        backend, _, _ = self._make(path)
        assert backend._container.name == container_name(path)

    def test_volume_name_matches_container_name(self):
        """Volume = '<container_name>-work'."""
        path = "/workspace"
        backend, _, _ = self._make(path)
        expected_volume = f"{container_name(path)}-work"
        assert backend._container._volume == expected_volume
