"""Тонкий MCP-сервер для образа «Статический анализ BSL».

Экспортирует ровно один инструмент `check`: принимает текст кода BSL (и
обязательный SHA-256 файла) и возвращает диагностики (ошибки/предупреждения) по
настройкам `.bsl-language-server.json`. Сервер stateless — без индекса и доступа к
кодовой базе: каждый вызов гоняет BSL Language Server в режиме CLI `analyze` с
json-репортёром по присланному тексту. Альтернатива тексту — `file_path`: сервер
читает файл сам, но только если путь виден из контейнера.

Функции `parse_report`, `prepare_input` и `run_check` специально не зависят от
пакета `mcp` и легко тестируются без java. Импорт FastMCP выполняется лениво в
`build_server()`.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Соответствие числовых уровней lsp4j DiagnosticSeverity именам.
_SEVERITY_BY_INT = {1: "Error", 2: "Warning", 3: "Information", 4: "Hint"}
# Нормализация строковых вариантов (в т.ч. сокращённого "Warn").
_SEVERITY_BY_STR = {
    "error": "Error",
    "warning": "Warning",
    "warn": "Warning",
    "information": "Information",
    "info": "Information",
    "hint": "Hint",
}

# Лимиты одного вызова: защита MCP-сервера от гигантского ввода и зависшей java.
MAX_CODE_BYTES = 5 * 1024 * 1024
MAX_CONFIG_BYTES = 1 * 1024 * 1024
ANALYZE_TIMEOUT_SECONDS = 300
_RESERVED_FILENAMES = {".bsl-language-server.json"}

# SHA-256 в hex: 64 символа (регистр нормализуется к нижнему).
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _severity_name(raw) -> str:
    """Привести severity (int или строку) к имени уровня.

    lsp4j может сериализовать severity числом (1=Error … 4=Hint) или именем.
    Неизвестные значения возвращаются как есть (приведённые к строке).
    """
    if isinstance(raw, bool):  # bool — подкласс int, не трактуем как уровень
        return str(raw)
    if isinstance(raw, int):
        return _SEVERITY_BY_INT.get(raw, str(raw))
    if isinstance(raw, str):
        return _SEVERITY_BY_STR.get(raw.strip().lower(), raw)
    return "" if raw is None else str(raw)


def parse_report(report: dict, filename: str) -> list[dict]:
    """Разобрать отчёт `bsl-json.json` в список диагностик для указанного файла.

    Фильтрация по basename пути из `fileinfos[].path`. Если `filename` пустой или
    None — попадают диагностики всех файлов. LSP-координаты (0-based line/character)
    переводятся в 1-based line/column. Функция устойчива к разреженным отчётам:
    отсутствующие ключи заменяются безопасными значениями и не вызывают исключений.

    Структура элемента результата:
    `{line, column, endLine, endColumn, severity, code, source, message}`.
    """
    report = report or {}
    fileinfos = report.get("fileinfos") or []
    want = Path(filename).name if filename else None

    result: list[dict] = []
    for info in fileinfos:
        info = info or {}
        if want is not None and Path(info.get("path") or "").name != want:
            continue
        for diag in info.get("diagnostics") or []:
            diag = diag or {}
            rng = diag.get("range") or {}
            start = rng.get("start") or {}
            end = rng.get("end") or {}
            result.append({
                "line": int(start.get("line", 0)) + 1,
                "column": int(start.get("character", 0)) + 1,
                "endLine": int(end.get("line", 0)) + 1,
                "endColumn": int(end.get("character", 0)) + 1,
                "severity": _severity_name(diag.get("severity")),
                "code": str(diag.get("code") or ""),
                "source": str(diag.get("source") or ""),
                "message": str(diag.get("message") or ""),
            })
    return result


def _as_config_text(config) -> str | None:
    """Нормализовать настройки в текст `.bsl-language-server.json`.

    Клиент может прислать настройки как строку-JSON или как объект (MCP-слой иногда
    десериализует JSON-строку в dict) — приводим к тексту для записи в файл.
    """
    if config is None or isinstance(config, str):
        return config or None
    return json.dumps(config, ensure_ascii=False)


def _summary(diagnostics: list[dict]) -> str:
    """Человекочитаемая сводка: сколько ошибок/предупреждений и пр."""
    if not diagnostics:
        return "Замечаний не найдено."
    counts: dict[str, int] = {}
    for d in diagnostics:
        counts[d["severity"]] = counts.get(d["severity"], 0) + 1
    parts = [f"{name}: {n}" for name, n in sorted(counts.items())]
    return f"Найдено замечаний: {len(diagnostics)} ({', '.join(parts)})."


def _sha256_hex(text: str) -> str:
    """SHA-256 текста в UTF-8 (как `sha256sum` по файлу в той же кодировке)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _counts(diagnostics: list[dict]) -> dict:
    """Сырые счётчики по уровням severity (нули для отсутствующих уровней)."""
    counts = {"Error": 0, "Warning": 0, "Information": 0, "Hint": 0}
    for diag in diagnostics:
        severity = diag.get("severity") or ""
        if severity in counts:
            counts[severity] += 1
    return counts


