"""Регрессия частичной загрузки: новый объект с формами/макетами.

Раньше load-config-optimized.py сводил любой подфайл к корню объекта. Для
нового отчёта этого мало: корневой XML ссылается на Form/Template, а сами
файлы-декларации в -listFile не попадали — платформа падала с «Неизвестный
объект метаданных». Здесь проверяем, что список содержит и корень, и файлы
форм/макетов (включая их Ext-содержимое).
"""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPT = (Path(__file__).resolve().parents[3] / "template" / ".claude" /
          "tools" / "load-config-optimized.py")


def _load():
    spec = importlib.util.spec_from_file_location("load_config_optimized", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Регистрация в sys.modules обязательна: dataclasses (3.12+) при обработке
    # строковых аннотаций берут cls.__module__ из sys.modules; без записи
    # получают None и падают с AttributeError на @dataclass.
    sys.modules["load_config_optimized"] = mod
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


def test_get_dirty_paths_normalizes_dedupes_and_filters(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([
        "src/cf/Catalogs/Товары.xml",
        "src/cf/Catalogs/Товары.xml",
        "src/cf/Catalogs/Товары/Ext/ConfigDumpInfo.xml",
    ]))
    monkeypatch.chdir(tmp_path)

    assert mod.get_dirty_paths() == ["Catalogs/Товары.xml"]


def test_expand_to_load_paths_adds_object_root_and_ext(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
    ]
    for rel in files:
        path = tmp_path / "src" / "cf" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)

    got = mod.expand_to_load_paths(["Catalogs/Товары/Ext/ObjectModule.bsl"])

    assert set(got) == set(files)


def test_file_sha256_missing_returns_none(tmp_path):
    mod = _load()
    assert mod.file_sha256(tmp_path / "нет-такого") is None


def test_save_and_load_state_roundtrip(tmp_path):
    mod = _load()
    path = tmp_path / "logs" / "task#1" / "load-state.json"
    files = {"Catalogs/Товары.xml": "abc", "Configuration.xml": "def"}

    mod.save_state(str(path), files)

    assert mod.load_state(str(path)) == files
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["hash"] == "sha256"
    assert data["files"] == files


def test_load_state_tolerates_missing_and_broken(tmp_path):
    mod = _load()
    assert mod.load_state(None) == {}
    assert mod.load_state(str(tmp_path / "absent.json")) == {}

    broken = tmp_path / "broken.json"
    broken.write_text("{oops", encoding="utf-8")
    assert mod.load_state(str(broken)) == {}

    broken.write_text(json.dumps({"version": 99, "files": {"a": "b"}}),
                      encoding="utf-8")
    assert mod.load_state(str(broken)) == {}


def _write_cf(root, rels):
    cf_dir = root / "src" / "cf"
    for rel in rels:
        path = cf_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")


def _hashes(mod, root, rels):
    cf_dir = root / "src" / "cf"
    return {rel: mod.file_sha256(cf_dir / rel) for rel in rels}


def test_collect_changes_skips_unchanged_metadata_and_configuration(
        tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Configuration.xml",
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
    ]
    _write_cf(tmp_path, files)
    state = _hashes(mod, tmp_path, files)

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got, snapshot, deleted, skipped = mod.collect_changes(state)

    assert got == []
    assert deleted == []
    assert set(skipped) == set(files)
    assert snapshot == state


def test_collect_changes_loads_only_changed_module(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Configuration.xml",
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
        "Catalogs/Услуги.xml",
        "Catalogs/Услуги/Ext/ObjectModule.bsl",
    ]
    _write_cf(tmp_path, files)
    state = _hashes(mod, tmp_path, files)
    (tmp_path / "src" / "cf" / "Catalogs/Товары/Ext/ObjectModule.bsl"
     ).write_text("// изменено\n", encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got, _snapshot, _deleted, _skipped = mod.collect_changes(state)

    assert "Configuration.xml" not in got
    assert "Catalogs/Товары/Ext/ObjectModule.bsl" in got
    assert "Catalogs/Товары.xml" in got          # корень изменённого объекта
    assert "Catalogs/Услуги.xml" not in got      # чужой объект не тронут


def test_collect_changes_detects_revert_to_head(tmp_path, monkeypatch):
    mod = _load()
    rel = "Catalogs/Товары.xml"
    _write_cf(tmp_path, [rel])

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))  # файл откатили к HEAD

    monkeypatch.chdir(tmp_path)

    got, _snapshot, _deleted, _skipped = mod.collect_changes({rel: "0" * 64})

    assert got == [rel]


