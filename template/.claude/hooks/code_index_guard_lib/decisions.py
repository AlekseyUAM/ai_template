"""Решения для Read / Grep / Glob (порт code-index-guard main.rs v1.15.4).

None — воздержание (хук молчит, нативный инструмент работает). `в сомнении —
пропустить`: блокируем только когда доказано, что MCP отдаст то же самое.
"""
from dataclasses import dataclass
from pathlib import Path

from . import index_db, paths, tools


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str | None = None


# Бинарные / не-индексируемые расширения. Их нет в `files`; в Glob —
# маркер «трогаем не индексированное» → воздержаться.
BINARY_EXT = (".epf", ".erf", ".cf", ".cfe", ".png", ".jpg", ".jpeg", ".gif",
              ".ico", ".bmp", ".zip", ".7z", ".gz", ".rar", ".exe", ".dll",
              ".bin", ".pdf", ".mxl", ".grs")


def _str(ti: dict, key: str) -> str:
    v = ti.get(key)
    return v if isinstance(v, str) else ""


def _int(ti: dict, key: str) -> int | None:
    v = ti.get(key)
    # JSON-число; bool — не число (в Python isinstance(True, int) истинно).
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def decide_read(ti: dict, ctx) -> Decision | None:
    """Чтение файла — основная ветка с точной проверкой членства."""
    fp = _str(ti, "file_path")
    if not fp:
        return None
    m = paths.match_indexed(fp, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return None
    alias, rel, root = m

    # Ритуальный Read РОВНО одной первой строки для снятия гейта Edit — пропускаем.
    # Любое другое чтение (даже 2-5 строк, и строка из середины файла) идёт через
    # индекс/кеш. Гейту Edit достаточно Read(offset=1, limit=1).
    if _int(ti, "limit") == 1 and _int(ti, "offset") in (None, 0, 1):
        return Decision(True)

    if not index_db.read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive):
        return None  # не доказано, что MCP отдаст → воздержаться (нативный Read)

    read_file = tools.tool("read_file")
    get_function = tools.tool("get_function")
    get_file_summary = tools.tool("get_file_summary")
    reason = (
        f"Read запрещён на индексированном пути (repo='{alias}'). Файл в индексе — "
        "MCP отдаёт его в 3-10× дешевле по токенам. Возьми инструменты code-index "
        "(как назван сервер в этой сессии — видно по списку инструментов): "
        f'{read_file}(repo="{alias}", path="{rel}", line_start=N, line_end=M). '
        f"Функцию целиком: {get_function}(repo=\"{alias}\", function_name=\"...\"). "
        f'Карту файла: {get_file_summary}(repo="{alias}", path="{rel}"). '
        f'Для гейта Edit допустим Read(file_path="{fp}", offset=1, limit=1).'
    )
    return Decision(False, reason)


def decide_grep(ti: dict, cwd: str | None, ctx) -> Decision | None:
    """Grep по всему репо: блокируем, только если MCP-поиск даст тот же результат."""
    path = _str(ti, "path")
    glob = _str(ti, "glob")
    ci = ctx.case_insensitive
    if path:
        norm = path.replace("\\", "/")
        if not Path(norm).exists():
            return None  # явный путь не существует → не блокируем
        m = paths.match_indexed(path, ctx.paths, case_insensitive=ci)
    else:
        # path не задан → Grep идёт от cwd сессии
        m = paths.match_indexed(cwd or "", ctx.paths, case_insensitive=ci)
    if m is None:
        return None
    alias, rel, root = m
    # Исключения проекта смотрим И по пути, И по образцу: `Grep(glob=".env")` из
    # корня репо указывает на неиндексируемый файл ровно так же, как явным путём.
    if (index_db.excluded_from_index(root, rel, case_insensitive=ci)
            or (glob and index_db.excluded_from_index(root, glob, case_insensitive=ci))):
        return None
    reason = (
        f"Grep запрещён на индексированном пути (repo='{alias}'). Используй инструменты code-index: "
        f'{tools.tool("grep_code")}(repo="{alias}", regex="...", language="...") по коду или '
        f'{tools.tool("grep_text")}(repo="{alias}", regex="...", path_glob="...") по yaml/md/json.'
    )
    return Decision(False, reason)


def decide_glob(ti: dict, cwd: str | None, ctx) -> Decision | None:
    """Glob по каталогу: list_files отдаёт только индексируемое."""
    path = _str(ti, "path")
    pattern = _str(ti, "pattern")
    # Glob по бинарному расширению — list_files его не вернёт (не индексируется).
    if any(pattern.lower().endswith(e) for e in BINARY_EXT):
        return None
    ci = ctx.case_insensitive
    # cwd — кандидат ВСЕГДА, когда явного пути нет: самый частый вызов агента —
    # `Glob(pattern="services/**/*.py")` из корня репо: относительный образец путём
    # не является, поэтому без cwd он проходил бы мимо.
    candidates = [path, pattern]
    if not path:
        candidates.append(cwd or "")
    for c in candidates:
        if not c:
            continue
        m = paths.match_indexed(c, ctx.paths, case_insensitive=ci)
        if m is None:
            continue
        alias, rel, root = m
        target = pattern if not rel else rel
        if (index_db.excluded_from_index(root, target, case_insensitive=ci)
                or (pattern and index_db.excluded_from_index(root, pattern,
                                                             case_insensitive=ci))):
            return None
        reason = (
            f"Glob запрещён на индексированном пути (repo='{alias}'). Используй инструмент "
            f'code-index {tools.tool("list_files")}(repo="{alias}", pattern="...", language="...").'
        )
        return Decision(False, reason)
    return None
