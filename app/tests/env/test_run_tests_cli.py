"""run-tests.py: ошибка среды не должна выглядеть как ошибка компиляции."""
import importlib.util
import json
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


def test_main_config_check_has_no_extension_flag(monkeypatch):
    mod = _load()
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _Result(0, "Модули скомпилированы")

    monkeypatch.setattr(mod, "batch_cmd", lambda: ["dummy"])
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    assert mod.check_modules(Path("."), None) == mod.RC_OK
    assert "--extension" not in calls[0]


def test_timeout_with_config_compile_error_is_rc2(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(1, "Ошибка компиляции модуля: X"))
    assert mod.diagnose_timeout(Path(".")) == mod.RC_COMPILE_ERROR


def test_timeout_without_config_compile_error_stays_rc124(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(0, "Модули скомпилированы"))
    assert mod.diagnose_timeout(Path(".")) == mod.RC_TIMEOUT


def test_timeout_with_env_failure_stays_rc124(monkeypatch):
    mod = _load()
    _patch(monkeypatch, mod, _Result(1, "Traceback (most recent call last):"))
    assert mod.diagnose_timeout(Path(".")) == mod.RC_TIMEOUT


def _config(tmp_path, result_path):
    cfg = tmp_path / "test.json"
    cfg.write_text(json.dumps({"ИмяМодуля": "M", "ИмяФайлаЛог": str(result_path)},
                              ensure_ascii=False), encoding="utf-8")
    return cfg


def _result(tests, done=True, error=None):
    return {"Выполнено": done, "ОписаниеОшибки": error, "РезультатТестов": tests}


def _patch_enterprise(monkeypatch, mod, result_path, result=None, rc=0):
    state = {"exists_at_start": None}

    def fake(project_root, c_value, timeout):
        state["exists_at_start"] = result_path.exists()
        if result is not None:
            result_path.write_text(json.dumps(result, ensure_ascii=False),
                                   encoding="utf-8")
        return rc

    monkeypatch.setattr(mod, "run_enterprise", fake)
    return state


def test_all_tests_passed_returns_rc0(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": True, "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK


def test_failed_test_returns_rc4_and_prints_summary(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": False,
                                "ОписаниеОшибки": "boom"}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_TESTS_FAILED
    out = capsys.readouterr().out
    assert "ИТОГ: 0/1 пройдено" in out
    assert "✗ A" in out
    assert "boom" in out


def test_missing_result_returns_rc5(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, None)
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_NO_RESULT
    assert "Файл результата не найден" in capsys.readouterr().out


def test_empty_test_list_returns_rc5(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, _result([]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_NO_RESULT


def test_previous_result_removed_before_run(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    result_path.write_text("старый", encoding="utf-8")
    cfg = _config(tmp_path, result_path)
    state = _patch_enterprise(monkeypatch, mod, result_path,
                              _result([{"Имя": "A", "Результат": True,
                                        "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK
    assert state["exists_at_start"] is False


def test_enterprise_failure_returned_as_is(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path, None, rc=1)
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == 1


def test_all_tests_passed_prints_summary(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": True,
                                "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK
    assert "ИТОГ: 1/1 пройдено" in capsys.readouterr().out


def test_debug_run_prints_not_evidence_notice(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": False,
                                "ОписаниеОшибки": "boom"}]))
    scenarios = "A"
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True,
                         scenarios) == mod.RC_TESTS_FAILED
    out = capsys.readouterr().out
    notice = "Отладочный прогон --test: это не доказательство смоука"
    assert notice in out
    assert out.index(notice) < out.index("ИТОГ: 0/1 пройдено")


def test_full_run_has_no_debug_notice(monkeypatch, tmp_path, capsys):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": True,
                                "ОписаниеОшибки": None}]))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_OK
    assert "не доказательство смоука" not in capsys.readouterr().out


def test_done_false_returns_rc4(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    _patch_enterprise(monkeypatch, mod, result_path,
                      _result([{"Имя": "A", "Результат": True,
                                "ОписаниеОшибки": None}], done=False))
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_TESTS_FAILED


def test_malformed_result_returns_rc5(monkeypatch, tmp_path):
    mod = _load()
    result_path = tmp_path / "result.json"
    cfg = _config(tmp_path, result_path)
    # Файл пишется во время «прогона»: _reset_result_log удаляет старый result.json,
    # поэтому запись после run_enterprise дала бы rc5 «файл не найден» вместо
    # «невалидный», и тест не отличил бы эти ветки.
    started = {}

    def fake(project_root, c_value, timeout):
        started["exists_at_start"] = result_path.exists()
        result_path.write_text("not json", encoding="utf-8")
        return mod.RC_OK

    monkeypatch.setattr(mod, "run_enterprise", fake)
    assert mod.run_tests(str(cfg), "ЮнитТесты", 10, True) == mod.RC_NO_RESULT
    assert started["exists_at_start"] is False
