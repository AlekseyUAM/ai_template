"""Тесты чистого парсера отчёта BSL LS (`parse_report`) и обёртки `run_check`.

Модуль `bsl_check_server.py` лежит в `app/docker/mcp` и НЕ на pythonpath, поэтому
грузим его напрямую из файла через importlib. Тесты не требуют пакета `mcp` и
java — проверяется только чистая логика разбора отчёта и формирования ответа.
"""
import hashlib
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


def test_oversized_code_rejected_before_java():
    calls = []
    res = mod.run_check("x" * (mod.MAX_CODE_BYTES + 1), "Module.bsl",
                        jar="/opt/x.jar", run=lambda *a, **k: calls.append(1))
    assert res["ok"] is False and "слишком большой" in res["summary"]
    assert calls == []


def test_oversized_config_rejected():
    res = mod.run_check("код", "Module.bsl", jar="/opt/x.jar",
                        config="y" * (mod.MAX_CONFIG_BYTES + 1),
                        run=lambda *a, **k: None)
    assert res["ok"] is False and "config" in res["summary"]


def test_reserved_filename_rejected():
    res = mod.run_check("код", ".bsl-language-server.json", jar="/opt/x.jar",
                        run=lambda *a, **k: None)
    assert res["ok"] is False and "зарезервировано" in res["summary"]


def test_timeout_returns_error():
    import subprocess
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
    res = mod.run_check("код", "Module.bsl", jar="/opt/x.jar", run=fake_run)
    assert res["ok"] is False
    assert "таймаут" not in res["summary"]  # текст с "не завершился"
    assert "не завершился" in res["summary"]


# --- обязательный sha256, источники ввода и сырые counts ---------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_run_check_sha256_mismatch_rejected_before_java():
    calls = []
    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256="0" * 64,
                        run=lambda *a, **k: calls.append(1))
    assert res["ok"] is False
    assert "sha256" in res["summary"]
    assert calls == []


