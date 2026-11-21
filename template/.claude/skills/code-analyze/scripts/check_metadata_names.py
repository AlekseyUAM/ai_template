#!/usr/bin/env python3
"""Проверить имена метаданных на совпадение с системными перечислениями/наборами.

Сканирует XML-выгрузку конфигурации (`src/cf`, `src/cfe`) и сообщает о
`<Name>`, совпадающих с именами системных перечислений и наборов значений.
Такие имена зарезервированы платформой и не должны использоваться для
объектов, реквизитов, табличных частей и других метаданных.

    python .claude/skills/code-analyze/scripts/check_metadata_names.py src/cf src/cfe

Код возврата 1 — есть находки. Формат строки совместим с analyze_code.py:
    error | reserved-system-name | путь:строка | сообщение
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rules  # noqa: E402

_NAME_RE = re.compile(r"<Name(?:\s[^>]*)?>([^<]*)</Name>")


def iter_xml(paths: list[str]):
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.rglob("*.xml"))
        elif path.suffix.lower() == ".xml" and path.is_file():
            yield path


def _git_lines(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_xml() -> list[str]:
    """XML, изменённые/добавленные в рабочем дереве (для проверки правок задачи)."""
    files = (_git_lines(["diff", "--name-only", "--diff-filter=ACMR"])
             + _git_lines(["ls-files", "--others", "--exclude-standard"]))
    return sorted({name for name in files if name.lower().endswith(".xml")})


def scan(paths: list[str]) -> list[dict]:
    findings: list[dict] = []
    for path in iter_xml(paths):
        if path.name == "ConfigDumpInfo.xml":
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        seen: set[str] = set()
        for match in _NAME_RE.finditer(text):
            name = match.group(1).strip()
            canonical = rules.SYSTEM_RESERVED.get(name.casefold())
            if not canonical or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            line = text.count("\n", 0, match.start()) + 1
            findings.append({"file": str(path), "line": line,
                             "name": name, "canonical": canonical})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["src/cf"],
                        help="каталоги/XML-файлы (по умолчанию src/cf)")
    parser.add_argument("--changed", action="store_true",
                        help="только XML, изменённые/добавленные в git")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    args = parser.parse_args()

    paths = changed_xml() if args.changed else args.paths
    if args.changed and not paths:
        if args.json:
            print(json.dumps({"findings": []}, ensure_ascii=False))
        else:
            print("Изменённых XML нет.")
        return 0
    findings = scan(paths)
    if args.json:
        print(json.dumps({"findings": findings}, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(
                f"error | reserved-system-name | {item['file']}:{item['line']} | "
                f"Имя «{item['name']}» зарезервировано под системное "
                f"перечисление/набор значений «{item['canonical']}»; "
                f"выберите другое имя."
            )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
