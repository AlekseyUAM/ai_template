"""Тонкий MCP-сервер для образа «Статический анализ BSL».

Экспортирует ровно один инструмент `check`: принимает текст кода BSL и возвращает
диагностики (ошибки/предупреждения) по настройкам `.bsl-language-server.json`.
Сервер stateless — без индекса и доступа к кодовой базе: каждый вызов гоняет
BSL Language Server в режиме CLI `analyze` с json-репортёром по присланному тексту.

Функции `parse_report` и `run_check` специально не зависят от пакета `mcp` и
легко тестируются без java. Импорт FastMCP выполняется лениво в `build_server()`.
"""
import json
import os
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


def run_check(code: str, filename: str, jar: str, config: str | None = None,
              java: str = "java", run=subprocess.run) -> dict:
    """Проверить присланный код BSL через CLI `analyze` BSL Language Server.

    Пишет `code` во временный `src/<filename>`. Если передан `config` (содержимое
    файла `.bsl-language-server.json` из корня проекта) — кладёт его в корень того
    же временного каталога как `.bsl-language-server.json`; BSL LS подхватывает его
    как per-workspace-настройки проверок. Запускает json-репортёр и парсит
    `bsl-json.json`. Параметр `run` (по умолчанию `subprocess.run`) позволяет
    подменить запуск в тестах без java. Временный каталог всегда удаляется.

    Сервер stateless: никакого доступа к кодовой базе проекта — только присланные
    код и настройки. Возвращает `{ok, count, diagnostics, summary}`; при ошибке
    запуска или отсутствии отчёта — `ok=False` и текст ошибки/stderr в `summary`.
    """
    filename = Path(filename or "Module.bsl").name or "Module.bsl"
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
            proc = run(cmd, capture_output=True, text=True)
        except Exception as exc:  # java не найдена и т.п.
            return {"ok": False, "count": 0, "diagnostics": [],
                    "summary": f"Не удалось запустить BSL LS: {exc}"}

        report_path = outdir / "bsl-json.json"
        if not report_path.exists():
            stderr = (getattr(proc, "stderr", "") or "").strip()
            code_ = getattr(proc, "returncode", "?")
            return {"ok": False, "count": 0, "diagnostics": [],
                    "summary": stderr or f"Отчёт не создан (код возврата {code_})."}

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return {"ok": False, "count": 0, "diagnostics": [],
                    "summary": f"Не удалось прочитать отчёт: {exc}"}

        diagnostics = parse_report(report, filename)
        return {"ok": True, "count": len(diagnostics),
                "diagnostics": diagnostics, "summary": _summary(diagnostics)}
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
    def check(code: str, config: str | dict | None = None,
              filename: str = "Module.bsl") -> dict:
        """Статический анализ кода 1С (BSL) на соответствие стандартам; возвращает ошибки/предупреждения.

        code — текст модуля BSL для проверки (обязательно).
        config — содержимое файла настроек .bsl-language-server.json. Перед вызовом
            прочитай .bsl-language-server.json в корне проекта и передай его сюда
            (строкой-JSON или объектом), чтобы проверки шли по правилам проекта.
            Если такого файла в проекте нет — не передавай config: анализ выполнится
            с правилами BSL LS по умолчанию.
        filename — имя файла для отчёта (по умолчанию Module.bsl).
        """
        return run_check(code, filename, jar=jar, config=_as_config_text(config))

    return mcp


def main():
    """Запустить MCP-сервер (streamable HTTP, эндпоинт `/mcp`)."""
    mcp = build_server()
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