def test_collect_changes_forgets_deleted_state_file(tmp_path, monkeypatch):
    mod = _load()
    missing = "Catalogs/Старый/Ext/OldModule.bsl"

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))
    monkeypatch.chdir(tmp_path)

    got, snapshot, deleted, skipped = mod.collect_changes({missing: "0" * 64})

    assert got == []
    assert deleted == [missing]
    assert missing not in snapshot
    assert skipped == []


def test_main_saves_state_after_successful_load(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    calls = []

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load",
                        lambda fs, allow_warnings=False: calls.append(fs) or 0)
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "logs" / "task#1" / "load-state.json"

    rc = mod.main(["--state", str(state_path)])

    assert rc == 0
    assert calls == [["Configuration.xml", "Catalogs/Товары.xml"]]
    assert mod.load_state(str(state_path)) == _hashes(mod, tmp_path, files)


def test_main_keeps_state_on_failed_load(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    state_path = tmp_path / "load-state.json"
    mod.save_state(str(state_path), {"Configuration.xml": "0" * 64})
    before = state_path.read_text(encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load",
                        lambda fs, allow_warnings=False: 1)
    monkeypatch.chdir(tmp_path)

    rc = mod.main(["--state", str(state_path)])

    assert rc == 1
    assert state_path.read_text(encoding="utf-8") == before


def test_main_updates_state_when_nothing_to_load(tmp_path, monkeypatch):
    mod = _load()
    state_path = tmp_path / "load-state.json"
    mod.save_state(str(state_path), {"Catalogs/Старый/Ext/Old.bsl": "0" * 64})

    def _must_not_load(files, allow_warnings=False):
        raise AssertionError("загрузка не нужна")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))
    monkeypatch.setattr(mod, "run_optimized_load", _must_not_load)
    monkeypatch.chdir(tmp_path)

    rc = mod.main(["--state", str(state_path)])

    assert rc == 0
    assert mod.load_state(str(state_path)) == {}


def test_main_without_state_uses_full_diff(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    calls = []

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load",
                        lambda fs, allow_warnings=False: calls.append(fs) or 0)
    monkeypatch.chdir(tmp_path)

    rc = mod.main([])

    assert rc == 0
    assert calls == [["Configuration.xml", "Catalogs/Товары.xml"]]


