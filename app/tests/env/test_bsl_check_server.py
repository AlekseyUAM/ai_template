"""Тесты чистого парсера отчёта BSL LS (`parse_report`) и обёртки `run_check`.

Модуль `bsl_check_server.py` лежит в `app/docker/mcp` и НЕ на pythonpath, поэтому
грузим его напрямую из файла через importlib. Тесты не требуют пакета `mcp` и
java — проверяется только чистая логика разбора отчёта и формирования ответа.
"""
import importlib.util
from pathlib import Path

_p = Path(__file__).resolve().parents[2] / "docker" / "mcp" / "bsl_check_server.py"
_spec = importlib.util.spec_from_file_location("bsl_check_server", _p)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _report(fileinfos):
    return {"date": "2026-10-06", "fileinfos": fileinfos, "sourceDir": "/tmp/src"}


def test_as_config_text_accepts_str_dict_and_none():
    import json
    assert mod._as_config_text(None) is None
    assert mod._as_config_text("") is None
    assert mod._as_config_text('{"language":"ru"}') == '{"language":"ru"}'
    out = mod._as_config_text({"language": "ru"})
    assert json.loads(out) == {"language": "ru"}


def test_empty_fileinfos_returns_empty():
    assert mod.parse_report(_report([]), "Module.bsl") == []


def test_no_fileinfos_key_is_robust():
    assert mod.parse_report({}, "Module.bsl") == []


def test_integer_severity_warning_and_1_based_positions():
    diag = {
        "range": {"start": {"line": 4, "character": 2},
                  "end": {"line": 4, "character": 10}},
        "severity": 2,
        "code": "LineLength",
        "source": "bsl-language-server",
        "message": "Строка слишком длинная",
    }
    out = mod.parse_report(_report([{"path": "Module.bsl", "diagnostics": [diag]}]), "Module.bsl")
    assert len(out) == 1
    item = out[0]
    assert item["severity"] == "Warning"
    assert item["line"] == 5 and item["column"] == 3
    assert item["endLine"] == 5 and item["endColumn"] == 11
    assert item["code"] == "LineLength"
    assert item["source"] == "bsl-language-server"
    assert item["message"] == "Строка слишком длинная"


def test_string_severity_error_preserved():
    diag = {"range": {"start": {"line": 0, "character": 0},
                      "end": {"line": 0, "character": 1}},
            "severity": "Error", "code": "Typo", "message": "опечатка"}
    out = mod.parse_report(_report([{"path": "Module.bsl", "diagnostics": [diag]}]), "Module.bsl")
    assert out[0]["severity"] == "Error"


def test_integer_severity_mapping_all():
    def one(sev):
        diag = {"range": {"start": {"line": 0, "character": 0},
                          "end": {"line": 0, "character": 0}}, "severity": sev}
        return mod.parse_report(_report([{"path": "M.bsl", "diagnostics": [diag]}]), "M.bsl")[0]["severity"]

    assert one(1) == "Error"
    assert one(2) == "Warning"
    assert one(3) == "Information"
    assert one(4) == "Hint"


def test_multiple_fileinfos_filtered_by_basename():
    fi = [
        {"path": "sub/dir/Module.bsl",
         "diagnostics": [{"range": {"start": {"line": 0, "character": 0},
                                    "end": {"line": 0, "character": 0}},
                          "severity": 1, "code": "A"}]},
        {"path": "other/Other.bsl",
         "diagnostics": [{"range": {"start": {"line": 0, "character": 0},
                                    "end": {"line": 0, "character": 0}},
                          "severity": 1, "code": "B"}]},
    ]
    out = mod.parse_report(_report(fi), "Module.bsl")
    assert [d["code"] for d in out] == ["A"]


def test_empty_filename_includes_all_files():
    fi = [
        {"path": "A.bsl", "diagnostics": [{"range": {"start": {"line": 0, "character": 0},
                                                     "end": {"line": 0, "character": 0}},
                                           "severity": 1, "code": "A"}]},
        {"path": "B.bsl", "diagnostics": [{"range": {"start": {"line": 0, "character": 0},
                                                     "end": {"line": 0, "character": 0}},
                                           "severity": 1, "code": "B"}]},
    ]
    assert {d["code"] for d in mod.parse_report(_report(fi), "")} == {"A", "B"}
    assert {d["code"] for d in mod.parse_report(_report(fi), None)} == {"A", "B"}


def test_sparse_diagnostic_missing_range_does_not_crash():
    fi = [{"path": "Module.bsl", "diagnostics": [{"severity": 2, "message": "нет range"}]}]
    out = mod.parse_report(_report(fi), "Module.bsl")
    assert len(out) == 1
    item = out[0]
    # отсутствующий range → безопасные значения, 1-based минимум
    assert item["line"] == 1 and item["column"] == 1
    assert item["severity"] == "Warning"
    assert item["code"] == ""
    assert item["message"] == "нет range"


def test_fileinfo_without_diagnostics_key():
    fi = [{"path": "Module.bsl"}]
    assert mod.parse_report(_report(fi), "Module.bsl") == []


# --- run_check с инъекцией fake-run (без java) --------------------------------

def test_run_check_ok_with_injected_run(tmp_path):
    report = _report([{"path": "Module.bsl", "diagnostics": [
        {"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
         "severity": 2, "code": "LineLength", "message": "длинно"}]}])

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # находим outputDir в аргументах и пишем туда отчёт
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(_json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", config=None, run=fake_run)
    assert res["ok"] is True
    assert res["count"] == 1
    assert res["diagnostics"][0]["code"] == "LineLength"
    assert "--reporter" in captured["cmd"] and "json" in captured["cmd"]
    # srcDir указывается, анализируется присланный текст
    assert "--srcDir" in captured["cmd"]


def test_run_check_no_report_returns_not_ok():
    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = "boom"
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", config=None, run=fake_run)
    assert res["ok"] is False
    assert res["count"] == 0
    assert res["diagnostics"] == []
    assert "boom" in res["summary"]


def test_run_check_writes_config_into_srcdir(tmp_path):
    """Переданный config кладётся в корень srcDir как .bsl-language-server.json."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        srcdir = Path(cmd[cmd.index("--srcDir") + 1])
        cfg = srcdir / ".bsl-language-server.json"
        captured["config_written"] = cfg.read_text(encoding="utf-8") if cfg.exists() else None
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(_json.dumps(_report([])), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    cfg_content = '{"language": "ru", "diagnostics": {"parameters": {"LineLength": {"maxLineLength": 20}}}}'
    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", config=cfg_content, run=fake_run)
    assert res["ok"] is True
    # флага -c нет: настройки берутся как per-workspace из srcDir
    assert "-c" not in captured["cmd"]
    assert captured["config_written"] == cfg_content


def test_run_check_no_config_writes_no_settings_file(tmp_path):
    """Без config файл .bsl-language-server.json в srcDir не создаётся."""
    captured = {}

    def fake_run(cmd, **kwargs):
        srcdir = Path(cmd[cmd.index("--srcDir") + 1])
        captured["has_config"] = (srcdir / ".bsl-language-server.json").exists()
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(_json.dumps(_report([])), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", config=None, run=fake_run)
    assert captured["has_config"] is False
