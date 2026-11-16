"""Ретрай setup_benchmark при транзиентной блокировке ИБ."""
import importlib.util
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
