"""Решения для инструмента Bash (порт code-index-guard main.rs v1.15.4).

Сначала пер-файловое чтение `cat`/`head`/`tail`, затем поисковое звено по всей
цепочке. None — воздержание: `в сомнении — пропустить`.
"""
from . import index_db, paths, shell, tools
from .decisions import BINARY_EXT, Decision  # noqa: F401  (BINARY_EXT — реэкспорт)
from .redirect import redirect_for_link

# Звенья-поисковики (с пробелом: `grep ` не матчит `grepx`).
READ_UTILS = ("grep ", "rg ", "find ", "ls ")


def decide_bash(tool_input: dict, cwd: str | None, ctx) -> Decision | None:
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd:
        return None
    # Пути в команде — по правилу регистра системы; имена команд сверяются
    # отдельно, на копии звена в нижнем регистре.
    lower = paths.fold_path(paths.normalize_msys_drives(cmd.replace("\\", "/")),
                            ctx.case_insensitive)

    d = decide_bash_file_read(cmd, lower, cwd, ctx)
    if d is not None:
        return d

    # Поисковое звено ищется по ВСЕЙ цепочке: `cd <репо> && grep -rn "x" src/`
    # начинается с `cd`. Цепочка заодно даёт рабочий каталог для следующих звеньев.
    # Звено после одиночной трубы не смотрим: там фильтруется чужой вывод.
    # None — каталог неизвестен (popd, cd -, нераскрытая подстановка).
    base: str | None = cwd or ""
    home = shell.home_dir()
    link: str | None = None
    assignments: dict[str, str] = {}
    for part in shell.split_chain(shell.strip_heredocs(lower)):
        part = shell.expand_vars(part.strip(), assignments)
        if not part:
            continue
        assign = shell.parse_assignment(part, False)
        if assign is not None:
            assignments[assign[0]] = assign[1]
            continue
        b = shell.dir_change(part, base, home)
        if b is shell._UNKNOWN_DIR:
            base = None
            continue
        if b is not None:
            base = b
            continue
        head = part.lower()
        # git grep / git log -S — история и содержимое коммитов, индексом не покрыты.
        if head.startswith("git "):
            continue
        if any(head.startswith(u) for u in READ_UTILS):
            # `ls` перехватывается в любом виде: список каталога заменяет list_files.
            # Исключение: `ls -la <существующие файлы>` — взгляд на размер и дату,
            # list_files такого не даёт.
            if head.startswith("ls ") and shell.ls_targets_are_files(part, base):
                continue
            link = part
            break
    if link is None:
        return None
    return redirect_for_link(link, base, "Bash-чтение", ctx)


def decide_bash_file_read(cmd: str, lower: str, cwd: str | None,
                          ctx) -> Decision | None:
    """`cat`/`head`/`tail` по ОДНОМУ индексированному файлу → Deny с read_file."""
    s = lower.strip().lower()
    if s.startswith("cat "):
        util = "cat"
    elif s.startswith("head "):
        util = "head"
    elif s.startswith("tail "):
        util = "tail"
    else:
        return None

    # Любая составная конструкция — не наша область, воздержаться.
    if ("|" in cmd or ">" in cmd or "<" in cmd or "`" in cmd or "$" in cmd
            or ";" in cmd or "*" in cmd or "?" in cmd or "~" in cmd
            or "&&" in cmd or "||" in cmd):
        return None

    # toks[0] — утилита; дальше флаги и РОВНО один файл (в любом порядке).
    toks = cmd.split()
    file: str | None = None
    n = 10  # умолчание head/tail
    i = 1
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            rest = t[1:]
            # cat с любым флагом меняет вывод (-n нумерация, -A и т.п.).
            if util == "cat":
                return None
            if t == "-n":
                i += 1
                if i >= len(toks) or not _is_int(toks[i]):
                    return None
                n = int(toks[i])
            elif rest.startswith("n"):
                if not _is_int(rest[1:]):
                    return None
                n = int(rest[1:])  # -n20
            elif rest and rest.isascii() and rest.isdigit():
                n = int(rest)  # -20
            else:
                return None  # -f / -F / -c / неизвестный флаг
        else:
            if file is not None:
                return None  # несколько файлов
            file = t
        i += 1
    if file is None:
        return None
    file = file.strip('"').strip("'")
    if n <= 0:
        return None

    # Абсолютный путь — как есть; относительный — от cwd сессии.
    if ":/" in file or file.startswith("/"):
        abs_path = file
    else:
        if not cwd:
            return None  # каталог сессии неизвестен
        abs_path = f"{cwd.replace(chr(92), '/').rstrip('/')}/{file}"

    m = paths.match_indexed(abs_path, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return None
    alias, rel, root = m
    if not index_db.read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive):
        return None  # не индексирован / oversize / индекс отстал

    if util == "head":
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", line_start=1, line_end={n})'
    elif util == "tail":
        how = (f'{tools.tool("stat_file")}(repo="{alias}", path="{rel}") для lines_total, затем '
               f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", '
               f"line_start=lines_total-{n}+1)")
    else:
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}")'
    reason = (
        f"Bash-чтение '{util}' по индексированному файлу (repo='{alias}') запрещено. "
        f"MCP отдаёт дешевле и точнее, инструментами code-index: {how}."
    )
    return Decision(False, reason)


def _is_int(s: str) -> bool:
    return bool(s) and s.isascii() and s.isdigit()
