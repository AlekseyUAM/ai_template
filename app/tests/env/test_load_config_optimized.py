"""Регрессия частичной загрузки: новый объект с формами/макетами.

Раньше load-config-optimized.py сводил любой подфайл к корню объекта. Для
нового отчёта этого мало: корневой XML ссылается на Form/Template, а сами
файлы-декларации в -listFile не попадали — платформа падала с «Неизвестный
объект метаданных». Здесь проверяем, что список содержит и корень, и файлы
форм/макетов (включая их Ext-содержимое).
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

SCRIPT = (Path(__file__).resolve().parents[3] / "template" / ".claude" /
          "tools" / "load-config-optimized.py")


def _load():
    spec = importlib.util.spec_from_file_location("load_config_optimized", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Completed:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def _fake_git(untracked):
    """subprocess-заглушка: git diff пуст, git ls-files --others отдаёт файлы."""
    def run(cmd, **_kwargs):
        if "diff" in cmd:
            return _Completed("")
        if "ls-files" in cmd:
            return _Completed("\n".join(untracked))
        raise AssertionError(f"неожиданный вызов: {cmd}")
    return SimpleNamespace(run=run)


def test_new_report_includes_form_and_template_files(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Reports/Продажи.xml",
        "Reports/Продажи/Ext/ObjectModule.bsl",
        "Reports/Продажи/Ext/ManagerModule.bsl",
        "Reports/Продажи/Forms/ФормаОтчета.xml",
        "Reports/Продажи/Forms/ФормаОтчета/Ext/Form.xml",
        "Reports/Продажи/Forms/ФормаОтчета/Ext/Form/Module.bsl",
        "Reports/Продажи/Templates/ОсновнаяСхемаКомпоновкиДанных.xml",
        ("Reports/Продажи/Templates/ОсновнаяСхемаКомпоновкиДанных/"
         "Ext/Template.xml"),
    ]
    cf_dir = tmp_path / "src" / "cf"
    for rel in files:
        path = cf_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got = mod.get_changed_files()

    assert "Reports/Продажи.xml" in got
    assert "Reports/Продажи/Forms/ФормаОтчета.xml" in got
    assert "Reports/Продажи/Templates/ОсновнаяСхемаКомпоновкиДанных.xml" in got
    assert "Reports/Продажи/Forms/ФормаОтчета/Ext/Form.xml" in got
    assert ("Reports/Продажи/Templates/ОсновнаяСхемаКомпоновкиДанных/"
            "Ext/Template.xml") in got


def test_service_config_dump_info_excluded(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Reports/Продажи.xml",
        "Reports/Продажи/Ext/ConfigDumpInfo.xml",
    ]
    cf_dir = tmp_path / "src" / "cf"
    for rel in files:
        path = cf_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got = mod.get_changed_files()

    assert "Reports/Продажи.xml" in got
    assert "Reports/Продажи/Ext/ConfigDumpInfo.xml" not in got