def _result(*, ok: bool, summary: str, sha256: str, source: str,
            raw_bytes: int, diagnostics: list[dict] | None = None) -> dict:
    """Единый формат ответа: ok/count/counts/diagnostics/summary/sha256/source/bytes."""
    diagnostics = diagnostics or []
    return {"ok": ok, "count": len(diagnostics),
            "counts": _counts(diagnostics), "diagnostics": diagnostics,
            "summary": summary, "sha256": sha256, "source": source,
            "bytes": raw_bytes}


def prepare_input(code, file_path, sha256, filename):
    """Проверить аргументы check и вернуть (code, filename, sha, source, error)."""
    expected = str(sha256 or "").strip().lower()
    if not expected:
        return None, filename, expected, "code", (
            "sha256 обязателен: вычисли его по файлу "
            "(sha256sum Module.bsl) и передай вместе с code.")
    if not _SHA256_RE.match(expected):
        return None, filename, expected, "code", (
            "sha256 должен быть 64 hex-символа.")
    if (code is None) == (file_path is None):
        return None, filename, expected, "code", (
            "передайте ровно один источник: code или file_path.")
    source = "code"
    if file_path is not None:
        try:
            code = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            return None, filename, expected, "file", (
                f"не удалось прочитать file_path: {exc}. В Docker-контейнере "
                f"путь проекта не виден — передайте code+sha256.")
        source = "file"
        if filename == "Module.bsl":
            filename = Path(file_path).name
    return code, filename, expected, source, None


