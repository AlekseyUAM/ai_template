# extract_queries.py — порт src/cli/extractQueries.ts (query_console_vscode).
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
            text = _unpipe("".join(raw))
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
    args = parser.parse_args(argv)
    path = args.Path
    blocks = []
    targets = []
    if os.path.isdir(path):
        ext = ".xml" if args.Xml else ".bsl"
        targets = sorted(_walk(path, ext))
    else:
        targets = [path]
    for file in targets:
        try:
            with open(file, encoding="utf-8") as fh:
                source = fh.read()
        except OSError:
            continue
        found = extract_queries_from_xml(source) if args.Xml else extract_query_strings(source)
        for q in found:
            blocks.append(f"# {file}:{q.line_start}\n{q.text}")
    print("\n--- 8< ---\n".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
