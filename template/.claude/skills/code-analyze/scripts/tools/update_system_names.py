#!/usr/bin/env python3
"""Собрать system_enums.json из разбора справки платформы 1С (.hbk).

Источник — корпус и построчный разбор `bsl-ctx` (тот же разбор справки, что
используют MCP-серверы платформенного контекста). Данные нужны правилам
code-analyze: `system-enum-value` и `reserved-system-name`.

Как получить входные файлы (пример для установленной платформы):

    bsl-ctx capture "C:\\Program Files (x86)\\1cv8\\8.3.27.2170\\bin" -o corpus.sqlite
    bsl-ctx parse --all --db corpus.sqlite --out parsed.jsonl

Затем:

    python tools/update_system_names.py \
        --corpus corpus.sqlite --parsed parsed.jsonl \
        --out system_enums.json --platform 8.3.27.2170

Скрипт использует только стандартную библиотеку Python.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

_VALUE_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")


def descendants(conn: sqlite3.Connection, pid: int) -> set[int]:
    """Все потомки категории TOC (включая вложенные подразделы)."""
    ids: set[int] = set()
    stack = [pid]
    while stack:
        cur = stack.pop()
        for (cid,) in conn.execute(
                "select id from category where parent_id = ?", (cur,)):
            if cid not in ids:
                ids.add(cid)
                stack.append(cid)
    return ids


def page_paths(conn: sqlite3.Connection, ids: set[int]) -> set[tuple[str, str]]:
    if not ids:
        return set()
    q = ",".join("?" * len(ids))
    return {(book, path) for book, path in conn.execute(
        f"select distinct book, path from page where category_id in ({q})",
        tuple(ids))}


def split_value(text: str) -> tuple[str, str]:
    """«Приход (Receipt)» -> («Приход», «Receipt»)."""
    match = _VALUE_RE.match(text.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), ""


def load_records(parsed: Path, wanted: set[tuple[str, str]]) -> list[dict]:
    out: list[dict] = []
    with parsed.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (rec.get("book"), rec.get("path")) not in wanted:
                continue
            values = (rec.get("member_lists") or {}).get("enum_values") or []
            if not values:
                continue
            names = rec.get("names") or {}
            name_ru = names.get("name_ru") or names.get("full_ru") or ""
            name_en = names.get("name_en") or names.get("full_en") or ""
            if not name_ru:
                continue
            pairs: list[list[str]] = []
            open_set = False
            for item in values:
                value_ru, value_en = split_value(item.get("text") or "")
                if not value_ru:
                    continue
                if "<" in value_ru or ">" in value_ru or "<" in value_en or ">" in value_en:
                    # «<Имя картинки>» — набор открыт, проверять члены нельзя.
                    open_set = True
                    continue
                pairs.append([value_ru, value_en])
            out.append({"name_ru": name_ru, "name_en": name_en,
                        "values": pairs, "open": open_set})
    return out


def build(corpus: Path, parsed: Path, platform: str) -> dict:
    conn = sqlite3.connect(corpus)
    enum_pages = page_paths(conn, descendants(conn, 6))      # Системные перечисления
    value_pages = page_paths(conn, descendants(conn, 5))     # Системные наборы значений
    enums = load_records(parsed, enum_pages)
    value_sets = load_records(parsed, value_pages)
    return {
        "schema_version": 1,
        "platform": platform,
        "generated_at": date.today().isoformat(),
        "source": "shcntx_ru.hbk (bsl-ctx corpus)",
        "enums": {
            rec["name_ru"]: {"name_en": rec["name_en"], "values": rec["values"]}
            for rec in sorted(enums, key=lambda item: item["name_ru"].casefold())
        },
        "value_sets": {
            rec["name_ru"]: {"name_en": rec["name_en"], "open": rec["open"],
                             "values": rec["values"]}
            for rec in sorted(value_sets, key=lambda item: item["name_ru"].casefold())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path,
                        help="corpus.sqlite из `bsl-ctx capture`")
    parser.add_argument("--parsed", required=True, type=Path,
                        help="JSONL из `bsl-ctx parse --all --out`")
    parser.add_argument("--out", required=True, type=Path,
                        help="куда записать system_enums.json")
    parser.add_argument("--platform", default="unknown",
                        help="версия платформы для метаданных файла")
    args = parser.parse_args()

    data = build(args.corpus, args.parsed, args.platform)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    enum_values = sum(len(info["values"]) for info in data["enums"].values())
    set_values = sum(len(info["values"]) for info in data["value_sets"].values())
    print(f"перечислений: {len(data['enums'])} (значений {enum_values})")
    print(f"наборов значений: {len(data['value_sets'])} (значений {set_values})")
    print(f"записано: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