def test_run_check_sha256_match_ok():
    code = "Код"
    report = _report([])

    def fake_run(cmd, **kwargs):
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    res = mod.run_check(code, "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha(code), run=fake_run)
    assert res["ok"] is True
    assert res["sha256"] == _sha(code)


def test_prepare_input_requires_sha256():
    code, filename, expected, source, error = mod.prepare_input(
        code="x", file_path=None, sha256="", filename="Module.bsl")
    assert code is None
    assert "sha256" in error


def test_prepare_input_requires_exactly_one_source():
    code, filename, expected, source, error = mod.prepare_input(
        code="x", file_path="y", sha256="0" * 64, filename="Module.bsl")
    assert code is None
    assert "ровно один" in error


def test_prepare_input_reads_file(tmp_path):
    path = tmp_path / "Module.bsl"
    path.write_text("ВЫБРАТЬ 1", encoding="utf-8")
    code, filename, expected, source, error = mod.prepare_input(
        code=None, file_path=str(path), sha256=_sha("ВЫБРАТЬ 1"),
        filename="Module.bsl")
    assert error is None
    assert code == "ВЫБРАТЬ 1"
    assert filename == "Module.bsl"
    assert source == "file"


def test_prepare_input_missing_file(tmp_path):
    code, filename, expected, source, error = mod.prepare_input(
        code=None, file_path=str(tmp_path / "nope.bsl"),
        sha256="0" * 64, filename="Module.bsl")
    assert code is None
    assert "file_path" in error


BOM = "﻿"


def test_prepare_input_bom_accepts_raw_sha_and_keeps_code():
    raw = BOM + "ВЫБРАТЬ 1"
    code, filename, expected, source, error = mod.prepare_input(
        code=raw, file_path=None, sha256=_sha(raw), filename="Module.bsl")
    assert error is None
    assert code == raw  # BOM срезает run_check (для bom_removed/raw_sha256)
    assert expected == _sha("ВЫБРАТЬ 1")
    assert source == "code"


def test_prepare_input_file_bom_accepts_file_sha(tmp_path):
    path = tmp_path / "Module.bsl"
    raw = BOM + "ВЫБРАТЬ 1"
    path.write_bytes(raw.encode("utf-8"))
    code, filename, expected, source, error = mod.prepare_input(
        code=None, file_path=str(path), sha256=_sha(raw),
        filename="Module.bsl")
    assert error is None
    assert code == raw
    assert expected == _sha("ВЫБРАТЬ 1")
    assert source == "file"


def _fake_json_run(report):
    def fake_run(cmd, **kwargs):
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()
    return fake_run


def test_run_check_bom_accepts_raw_sha_and_strips_bom():
    raw = BOM + "Код"
    res = mod.run_check(raw, "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha(raw),
                        run=_fake_json_run(_report([])))
    assert res["ok"] is True
    assert res["sha256"] == _sha("Код")
    assert res["raw_sha256"] == _sha(raw)
    assert res["bom_removed"] is True


def test_run_check_bom_accepts_normalized_sha():
    raw = BOM + "Код"
    res = mod.run_check(raw, "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha("Код"),
                        run=_fake_json_run(_report([])))
    assert res["ok"] is True
    assert res["sha256"] == _sha("Код")
    assert res["bom_removed"] is True


def test_run_check_bom_mismatch_rejected_before_java():
    calls = []
    res = mod.run_check(BOM + "Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256="0" * 64,
                        run=lambda *a, **k: calls.append(1))
    assert res["ok"] is False
    assert "sha256" in res["summary"]
    assert calls == []


# --- завершающий перевод строки: хэш файла и хэш присланного текста ----------

def test_prepare_input_file_newline_code_without_newline_accepted(tmp_path):
    """Файл оканчивается `\\n`, code прислан без него — хэш файла принимается."""
    path = tmp_path / "Module.bsl"
    path.write_text("ВЫБРАТЬ 1\n", encoding="utf-8")
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    code, filename, expected, source, error = mod.prepare_input(
        code="ВЫБРАТЬ 1", file_path=None, sha256=file_sha, filename="Module.bsl")
    assert error is None
    assert code == "ВЫБРАТЬ 1"
    assert expected == _sha("ВЫБРАТЬ 1")
    assert source == "code"


def test_prepare_input_code_with_extra_newline_accepted(tmp_path):
    """Code прислан с лишним `\\n` в конце — хэш без него принимается."""
    path = tmp_path / "Module.bsl"
    path.write_text("ВЫБРАТЬ 1", encoding="utf-8")
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    code, filename, expected, source, error = mod.prepare_input(
        code="ВЫБРАТЬ 1\n", file_path=None, sha256=file_sha, filename="Module.bsl")
    assert error is None
    assert code == "ВЫБРАТЬ 1\n"
    assert expected == _sha("ВЫБРАТЬ 1\n")
    assert source == "code"


def test_prepare_input_newline_tolerance_keeps_bom_variants(tmp_path):
    """BOM и завершающий `\\n` сочетаются: хэш файла принимается."""
    path = tmp_path / "Module.bsl"
    path.write_bytes((BOM + "ВЫБРАТЬ 1\n").encode("utf-8"))
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    code, filename, expected, source, error = mod.prepare_input(
        code=BOM + "ВЫБРАТЬ 1", file_path=None, sha256=file_sha,
        filename="Module.bsl")
    assert error is None
    assert expected == _sha("ВЫБРАТЬ 1")


def test_prepare_input_mismatched_hash_still_rejected():
    code, filename, expected, source, error = mod.prepare_input(
        code="ВЫБРАТЬ 1", file_path=None, sha256=_sha("ВЫБРАТЬ 2"),
        filename="Module.bsl")
    assert code is None
    assert "sha256" in error


def test_run_check_newline_tolerance_and_normalized_sha():
    """run_check принимает хэш варианта с `\\n`; в ответе — хэш присланного текста."""
    report = _report([])
    code = "Код"

    res = mod.run_check(code, "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha(code + "\n"),
                        run=_fake_json_run(report))
    assert res["ok"] is True
    assert res["sha256"] == _sha(code)

    res = mod.run_check(code + "\n", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha(code), run=_fake_json_run(report))
    assert res["ok"] is True
    assert res["sha256"] == _sha(code + "\n")


def test_run_check_newline_tolerance_mismatch_still_rejected():
    calls = []
    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha("Другой\n"),
                        run=lambda *a, **k: calls.append(1))
    assert res["ok"] is False
    assert "sha256" in res["summary"]
    assert calls == []


