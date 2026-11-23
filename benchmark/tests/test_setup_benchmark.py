"""Ретрай setup_benchmark при транзиентной блокировке ИБ."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "setup_benchmark.py"


def _load():
    spec = importlib.util.spec_from_file_location("setup_benchmark", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["setup_benchmark"] = mod
    spec.loader.exec_module(mod)
    return mod


LOCK = "Ошибка исключительной блокировки информационной базы"


def test_import_switches_stdout_to_utf8():
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location("
        f"'setup_benchmark', {str(SCRIPT)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['setup_benchmark'] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "print('\\u2713')\n"
    )
    env = {**os.environ, "PYTHONIOENCODING": "cp1251"}
    proc = subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_retries_lock_error_then_succeeds():
    mod = _load()
    attempts = []
    sleeps = []

    def run_setup():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError(LOCK)
        return "ok"

    result = mod.run_setup_with_lock_retry(
        run_setup, attempts=2, delay=5, sleep=sleeps.append,
        log=lambda line: None)
    assert result == "ok"
    assert len(attempts) == 2
    assert sleeps == [5]


def test_does_not_retry_other_errors():
    mod = _load()
    attempts = []

    def run_setup():
        attempts.append(1)
        raise RuntimeError("не блокировка")

    try:
        mod.run_setup_with_lock_retry(
            run_setup, attempts=2, sleep=lambda _s: None,
            log=lambda line: None)
    except RuntimeError as exc:
        assert "не блокировка" in str(exc)
    else:
        raise AssertionError("ожидали ошибку")
    assert len(attempts) == 1


def _completed(returncode):
    return subprocess.CompletedProcess(["docker", "info"], returncode)


def test_docker_problem_none_when_daemon_ok(monkeypatch):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **kw: _completed(0))
    assert mod.docker_problem() is None


def test_docker_problem_reports_missing_cli(monkeypatch):
    mod = _load()

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(mod.subprocess, "run", missing)
    assert "docker" in mod.docker_problem().lower()


def test_docker_problem_reports_stopped_daemon(monkeypatch):
    mod = _load()
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *a, **kw: _completed(1))
    assert "демон" in mod.docker_problem()


def test_docker_problem_passes_timeout(monkeypatch):
    mod = _load()
    seen = {}

    def slow(*_args, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired("docker info", kwargs["timeout"])

    monkeypatch.setattr(mod.subprocess, "run", slow)
    problem = mod.docker_problem()
    assert seen["timeout"] == 10.0
    assert "не ответил" in problem


def test_main_fails_before_store_without_docker(monkeypatch, capsys,
                                               tmp_path):
    mod = _load()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "load_repo_env", lambda: None)
    monkeypatch.setattr(mod, "docker_problem",
                        lambda *a, **kw: "демон не отвечает")
    assert mod.main([]) == 1
    assert "Docker недоступен" in capsys.readouterr().err


def test_gives_up_after_attempts():
    mod = _load()
    attempts = []
    sleeps = []

    def run_setup():
        attempts.append(1)
        raise RuntimeError(LOCK)

    try:
        mod.run_setup_with_lock_retry(
            run_setup, attempts=2, delay=5, sleep=sleeps.append,
            log=lambda line: None)
    except RuntimeError as exc:
        assert LOCK in str(exc)
    else:
        raise AssertionError("ожидали ошибку")
    assert len(attempts) == 2
    assert sleeps == [5]