def run_check(code: str, filename: str, jar: str, config: str | None = None,
              java: str = "java", run=subprocess.run,
              expected_sha256: str | None = None,
              source: str = "code") -> dict:
    """Проверить присланный код BSL через CLI `analyze` BSL Language Server.

    Пишет `code` во временный `src/<filename>`. Если передан `config` (содержимое
    файла `.bsl-language-server.json` из корня проекта) — кладёт его в корень того
    же временного каталога как `.bsl-language-server.json`; BSL LS подхватывает его
    как per-workspace-настройки проверок. Запускает json-репортёр и парсит
    `bsl-json.json`. Параметр `run` (по умолчанию `subprocess.run`) позволяет
    подменить запуск в тестах без java. Временный каталог всегда удаляется.

    Если передан `expected_sha256` — он должен быть 64 hex и совпасть с SHA-256
    `code`; иначе `ok=False` и java не запускается. Внутренний вызов может не
    передавать хэш (`None`) — обязательность обеспечивает публичный `check`.

    Сервер stateless: никакого доступа к кодовой базе проекта — только присланные
    код и настройки. Возвращает `{ok, count, counts, diagnostics, summary, sha256,
    source, bytes}`; при ошибке запуска или отсутствии отчёта — `ok=False` и текст
    ошибки/stderr в `summary`.
    """
    code = code if isinstance(code, str) else str(code or "")
    raw_bytes = len(code.encode("utf-8"))
    actual_sha = _sha256_hex(code)
    if expected_sha256 is not None:
        expected = str(expected_sha256).strip().lower()
        if not _SHA256_RE.match(expected):
            return _result(ok=False, summary="sha256 должен быть 64 hex-символа.",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        if actual_sha != expected:
            return _result(
                ok=False,
                summary=(f"sha256 не совпадает: передан {expected}, фактический "
                         f"{actual_sha}. Текст не соответствует файлу — не "
                         f"перепечатывай модуль, передай его как есть."),
                sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    if raw_bytes > MAX_CODE_BYTES:
        return _result(ok=False,
                       summary=f"код слишком большой (> {MAX_CODE_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    if config and len(config.encode("utf-8")) > MAX_CONFIG_BYTES:
        return _result(ok=False,
                       summary=f"config слишком большой (> {MAX_CONFIG_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    filename = Path(filename or "Module.bsl").name or "Module.bsl"
    if filename in _RESERVED_FILENAMES:
        return _result(ok=False,
                       summary=f"имя файла {filename!r} зарезервировано под настройки анализа",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes)
    tmp = tempfile.mkdtemp(prefix="bsl-check-")
    try:
        srcdir = Path(tmp) / "src"
        outdir = Path(tmp) / "out"
        srcdir.mkdir(parents=True, exist_ok=True)
        (srcdir / filename).write_text(code, encoding="utf-8")
        # Настройки проверок кладём в корень workspace-папки (srcDir) — BSL LS
        # читает `.bsl-language-server.json` оттуда автоматически.
        if config:
            (srcdir / ".bsl-language-server.json").write_text(config, encoding="utf-8")

        cmd = [java, "-jar", jar, "analyze",
               "--srcDir", str(srcdir),
               "--outputDir", str(outdir),
               "--reporter", "json"]

        try:
            proc = run(cmd, capture_output=True, text=True,
                       timeout=ANALYZE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return _result(ok=False,
                           summary=f"BSL LS не завершился за {ANALYZE_TIMEOUT_SECONDS} с",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)
        except Exception as exc:  # java не найдена и т.п.
            return _result(ok=False,
                           summary=f"Не удалось запустить BSL LS: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)

        report_path = outdir / "bsl-json.json"
        if not report_path.exists():
            stderr = (getattr(proc, "stderr", "") or "").strip()
            code_ = getattr(proc, "returncode", "?")
            return _result(ok=False,
                           summary=stderr or f"Отчёт не создан (код возврата {code_}).",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return _result(ok=False, summary=f"Не удалось прочитать отчёт: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes)

        diagnostics = parse_report(report, filename)
        return _result(ok=True, summary=_summary(diagnostics),
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                       diagnostics=diagnostics)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_server():
    """Собрать FastMCP-сервер с единственным инструментом `check`.

    Импорт `mcp` выполняется здесь (лениво), чтобы `parse_report`/`run_check`
    можно было импортировать в тестах без установленного пакета `mcp`.
    """
    from mcp.server.fastmcp import FastMCP

    port = int(os.environ.get("BSL_PORT", "8001"))
    jar = os.environ.get("BSL_JAR", "/opt/bsl-language-server.jar")

    mcp = FastMCP("bsl_ls", host="0.0.0.0", port=port)

    @mcp.tool()
    def check(sha256: str, code: str | None = None,
              file_path: str | None = None,
              config: str | dict | None = None,
              filename: str = "Module.bsl") -> dict:
        """Статический анализ кода 1С (BSL) на соответствие стандартам.

        sha256 — обязательный SHA-256 файла (64 hex). Вычисли по самому файлу:
            sha256sum Module.bsl
        code — точный текст модуля; не перепечатывай его вручную.
        file_path — альтернатива code: сервер прочитает файл сам, если путь виден
            в контейнере. В стандартном Docker-развёртывании проект не смонтирован;
            используйте code+sha256.
        config — содержимое .bsl-language-server.json (строкой-JSON или объектом).
        filename — имя файла для отчёта (по умолчанию Module.bsl).
        """
        prepared, filename, expected, source, error = prepare_input(
            code, file_path, sha256, filename)
        if error:
            return _result(ok=False, summary=error, sha256=expected,
                           source=source, raw_bytes=0)
        return run_check(prepared, filename, jar=jar,
                         config=_as_config_text(config),
                         expected_sha256=expected, source=source)

    return mcp


def main():
    """Запустить MCP-сервер (streamable HTTP, эндпоинт `/mcp`)."""
    mcp = build_server()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
