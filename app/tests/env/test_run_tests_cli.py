"""run-tests.py: ошибка среды не должна выглядеть как ошибка компиляции."""
import importlib.util
from pathlib import Path

CLI = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools" / "run-tests.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_tests_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Result:
    def __init__(self, rc, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def _patch(monkeypatch, mod, result):
    monkeypatch.setattr(mod, "batch_cmd", lambda: ["dummy"])
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: result)


def test_compile_error_is_rc2(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(1, "Ошибка компиляции модуля: X"))
    assert mod.check_modules(Path("."), "ЮнитТесты") == mod.RC_COMPILE_ERROR


def test_marker_with_rc0_is_compile_error(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(0, "ОшибкаКомпиляцииВстроенногоЯзыка"))
    assert mod.check_modules(Path("."), "ЮнитТесты") == mod.RC_COMPILE_ERROR


def test_environment_failure_is_rc3(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(
        1, "Traceback (most recent call last):\nFileNotFoundError: 1cv8"))
    assert mod.check_modules(Path("."), "ЮнитТесты") == mod.RC_ENV_ERROR


def test_license_failure_is_rc3(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(1, "Не найдена лицензия на сервере"))
    assert mod.check_modules(Path("."), "ЮнитТесты") == mod.RC_ENV_ERROR


def test_ok_is_rc0(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(0, "Модули скомпилированы"))
    assert mod.check_modules(Path("."), "ЮнитТесты") == mod.RC_OK