# --- один повтор на транзиентный сбой старта Spring ---------------------------

def test_run_check_retries_once_on_bean_creation_exception():
    import json as _json
    calls = []
    report = _report([])

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        if len(calls) == 1:
            _R.returncode = 1
            _R.stderr = ("org.springframework.beans.factory.BeanCreationException: "
                         "Error creating bean with name 'bslLanguageServer'")
            return _R()
        outdir = Path(cmd[cmd.index("--outputDir") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", run=fake_run)
    assert res["ok"] is True
    assert len(calls) == 2


def test_run_check_does_not_retry_non_spring_failure():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class _R:
            returncode = 1
            stdout = ""
            stderr = "ParseError: ожидается выражение"
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar", run=fake_run)
    assert res["ok"] is False
    assert "ParseError" in res["summary"]
    assert len(calls) == 1


def test_counts_in_result():
    report = _report([{"path": "Module.bsl", "diagnostics": [
        {"range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 1}},
         "severity": 1, "code": "E"},
        {"range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 0, "character": 1}},
         "severity": 2, "code": "W"},
    ]}])

    def fake_run(cmd, **kwargs):
        import json as _json
        outdir = cmd[cmd.index("--outputDir") + 1]
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "bsl-json.json").write_text(
            _json.dumps(report), encoding="utf-8")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""
        return _R()

    res = mod.run_check("Код", "Module.bsl", jar="/opt/x.jar",
                        expected_sha256=_sha("Код"), run=fake_run)
    assert res["counts"]["Error"] == 1
    assert res["counts"]["Warning"] == 1


# --- публичный инструмент check (build_server с подставным FastMCP) ----------

def _build_check_tool(monkeypatch):
    """Собрать сервер с подставным пакетом `mcp` и вернуть инструмент `check`.

    Пакет `mcp` не установлен в venv, поэтому подменяем `mcp.server.fastmcp`
    минимальным FastMCP, который запоминает декорированные функции.
    """
    import sys
    import types

    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            self.tools = {}

        def tool(self, *args, **kwargs):
            def decorator(fn):
                self.tools[fn.__name__] = fn
                return fn
            return decorator

    fastmcp = types.ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = _FakeFastMCP
    mcp_pkg = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_server.fastmcp = fastmcp
    mcp_pkg.server = mcp_server
    monkeypatch.setitem(sys.modules, "mcp", mcp_pkg)
    monkeypatch.setitem(sys.modules, "mcp.server", mcp_server)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp)
    return mod.build_server().tools["check"]


def test_check_requires_sha256(monkeypatch):
    check = _build_check_tool(monkeypatch)
    calls = []
    monkeypatch.setattr(mod, "run_check", lambda *a, **k: calls.append((a, k)))

    res = check(sha256="", code="x")
    assert res["ok"] is False
    assert "sha256" in res["summary"]
    assert calls == []


def test_check_sha256_cannot_be_omitted(monkeypatch):
    """sha256 — обязательный позиционный параметр: без него TypeError."""
    import pytest

    check = _build_check_tool(monkeypatch)
    with pytest.raises(TypeError):
        check(code="x")


def test_check_valid_sha_calls_run_check(monkeypatch):
    check = _build_check_tool(monkeypatch)
    stub = {"ok": True}
    calls = []
    monkeypatch.setattr(
        mod, "run_check",
        lambda *a, **k: calls.append((a, k)) or stub)

    sha = _sha("x")
    res = check(sha256=sha, code="x")
    assert res is stub
    assert len(calls) == 1
    assert calls[0][1]["expected_sha256"] == sha


def test_check_missing_file_path_errors(monkeypatch, tmp_path):
    check = _build_check_tool(monkeypatch)
    calls = []
    monkeypatch.setattr(mod, "run_check", lambda *a, **k: calls.append((a, k)))

    res = check(sha256=_sha("x"), file_path=str(tmp_path / "nope.bsl"))
    assert res["ok"] is False
    assert "file_path" in res["summary"]
    assert calls == []
