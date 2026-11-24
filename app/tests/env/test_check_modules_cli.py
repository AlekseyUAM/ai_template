"""check-modules.py: общий кэш успешной компиляции с run-tests.py.

Кэш хранится в logs/.check-modules-cache/cf.json и привязан к хэшу исходников
src/cf: повторная проверка тех же исходников не запускает компилятор, а
run-tests.py переиспользует результат, записанный check-modules.py.
"""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools"


def _load(name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Result:
    def __init__(self, rc: int):
        self.returncode = rc


def _setup_project(tmp_path, monkeypatch, mod, rc: int = 0):
    src = tmp_path / "src" / "cf"
    src.mkdir(parents=True)
    (src / "Configuration.xml").write_text("<Configuration/>", encoding="utf-8")
    module = src / "CommonModules" / "Тест" / "Ext" / "Module.bsl"
    module.parent.mkdir(parents=True)
    module.write_text("Процедура А() КонецПроцедуры", encoding="utf-8")
    wrapper = tmp_path / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("", encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "has_nonempty_changed_bsl",
                        lambda root, subdir=None: True)
    calls = []

    def fake_run(cmd, cwd=None):
        calls.append(cmd)
        return _Result(rc)

    # Подменяем только имя subprocess внутри загруженного скрипта,
    # не глобальный модуль subprocess.
    monkeypatch.setattr(mod, "subprocess", SimpleNamespace(run=fake_run))
    return src, calls


def _cache_file(tmp_path: Path) -> Path:
    return tmp_path / "logs" / ".check-modules-cache" / "cf.json"


def test_first_run_checks_and_stores_cache(tmp_path, monkeypatch):
    mod = _load("check-modules.py", "check_modules_cli")
    _, calls = _setup_project(tmp_path, monkeypatch, mod)

    assert mod.main([]) == 0
    assert len(calls) == 1
    data = json.loads(_cache_file(tmp_path).read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["rc"] == 0
    assert data["hash"]


def test_second_run_same_sources_skips(tmp_path, monkeypatch, capsys):
    mod = _load("check-modules.py", "check_modules_cli")
    _setup_project(tmp_path, monkeypatch, mod)

    assert mod.main([]) == 0
    assert mod.main([]) == 0
    assert "кэш" in capsys.readouterr().out


def test_changed_bsl_invalidates_cache(tmp_path, monkeypatch):
    mod = _load("check-modules.py", "check_modules_cli")
    src, calls = _setup_project(tmp_path, monkeypatch, mod)

    assert mod.main([]) == 0
    (src / "CommonModules" / "Тест" / "Ext" / "Module.bsl").write_text(
        "Процедура Б() КонецПроцедуры", encoding="utf-8")
    assert mod.main([]) == 0
    assert len(calls) == 2


def test_config_dump_info_change_does_not_invalidate(tmp_path, monkeypatch):
    mod = _load("check-modules.py", "check_modules_cli")
    src, calls = _setup_project(tmp_path, monkeypatch, mod)

    assert mod.main([]) == 0
    (src / "ConfigDumpInfo.xml").write_text(
        "<ConfigDumpInfo>изменён</ConfigDumpInfo>", encoding="utf-8")
    assert mod.main([]) == 0
    assert len(calls) == 1


def test_failed_check_is_not_cached(tmp_path, monkeypatch):
    mod = _load("check-modules.py", "check_modules_cli")
    _setup_project(tmp_path, monkeypatch, mod, rc=1)

    assert mod.main([]) == 1
    assert mod.main([]) == 1
    assert not _cache_file(tmp_path).exists()


def test_force_bypasses_cache(tmp_path, monkeypatch):
    mod = _load("check-modules.py", "check_modules_cli")
    _, calls = _setup_project(tmp_path, monkeypatch, mod)

    assert mod.main([]) == 0
    assert mod.main(["--force"]) == 0
    assert len(calls) == 2


def test_run_tests_reuses_cache_written_by_check_modules(tmp_path, monkeypatch,
                                                         capsys):
    cm = _load("check-modules.py", "check_modules_cli")
    _setup_project(tmp_path, monkeypatch, cm)
    assert cm.main([]) == 0

    rt = _load("run-tests.py", "run_tests_cli")
    monkeypatch.setattr(rt, "has_nonempty_changed_bsl",
                        lambda root, subdir=None: True)
    raw_calls = []

    def fake_raw(*args, **kwargs):
        raw_calls.append((args, kwargs))
        return rt.RC_OK

    monkeypatch.setattr(rt, "_check_modules_raw", fake_raw)
    assert rt.check_modules(tmp_path, None) == rt.RC_OK
    assert raw_calls == []
    assert "кэш" in capsys.readouterr().out
