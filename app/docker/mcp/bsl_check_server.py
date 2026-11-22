"""Тонкий MCP-сервер для образа «Статический анализ BSL».

Экспортирует ровно один инструмент `check`: принимает текст кода BSL (и
обязательный SHA-256 файла) и возвращает диагностики (ошибки/предупреждения) по
настройкам `.bsl-language-server.json`. Сервер stateless — без индекса и доступа к
кодовой базе: каждый вызов гоняет BSL Language Server в режиме CLI `analyze` с
json-репортёром по присланному тексту. Альтернатива тексту — `file_path`: сервер
читает файл сам, но только если путь виден из контейнера. Ведущий UTF-8 BOM
срезается до анализа (BSL LS падает на нём с `ParseError`); `sha256` принимается
как для файла с BOM, так и для нормализованного текста.

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


_BOM = "﻿"


def _strip_bom(text: str) -> str:
    """Убрать ведущий UTF-8 BOM: BSL LS падает на `ParseError` с ним."""
    return text[1:] if text.startswith(_BOM) else text


def _sha256_hex(text: str) -> str:
    """SHA-256 текста в UTF-8 (как `sha256sum` по файлу в той же кодировке)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_variants(*texts: str) -> set[str]:
    """Допустимые SHA-256: с BOM и без, с одним завершающим `\n` и без него.

    Файл модуля часто заканчивается переводом строки, а текст в аргументе `code`
    приходит без него (и наоборот). Принимаем оба варианта плюс BOM-формы —
    `sha256sum Module.bsl` продолжает работать независимо от последней строки.
    """
    variants: set[str] = set()
    for text in texts:
        for candidate in (text, _strip_bom(text)):
            variants.add(_sha256_hex(candidate))
            if candidate.endswith("\n"):
                variants.add(_sha256_hex(candidate[:-1]))
            else:
                variants.add(_sha256_hex(candidate + "\n"))
    return variants


# Признак сбоя старта Spring в stderr BSL LS: повторный запуск обычно проходит.
_TRANSIENT_STDERR_MARKERS = ("BeanCreationException",)


def _is_transient_failure(stderr: str) -> bool:
    """stderr сносит запуск java, но повтор может пройти (сбой старта Spring)."""
    return any(marker in (stderr or "") for marker in _TRANSIENT_STDERR_MARKERS)


def _counts(diagnostics: list[dict]) -> dict:
    """Сырые счётчики по уровням severity (нули для отсутствующих уровней)."""
    counts = {"Error": 0, "Warning": 0, "Information": 0, "Hint": 0}
    for diag in diagnostics:
        severity = diag.get("severity") or ""
        if severity in counts:
            counts[severity] += 1
    return counts


def _result(*, ok: bool, summary: str, sha256: str, source: str,
            raw_bytes: int, diagnostics: list[dict] | None = None,
            bom_removed: bool = False,
            raw_sha256: str | None = None) -> dict:
    """Единый формат ответа: ok/count/counts/diagnostics/summary/sha256/source/bytes.

    `sha256` — хэш нормализованного текста (без BOM); `raw_sha256` — хэш
    исходного текста, если BOM был; `bom_removed` — признак нормализации.
    """
    diagnostics = diagnostics or []
    result = {"ok": ok, "count": len(diagnostics),
              "counts": _counts(diagnostics), "diagnostics": diagnostics,
              "summary": summary, "sha256": sha256, "source": source,
              "bytes": raw_bytes, "bom_removed": bom_removed}
    if raw_sha256 and raw_sha256 != sha256:
        result["raw_sha256"] = raw_sha256
    return result


