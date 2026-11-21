"""Минимальная работа с daemon.toml code-index без TOML-зависимостей."""
from __future__ import annotations

import re

_PATH_HEADER = re.compile(r"(?m)^\[\[paths\]\][ \t]*$")
_ALIAS = re.compile(r'(?m)^[ \t]*alias[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"')
_MCP_HEADER = re.compile(r"(?m)^\[mcp\][ \t]*$")
_PATH_KEY = re.compile(r"(?m)^[ \t]*path[ \t]*=[ \t]*.*$")
_LANG_KEY = re.compile(r"(?m)^[ \t]*language[ \t]*=[ \t]*.*$")

_MCP_SECTION = ('[mcp]\n'
                '# массовый режим: get_object_structure принимает full_names (несколько объектов).\n'
                '# serve читает секцию один раз при старте — после изменения daemon.toml\n'
                '# перезапусти контейнер, иначе full_names продолжит отбиваться с -32602.\n'
                'mass_mode_tools = ["get_object_structure"]\n')


def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r",
                        '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _path_block(alias: str, path: str, language: str) -> str:
    return (f"[[paths]]\npath = {_quote(path)}\n"
            f"alias = {_quote(alias)}\nlanguage = {_quote(language)}\n")


def _set_key(body: str, pattern: re.Pattern, key: str, value: str) -> str:
    """Заменить значение key в теле блока или добавить ключ в конец."""
    line = f"{key} = {_quote(value)}"
    if pattern.search(body):
        return pattern.sub(lambda _m: line, body, count=1)
    if body and not body.endswith("\n"):
        body += "\n"
    return body + line + "\n"


def _update_path_block(segment: str, header_end: int, path: str,
                       language: str) -> str:
    """Обновить path/language блока на месте, сохранив прочие строки."""
    header = segment[:header_end]
    body = segment[header_end:]
    # тело блока — до следующего заголовка таблицы, если он есть
    tail_at = re.search(r"(?m)^\[", body)
    if tail_at:
        body, tail = body[:tail_at.start()], body[tail_at.start():]
    else:
        tail = ""
    body = _set_key(body, _PATH_KEY, "path", path)
    body = _set_key(body, _LANG_KEY, "language", language)
    return header + body + tail


def render_daemon_toml(alias: str, path: str, port: int | None = None) -> str:
    text = ('# Сгенерировано автоматически при развёртывании code-index.\n'
            '[daemon]\nhttp_host = "127.0.0.1"\nhttp_port = 0\n'
            'log_level = "info"\n\n')
    if port is not None:
        text += f"[[cache_targets]]\nurl = {_quote(f'http://127.0.0.1:{port}')}\n\n"
    text += _MCP_SECTION + "\n"
    return text + _path_block(alias, path, "bsl")


def merge_path(text: str, *, alias: str, path: str,
               language: str = "bsl") -> str:
    block = _path_block(alias, path, language)
    matches = list(_PATH_HEADER.finditer(text))
    if not matches:
        base = text.rstrip()
        return (base + "\n\n" if base else "") + block
    starts = [m.start() for m in matches]
    preamble = text[:starts[0]]
    segments = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        segments.append(text[start:end])
    found = False
    result = [preamble]
    for segment in segments:
        header_end = _PATH_HEADER.search(segment).end()
        body = segment[header_end:]
        match = _ALIAS.search(body)
        if match and _unescape(match.group(1)) == alias:
            result.append(_update_path_block(segment, header_end,
                                             path, language))
            found = True
        else:
            result.append(segment)
    if not found:
        if not result[-1].endswith("\n"):
            result.append("\n")
        result.append(block)
    return "".join(result)


def ensure_sections(text: str, port: int) -> str:
    out = text
    if not _MCP_HEADER.search(out):
        out = out.rstrip() + "\n\n" + _MCP_SECTION
    elif "mass_mode_tools" not in out:
        out = _MCP_HEADER.sub(_MCP_SECTION.lstrip(), out, count=1)
    cache_url = f"http://127.0.0.1:{port}"
    if cache_url not in out:
        out = out.rstrip() + f"\n\n[[cache_targets]]\nurl = {_quote(cache_url)}\n"
    return out
