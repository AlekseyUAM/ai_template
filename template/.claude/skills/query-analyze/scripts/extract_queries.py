# extract_queries.py - port of src/cli/extractQueries.ts (query_console_vscode).
import argparse
import os
import re
import sys
from dataclasses import dataclass

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

QUERY_KEYWORDS = ("ВЫБРАТЬ", "УНИЧТОЖИТЬ")

NAMED_XML_ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}

_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|#[xX][0-9a-fA-F]+|#[0-9]+);")

_QUERY_TEXT_RE = re.compile(r"\bЗапрос\s*\.\s*Текст\b", re.IGNORECASE)
_NEW_QUERY_RE = re.compile(r"\bНовый\s+Запрос\b", re.IGNORECASE)


def _strip_leading_comments(text: str) -> str:
    """Remove leading empty lines and //... comment lines, as well as
    the indent of the first line (after `|` removal it remains from `Запрос.Текст = "`)."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("//"):
            i += 1
            continue
        break
    result = lines[i:]
    if result:
        result[0] = result[0].lstrip(" \t")
    return "\n".join(result)


def _sanitize_bsl(source: str) -> str:
    """Replace strings and comments with spaces, keeping line breaks."""
    out = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch == '"':
            out.append(" ")
            i += 1
            while i < n:
                c = source[i]
                if c == '"':
                    if i + 1 < n and source[i + 1] == '"':
                        out.append("  ")
                        i += 2
                        continue
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else " ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out.append(" ")
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class ExtractedQuery:
    text: str
    line_start: int


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _starts_with_query_keyword(text: str) -> bool:
    trimmed = text.lstrip(" \t\r\n﻿")
    upper = trimmed.upper()
    for kw in QUERY_KEYWORDS:
        if not upper.startswith(kw):
            continue
        nxt = trimmed[len(kw):len(kw) + 1]
        if nxt == "" or not _is_word_char(nxt):
            return True
    return False


def _unpipe(raw_body: str) -> str:
    lines = raw_body.split("\n")
    out = []
    for i, line in enumerate(lines):
        if i == 0:
            out.append(line)
            continue
        m = re.match(r"[ \t]*\|", line)
        out.append(line[m.end():] if m else line)
    return "\n".join(out)


def unescape_xml_entities(s: str) -> str:
    def repl(m):
        ent = m.group(1)
        if ent[0] == "#":
            code = int(ent[2:], 16) if ent[1] in "xX" else int(ent[1:], 10)
            if code < 0 or code > 0x10FFFF:
                return m.group(0)
            try:
                return chr(code)
            except ValueError:
                return m.group(0)
        return NAMED_XML_ENTITIES[ent]
    return _ENTITY_RE.sub(repl, s)


def extract_query_strings(bsl_source: str):
    result = []
    n = len(bsl_source)
    i = 0
    line = 1
    while i < n:
        ch = bsl_source[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "/" and i + 1 < n and bsl_source[i + 1] == "/":
            while i < n and bsl_source[i] != "\n":
                i += 1
            continue
        if ch == "'":
            i += 1
            while i < n and bsl_source[i] != "'" and bsl_source[i] != "\n":
                i += 1
            if i < n and bsl_source[i] == "'":
                i += 1
            continue
        if ch == '"':
            line_start = line
            i += 1
            raw = []
            while i < n:
                c = bsl_source[i]
                if c == '"':
                    if i + 1 < n and bsl_source[i + 1] == '"':
                        raw.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                if c == "\n":
                    line += 1
                raw.append(c)
                i += 1
            text = _strip_leading_comments(_unpipe("".join(raw)))
            if _starts_with_query_keyword(text):
                result.append(ExtractedQuery(text, line_start))
            continue
        i += 1
    return result


def extract_queries_from_xml(xml_source: str):
    result = []
    for m in re.finditer(r"<query>([\s\S]*?)</query>", xml_source):
        line_start = xml_source[:m.start()].count("\n") + 1
        text = unescape_xml_entities(m.group(1))
        if _starts_with_query_keyword(text):
            result.append(ExtractedQuery(text, line_start))
    return result


def _walk(root: str, ext: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(ext):
                yield os.path.join(dirpath, name)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("-Path", required=True)
    parser.add_argument("-Xml", action="store_true", help="извлекать из СКД-XML (<query>)")
    parser.add_argument("-NoFail", action="store_true",
                        help="не возвращать код 2 при нулевом извлечении")
    args = parser.parse_args(argv)
    path = args.Path
    blocks = []
    targets = []
    if os.path.isdir(path):
        ext = ".xml" if args.Xml else ".bsl"
        targets = sorted(_walk(path, ext))
    else:
        targets = [path]
    warnings = []
    undecodable = []
    for file in targets:
        try:
            with open(file, encoding="utf-8") as fh:
                source = fh.read()
        except UnicodeDecodeError:
            undecodable.append(file)
            continue
        except OSError:
            continue
        found = extract_queries_from_xml(source) if args.Xml else extract_query_strings(source)
        for q in found:
            blocks.append(f"# {file}:{q.line_start}\n{q.text}")
        if not args.Xml and not found:
            sanitized = _sanitize_bsl(source)
            if _QUERY_TEXT_RE.search(sanitized) or _NEW_QUERY_RE.search(sanitized):
                warnings.append(file)
    for file in warnings:
        print(
            f"ВНИМАНИЕ: {file}: есть 'Запрос.Текст'/'Новый Запрос', но извлечено "
            f"0 запросов — query-analyze не проверит запрос. Проверьте текст "
            f"запроса вручную.",
            file=sys.stderr,
        )
    for file in undecodable:
        print(
            f"ВНИМАНИЕ: {file}: не удалось прочитать как UTF-8 — файл пропущен",
            file=sys.stderr,
        )
    print("\n--- 8< ---\n".join(blocks))
    return 0 if args.NoFail or not (warnings or undecodable) else 2


if __name__ == "__main__":
    raise SystemExit(main())