def prepare_input(code, file_path, sha256, filename):
    """Проверить аргументы check и вернуть (code, filename, sha, source, error).

    `code` возвращается **исходным** (с BOM): BOM срезает `run_check`, который
    также сообщает `bom_removed`/`raw_sha256`. Здесь проверяется, что sha256
    соответствует исходному или нормализованному тексту, а также варианту с
    завершающим переводом строки или без него — так `sha256sum Module.bsl`
    продолжает работать для BOM-файлов и для файлов, оканчивающихся `\n`.
    """
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
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            return None, filename, expected, "file", (
                f"не удалось прочитать file_path: {exc}. В Docker-контейнере "
                f"путь проекта не виден — передайте code+sha256.")
        source = "file"
        if filename == "Module.bsl":
            filename = Path(file_path).name
    else:
        raw = code if isinstance(code, str) else str(code or "")

    normalized = _strip_bom(raw)
    actual = _sha256_hex(normalized)
    raw_sha = _sha256_hex(raw)
    if expected not in _sha256_variants(raw):
        return None, filename, expected, source, (
            f"sha256 не совпадает: передан {expected}, фактический {actual} "
            f"(без BOM) / {raw_sha} (с BOM); допускается также хэш варианта "
            f"с/без завершающего перевода строки. Текст не соответствует файлу — "
            f"не перепечатывай модуль, передай его как есть.")
    # Возвращаем исходный текст: run_check сам срежет BOM и заполнит
    # bom_removed/raw_sha256. expected нормализуем к хэшу текста без BOM —
    # run_check принимает обе формы, но так ответ однозначен.
    return raw, filename, actual, source, None


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

    Ведущий UTF-8 BOM срезается до записи в temp: BSL LS отвечает `ParseError`
    на начало модуля с BOM. Принимается sha256 как исходного (`raw`) текста, так
    и нормализованного — `sha256sum Module.bsl` по файлу с BOM продолжает
    работать. В ответе `sha256` — хэш нормализованного текста; при наличии BOM
    дополнительно возвращаются `raw_sha256` и `bom_removed=true`.

    Если передан `expected_sha256` — он должен быть 64 hex и совпасть с SHA-256
    `code` (с BOM/без и с завершающим `\n`/без него); иначе `ok=False` и java не
    запускается. Если java завершилась без отчёта с `BeanCreationException` в
    stderr — запуск повторяется один раз; прочие ошибки не повторяются.
    Внутренний вызов может не передавать хэш (`None`) — обязательность
    обеспечивает публичный `check`.

    Сервер stateless: никакого доступа к кодовой базе проекта — только присланные
    код и настройки. Возвращает `{ok, count, counts, diagnostics, summary, sha256,
    source, bytes, bom_removed[, raw_sha256]}`; при ошибке запуска или отсутствии
    отчёта — `ok=False` и текст ошибки/stderr в `summary`.
    """
    raw_code = code if isinstance(code, str) else str(code or "")
    code = _strip_bom(raw_code)
    bom_removed = code != raw_code
    raw_bytes = len(raw_code.encode("utf-8"))
    actual_sha = _sha256_hex(code)
    raw_sha = _sha256_hex(raw_code)
    if expected_sha256 is not None:
        expected = str(expected_sha256).strip().lower()
        if not _SHA256_RE.match(expected):
            return _result(ok=False, summary="sha256 должен быть 64 hex-символа.",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)
        if expected not in _sha256_variants(raw_code):
            return _result(
                ok=False,
                summary=(f"sha256 не совпадает: передан {expected}, фактический "
                         f"{actual_sha} (без BOM) / {raw_sha} (с BOM); "
                         f"допускается также хэш варианта с/без завершающего "
                         f"перевода строки. Текст не соответствует файлу — не "
                         f"перепечатывай модуль, передай его как есть."),
                sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                bom_removed=bom_removed, raw_sha256=raw_sha)
    if raw_bytes > MAX_CODE_BYTES:
        return _result(ok=False,
                       summary=f"код слишком большой (> {MAX_CODE_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)
    if config and len(config.encode("utf-8")) > MAX_CONFIG_BYTES:
        return _result(ok=False,
                       summary=f"config слишком большой (> {MAX_CONFIG_BYTES} байт)",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)
    filename = Path(filename or "Module.bsl").name or "Module.bsl"
    if filename in _RESERVED_FILENAMES:
        return _result(ok=False,
                       summary=f"имя файла {filename!r} зарезервировано под настройки анализа",
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)
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
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)
        except Exception as exc:  # java не найдена и т.п.
            return _result(ok=False,
                           summary=f"Не удалось запустить BSL LS: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)

        report_path = outdir / "bsl-json.json"
        if not report_path.exists():
            stderr = (getattr(proc, "stderr", "") or "").strip()
            # Сбой старта Spring (BeanCreationException) — транзиентный: повтор
            # запуска обычно проходит. Ошибки разбора (ParseError) и прочие
            # сбои не повторяются. Повтор ровно один; каталог отчёта старого
            # запуска удаляется, чтобы отчёт писался с нуля.
            if _is_transient_failure(stderr):
                shutil.rmtree(outdir, ignore_errors=True)
                try:
                    proc = run(cmd, capture_output=True, text=True,
                               timeout=ANALYZE_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    return _result(
                        ok=False,
                        summary=f"BSL LS не завершился за {ANALYZE_TIMEOUT_SECONDS} с",
                        sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                        bom_removed=bom_removed, raw_sha256=raw_sha)
                except Exception as exc:  # java не найдена и т.п.
                    return _result(ok=False,
                                   summary=f"Не удалось запустить BSL LS: {exc}",
                                   sha256=actual_sha, source=source,
                                   raw_bytes=raw_bytes, bom_removed=bom_removed,
                                   raw_sha256=raw_sha)
            if not report_path.exists():
                stderr = (getattr(proc, "stderr", "") or "").strip()
                code_ = getattr(proc, "returncode", "?")
                return _result(ok=False,
                               summary=stderr or f"Отчёт не создан (код возврата {code_}).",
                               sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                               bom_removed=bom_removed, raw_sha256=raw_sha)

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return _result(ok=False, summary=f"Не удалось прочитать отчёт: {exc}",
                           sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                           bom_removed=bom_removed, raw_sha256=raw_sha)

        diagnostics = parse_report(report, filename)
        return _result(ok=True, summary=_summary(diagnostics),
                       sha256=actual_sha, source=source, raw_bytes=raw_bytes,
                       bom_removed=bom_removed, raw_sha256=raw_sha,
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
        code — точный текст модуля; не перепечатывай его вручную. Хэш принимается
            и для текста с завершающим переводом строки, и без него.
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