def test_main_rejects_directory_as_state(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.chdir(tmp_path)

    assert mod.main(["--state", str(tmp_path)]) == 2


# ── Предупреждения платформы: проигнорированные свойства ─────────────────────
# Строки ниже — из реального лога benchmark task##001: агент скопировал свойства
# измерения регистра сведений в регистр накопления. Платформа их молча
# проигнорировала (5 измерений × 6 свойств + 5 ресурсов × 4 свойства), а загрузка
# при этом завершилась кодом 0.

_DIM_PROPS = ("FillFromFillingValue", "FillValue", "Master", "MainFilter",
              "DataHistory", "TypeReductionMode")
_RES_PROPS = ("FillFromFillingValue", "FillValue", "Indexing", "DataHistory")


def _property_warning(prop, kind):
    return (f"Неверное свойство объекта метаданных. Свойство {prop} не входит в "
            f"состав объекта метаданных {kind}. - {prop}")


def _real_warning_lines(count=5):
    """Строки реального лога: по 5 регистров.

    5 измерений × 6 свойств = 30 Dimension + 5 ресурсов × 4 свойства =
    20 Resource; итого count × 10 = 50 строк при count=5 (как в логе task##001).
    """
    lines = []
    for _ in range(count):
        lines.extend(_property_warning(p, "Dimension") for p in _DIM_PROPS)
        lines.extend(_property_warning(p, "Resource") for p in _RES_PROPS)
    return lines


def test_platform_warnings_groups_real_log():
    mod = _load()
    text = "\n".join(
        ["Запуск: 1cv8 DESIGNER /LoadConfigFromFiles src/cf"]
        + _real_warning_lines()
        + ["Обработка структуры базы данных...",
           "Обновление конфигурации успешно завершено"]
    )

    warn = mod.platform_warnings(text)

    assert warn.count == 50
    assert warn.groups == {
        ("Dimension", "FillFromFillingValue"): 5,
        ("Dimension", "FillValue"): 5,
        ("Dimension", "Master"): 5,
        ("Dimension", "MainFilter"): 5,
        ("Dimension", "DataHistory"): 5,
        ("Dimension", "TypeReductionMode"): 5,
        ("Resource", "FillFromFillingValue"): 5,
        ("Resource", "FillValue"): 5,
        ("Resource", "Indexing"): 5,
        ("Resource", "DataHistory"): 5,
    }
    assert sum(warn.groups.values()) == 50


def test_platform_warnings_clean_output():
    mod = _load()
    text = "\n".join([
        "Обработка структуры базы данных...",
        "Новый объект: РегистрНакопления.Товары",
        "Обновление конфигурации успешно завершено",
        "✅ Оптимизированная загрузка завершена",
    ])

    warn = mod.platform_warnings(text)

    assert warn.count == 0
    assert warn.groups == {}
    assert warn.other == []


def test_platform_warnings_marks_non_property_warnings():
    mod = _load()
    text = "\n".join([
        _property_warning("Indexing", "Resource"),
        "Неверное значение перечисления - Don'tUse",
        "Неверное значение перечисления - Don'tUse",
        "Исключение XDTO произошло при чтении файла- /x/src/cf/Catalogs/Организации.xml.",
        "facet фиксации ControlType не соответствует",
    ])

    warn = mod.platform_warnings(text)

    assert warn.count == 5
    assert warn.groups == {("Resource", "Indexing"): 1}
    assert warn.other == [
        ("Неверное значение перечисления", 2),
        ("Исключение XDTO", 1),
        ("facet", 1),
    ]
    assert sum(v for _m, v in warn.other) + sum(warn.groups.values()) == warn.count


def test_platform_warnings_facet_path_is_not_a_warning():
    """Путь/слово с «facet» (FacetGroups.xml) — не предупреждение платформы."""
    mod = _load()
    text = "\n".join([
        "Загрузка: src/cf/CommonPictures/FacetGroups.xml",
        "Чтение FacetGroups.xml — ok",
        "Неверное значение перечисления - Don'tUse",
    ])

    warn = mod.platform_warnings(text)

    assert warn.other == [("Неверное значение перечисления", 1)]
    assert warn.count == 1


def test_platform_warnings_property_line_counted_once():
    """Строка с маркером свойства не учитывается ещё и как «прочее»."""
    mod = _load()
    text = _property_warning("Indexing", "Resource")

    warn = mod.platform_warnings(text)

    assert warn.count == 1
    assert warn.groups == {("Resource", "Indexing"): 1}
    assert warn.other == []


def test_facet_marker_requires_platform_phrasing():
    mod = _load()
    assert mod.platform_warnings("facet фиксации ControlType x").count == 1
    assert mod.platform_warnings("facet of control x").count == 0


def _fake_load(monkeypatch, mod, stdout="", returncode=0):
    """Подмени subprocess.run для git (один изменённый объект) и 1c-batch.

    Возвращает путь изменённого объекта и список вызовов. Configuration.xml
    не годится: при наличии state он не попадает в список (полная загрузка),
    а без state — годится, но объект нагляднее.
    """
    changed = "Catalogs/Товары.xml"
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if "diff" in cmd:
            return _Completed("")
        if "ls-files" in cmd:
            return _Completed(f"src/cf/{changed}")
        if "load-config" in cmd:
            assert kwargs.get("capture_output") is True
            assert kwargs.get("encoding") == "utf-8"
            assert kwargs.get("errors") == "replace"
            return _Completed(stdout, returncode)
        raise AssertionError(f"неожиданный вызов: {cmd}")

    monkeypatch.setattr(mod, "subprocess", SimpleNamespace(run=run))
    return changed, calls


def _state_setup(tmp_path, monkeypatch):
    """Каталог проекта с одним изменённым объектом; вернуть (mod, state_path)."""
    mod = _load()
    _write_cf(tmp_path, ["Catalogs/Товары.xml"])
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    return mod, tmp_path / "logs" / "task#1" / "load-state.json"


def test_real_log_file_groups_50_warnings():
    """Настоящий лог task##001 (если есть рядом): ровно 50, 30+20."""
    log = Path("/home/uam/projects/test2/logs/task##001/load-config.log")
    if not log.exists():
        import pytest
        pytest.skip("реальный лог task##001 недоступен")
    mod = _load()

    warn = mod.platform_warnings(log.read_text(encoding="utf-8",
                                               errors="replace"))

    assert warn.count == 50
    assert sum(v for (k, _p), v in warn.groups.items() if k == "Dimension") == 30
    assert sum(v for (k, _p), v in warn.groups.items() if k == "Resource") == 20
    assert len(warn.groups) == 10
    assert all(v == 5 for v in warn.groups.values())
    assert warn.other == []


def test_load_warnings_block_success_and_state(tmp_path, monkeypatch, capsys):
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    changed, calls = _fake_load(monkeypatch, mod,
                                stdout="\n".join(_real_warning_lines()))

    rc = mod.main(["--state", str(state_path)])

    out = capsys.readouterr().out
    # Загрузка действительно шла: child load-config вызван для изменённого объекта.
    assert any("load-config" in c for c in calls)
    assert changed in out
    assert rc == 2
    assert "⚠️ Платформа проигнорировала 50 свойств" in out
    assert "Dimension FillFromFillingValue: 5" in out
    assert "Resource Indexing: 5" in out
    assert "Оптимизированная загрузка завершена" not in out
    assert not state_path.exists()


def test_load_warnings_prints_other_block(tmp_path, monkeypatch, capsys):
    """Свойства и прочие предупреждения — разные блоки и счётчики."""
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    _fake_load(monkeypatch, mod, stdout="\n".join([
        _property_warning("Indexing", "Resource"),
        "Неверное значение перечисления - Don'tUse",
    ]))

    rc = mod.main(["--state", str(state_path)])

    out = capsys.readouterr().out
    assert rc == 2
    assert "⚠️ Платформа проигнорировала 1 свойств" in out
    assert "  - Resource Indexing: 1" in out
    assert "Прочие предупреждения платформы (1)" in out
    assert "  - Неверное значение перечисления: 1" in out
    # раздельные счётчики: заголовок свойств показывает только свойства
    property_block = out.split("Прочие предупреждения платформы")[0]
    property_block = property_block[property_block.index("Платформа проигнорировала"):]
    assert property_block.count(": 1") == 1
    # точная строка вердикта (rc 2) печатается отдельной строкой
    assert ("❌ Загрузка применена, но исходники некорректны: платформа "
            "проигнорировала перечисленные свойства. Исправь их или "
            "запусти с --allow-warnings, если это осознанно.") in out


def test_load_facet_path_does_not_fail(tmp_path, monkeypatch, capsys):
    """FacetGroups.xml в логе не делает загрузку ошибочной."""
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    _fake_load(monkeypatch, mod, stdout="Чтение src/cf/FacetGroups.xml — ok")

    rc = mod.main(["--state", str(state_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "исходники некорректны" not in out
    assert state_path.exists()


def test_load_warnings_checkpoint_state_kept(tmp_path, monkeypatch, capsys):
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    mod.save_state(str(state_path), {"Catalogs/Товары.xml": "0" * 64})
    before = state_path.read_text(encoding="utf-8")
    _fake_load(monkeypatch, mod,
               stdout=_property_warning("Indexing", "Resource"))

    rc = mod.main(["--state", str(state_path)])

    assert rc == 2
    assert state_path.read_text(encoding="utf-8") == before


def test_load_warnings_allowed_with_flag(tmp_path, monkeypatch, capsys):
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    _fake_load(monkeypatch, mod, stdout=_property_warning("Indexing", "Resource"))

    rc = mod.main(["--state", str(state_path), "--allow-warnings"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "✅ Оптимизированная загрузка завершена" in out
    assert "(с предупреждениями, --allow-warnings)" in out
    assert state_path.exists()
    assert "Catalogs/Товары.xml" in mod.load_state(str(state_path))


def test_clean_load_succeeds_and_saves_state(tmp_path, monkeypatch, capsys):
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    _fake_load(monkeypatch, mod, stdout="Обновление конфигурации успешно завершено")

    rc = mod.main(["--state", str(state_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "✅ Оптимизированная загрузка завершена" in out
    assert "с предупреждениями" not in out
    assert "⚠️ Платформа проигнорировала" not in out
    assert state_path.exists()


def test_child_failure_code_preserved_with_summary(tmp_path, monkeypatch, capsys):
    mod, state_path = _state_setup(tmp_path, monkeypatch)
    _fake_load(monkeypatch, mod, stdout=_property_warning("Indexing", "Resource"),
               returncode=1)

    rc = mod.main(["--state", str(state_path), "--allow-warnings"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "❌ Ошибка при загрузке конфигурации" in out
    assert "⚠️ Платформа проигнорировала 1 свойств" in out
    assert "Оптимизированная загрузка завершена" not in out
    assert not state_path.exists()
