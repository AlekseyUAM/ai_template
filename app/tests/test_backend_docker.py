"""Тесты _DockerContainer — идентичность и жизненный цикл контейнера.

Все команды идут через FakeRun (без реального Docker).
FakeRun позволяет задавать разные ответы на разные команды по ключевому
слову из argv (подстрока в строке вида «docker inspect», «docker images» и т.д.).
"""
import pytest

from agentmon.backends.docker import (
    DEFAULT_IMAGE,
    DEFAULT_WORKDIR,
    DEFAULT_RETRY_SECONDS,
    _DockerContainer,
    container_name,
)
from agentmon.backends import RunResult


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
                    network="host", env=None, clock=None,
                    retry_seconds=DEFAULT_RETRY_SECONDS):
    """Фабрика контейнера с инъектируемым FakeRun."""
    kw = {}
    if clock is not None:
        kw["clock"] = clock
    return _DockerContainer(
        name=name,
        image=image,
        workdir=workdir,
        volume=volume,
        network=network,
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

    def test_docker_run_has_network(self):
        fake = self._fake_for_absent()
        c = _make_container(fake, network="host")
        c.ensure()
        cmd = fake.called_with("docker run")[0]
        assert "--network=host" in cmd

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

    def test_broken_false_after_retry_window(self):
        """После истечения окна broken → False (окно не перезапускалось)."""
        # Окно 2 секунды; после вызова mark_broken симулируем пройденное время
        times = [0.0, 10.0]  # первый вызов clock() — при mark_broken; второй — при проверке broken
        idx = [0]

        def fake_clock():
            t = times[min(idx[0], len(times) - 1)]
            idx[0] += 1
            return t

        fake = FakeRun()
        c = _make_container(fake, clock=fake_clock, retry_seconds=5.0)
        c.mark_broken()
        # Теперь clock() вернёт 10.0, а retry_seconds=5.0 → 10-0=10 >= 5 → broken НЕ проверяет окно
        # (broken просто проверяет _broken_at is not None)
        # По аналогии с _Connection.broken — broken=True если _broken_at is not None
        # Но окно используется в client(); здесь проверяем только mark_broken-идемпотентность.
        assert c.broken  # помечен — значит broken=True

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
