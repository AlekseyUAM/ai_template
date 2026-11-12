"""Решения для инструмента PowerShell (порт code-index-guard main.rs v1.15.4).

Те же чтения, что в Bash, другими именами: Get-Content/gc/cat/type — пер-файлово,
Select-String/sls/Get-ChildItem/gci/ls/dir/findstr — поисковое звено по всей
цепочке. Без этой ветки PowerShell был бы обходом гарда целиком.
None — воздержание: `в сомнении — пропустить`.
"""
from . import index_db, paths, shell, tools
from .decisions import Decision
from .redirect import redirect_for_link

# Командлеты-поисковики вместе с алиасами (с пробелом: `ls ` не матчит `lsx`).
# Пер-файловые ридеры (get-content/gc/cat/type) здесь НЕ ищутся — они в
# decide_ps_file_read.
PS_READ_UTILS = ("select-string ", "sls ", "get-childitem ", "gci ", "ls ",
                 "dir ", "findstr ")
PS_LISTING_UTILS = ("ls ", "dir ", "gci ", "get-childitem ")


def decide_powershell(tool_input: dict, cwd: str | None, ctx) -> Decision | None:
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd:
        return None
    cmd = shell.strip_here_strings(cmd)
    # Как у Bash: пути — по правилу регистра системы, командлеты — без учёта регистра.
    lower = paths.fold_path(paths.normalize_msys_drives(cmd.replace("\\", "/")),
                            ctx.case_insensitive)

    d = decide_ps_file_read(cmd, lower, cwd, ctx)
    if d is not None:
        return d

    # Цепочка звеньев: как у Bash (обрыв на первой одиночной трубе — правее
    # фильтруется чужой вывод объектами, а не читаются файлы).
    # `""` — каталог неизвестен: match_indexed("") воздерживается.
    base = cwd or ""
    home = shell.home_dir()
    link: str | None = None
    assignments: dict[str, str] = {}
    for part in shell.split_chain(lower):
        part = shell.expand_vars(part.strip(), assignments)
        if not part:
            continue
        # `$root = "C:/tmp"` — не команда, а значение для следующих звеньев.
        assign = shell.parse_assignment(part, True)
        if assign is not None:
            assignments[assign[0]] = assign[1]
            continue
        b = shell.dir_change(part, base, home)
        if b is not None:
            base = b
            continue
        head = part.lower()
        # git grep / git log -S — история и содержимое коммитов, индексом не покрыты.
        if head.startswith("git "):
            continue
        if any(head.startswith(u) for u in PS_READ_UTILS):
            # Список каталога заменяет list_files, но взгляд на размер/дату
            # конкретных существующих файлов MCP не отдаёт — запрет был бы дед-эндом.
            if (any(head.startswith(u) for u in PS_LISTING_UTILS)
                    and shell.ls_targets_are_files(part, base)):
                continue
            link = part
            break
    if link is None:
        return None
    return redirect_for_link(link, base, "PowerShell-чтение", ctx)


def decide_ps_file_read(cmd: str, lower: str, cwd: str | None,
                        ctx) -> Decision | None:
    """Get-Content (алиасы gc/cat/type) по ОДНОМУ индексированному файлу → Deny."""
    s = lower.strip().lower()
    util = None
    for u in ("get-content", "gc", "cat", "type"):
        if s.startswith(u + " "):
            util = u
            break
    if util is None:
        return None

    # Любая составная конструкция — не наша область, воздержаться.
    # '$' покрывает переменные и подвыражения PowerShell, '`' — экранирование.
    if ("|" in cmd or ">" in cmd or "<" in cmd or "`" in cmd or "$" in cmd
            or ";" in cmd or "*" in cmd or "?" in cmd or "~" in cmd
            or "&&" in cmd or "||" in cmd):
        return None

    # toks[0] — командлет; дальше именованные параметры и РОВНО один файл.
    toks = cmd.split()
    file: str | None = None
    head: int | None = None  # -TotalCount N
    tail: int | None = None  # -Tail N
    i = 1
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            name = t.lower()
            if name in ("-path", "-literalpath"):
                i += 1
                if i >= len(toks) or file is not None:
                    return None  # несколько файлов
                file = toks[i]
            elif name in ("-totalcount", "-first", "-head"):
                i += 1
                head = _parse_int(toks[i]) if i < len(toks) else None
                if head is None:
                    return None
            elif name in ("-tail", "-last"):
                i += 1
                tail = _parse_int(toks[i]) if i < len(toks) else None
                if tail is None:
                    return None
            elif name in ("-raw", "-force", "-nonewline"):
                pass  # вывод файла не меняют — читаем дальше
            elif name == "-encoding":
                i += 1  # значение параметра пропускаем
            else:
                return None  # неизвестный параметр → воздержаться
        else:
            if file is not None:
                return None  # несколько файлов
            file = t
        i += 1
    if file is None:
        return None
    file = file.strip('"').strip("'")
    if (head is not None and head <= 0) or (tail is not None and tail <= 0):
        return None

    # Абсолютный путь — как есть; относительный — от cwd сессии.
    if ":/" in file or ":\\" in file or file.startswith("/"):
        abs_path = file.replace("\\", "/")
    else:
        if not cwd:
            return None
        abs_path = f"{cwd.replace(chr(92), '/').rstrip('/')}/{file}"

    m = paths.match_indexed(abs_path, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return None
    alias, rel, root = m
    if not index_db.read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive):
        return None  # не индексирован / oversize / индекс отстал

    if head is not None:
        n = head
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", line_start=1, line_end={n})'
    elif tail is not None:
        n = tail
        how = (f'{tools.tool("stat_file")}(repo="{alias}", path="{rel}") для lines_total, затем '
               f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", '
               f"line_start=lines_total-{n}+1)")
    else:
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}")'
    reason = (
        f"PowerShell-чтение '{util}' по индексированному файлу (repo='{alias}') запрещено. "
        f"MCP отдаёт дешевле и точнее, инструментами code-index: {how}."
    )
    return Decision(False, reason)


def _parse_int(s: str) -> int | None:
    """Rust `str::parse::<i64>()`: целое со знаком, хвостового мусора нет."""
    if not s or not s.isascii():
        return None
    body = s[1:] if s[0] in "+-" else s
    if not body or not body.isdigit():
        return None
    return int(s)
