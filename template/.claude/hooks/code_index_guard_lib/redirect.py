"""Общий хвост redirect-веток Bash и PowerShell (порт main.rs:790-858 v1.15.4).

Находит индексированный корень по звену команды (или по рабочему каталогу для
bare-команды), отсеивает исключения проекта и выдаёт Deny с подсказкой про MCP.
"""
from . import decisions, index_db, paths, shell, tools
from .decisions import Decision


def redirect_for_link(link: str, base: str, tool_label: str, ctx) -> Decision | None:
    """`tool_label` — начало текста отказа (`Bash-чтение`, `PowerShell-поиск`)."""
    # Нераскрытая подстановка ($var из окружения, $(...), обратные кавычки) — цель
    # звена неизвестна. Воздерживаемся: подставить вместо неё каталог сессии значит
    # отказать по репозиторию, к которому команда может не иметь отношения.
    if "$" in link or "`" in link:
        return None
    # Команда трогает бинарь → воздержаться (его в индексе нет, дед-энд недопустим).
    link_lc = link.lower()
    if any(e in link_lc for e in decisions.BINARY_EXT):
        return None
    # Префиксы в ctx.paths уже свёрнуты по регистру системы — сверяем со свёрнутым
    # звеном; гейт явного пути смотрит на ИСХОДНОЕ звено (как путь пишет агент).
    link_folded = paths.fold_path(link, ctx.case_insensitive)
    paths_list = ctx.paths
    sorted_paths = sorted(paths_list, key=lambda entry: len(entry[0]), reverse=True)

    alias: str | None = None
    matched_root: str | None = None
    for prefix, a in sorted_paths:
        if shell.cmd_contains_indexed_prefix(link_folded, prefix):
            alias = a
            matched_root = prefix
            break
    # cwd-fallback только для истинно bare-команд (без явного пути-аргумента):
    # `ls ~/.claude/...` и `ls /tmp` из индексированного cwd к репо не относятся.
    # Смотрим на звено БЕЗ кавычек: `ls "/tmp/x"` — тоже явный путь.
    if alias is None and not shell.has_explicit_path(_unquote(link)):
        m = paths.match_indexed(base, paths_list, case_insensitive=ctx.case_insensitive)
        if m is not None:
            a, _rel, root = m
            alias = a
            matched_root = root
    if alias is None:
        return None
    # Исключения проекта — по КАЖДОМУ слову звена: цель бывает и путём, и маской.
    if matched_root is not None:
        for word in link.split()[1:]:
            if word.startswith("-"):
                continue
            clean = word.strip('"').strip("'")
            if not clean:
                continue
            # Абсолютный путь приводим к относительному ОТ ЕГО СОБСТВЕННОГО корня:
            # склейка root + "c:/repo/file" даёт чепуху, и неиндексированный файл
            # выглядит неисключённым.
            m = paths.match_indexed(clean, paths_list, case_insensitive=ctx.case_insensitive)
            if m is not None:
                _a, rel, check_root = m
            else:
                check_root, rel = matched_root, clean
            if rel and index_db.excluded_from_index(
                    check_root, rel, case_insensitive=ctx.case_insensitive):
                return None
        # Свежесть каталога-цели: каталог изменился после индексации (новые
        # объекты) → list_files их не знает, нативный листинг — единственный путь.
        # Только для листинга: `cat`/`grep` по индексированным файлам блокируем.
        if _is_directory_listing(link) and _listing_dir_changed(
                link, base, ctx, case_insensitive=ctx.case_insensitive):
            return None
    reason = (
        f"{tool_label} по индексированному пути (repo='{alias}') запрещено. "
        "На индексированных файлах MCP дешевле в 3-10×: инструменты code-index "
        f'{tools.tool("grep_code")}/{tools.tool("grep_text")}/{tools.tool("read_file")}/'
        f'{tools.tool("list_files")}(repo="{alias}", ...). '
        f'Список репо — {tools.tool("get_stats")}().'
    )
    return Decision(False, reason)


_LISTING_UTILS = ("ls", "dir", "find", "get-childitem", "gci")


def _is_directory_listing(link: str) -> bool:
    """Звено — листинг каталога (`ls`/`dir`/`find`/`Get-ChildItem`/`gci`)."""
    toks = link.split()
    return bool(toks) and toks[0].lower() in _LISTING_UTILS


def _listing_targets(link: str) -> list[str] | None:
    """Цели листинга без флагов. None → цель не разобрать (маска, флаг со значением).

    Маска (`*`, `?`) — выборка по содержимому каталога, а не листинг конкретного
    каталога: свежесть такого каталога не определяет, что найдёт команда.
    """
    out: list[str] = []
    for tok in link.split()[1:]:
        tok = tok.strip('"').strip("'")
        if not tok:
            continue
        if tok.startswith("-"):
            continue  # флаг; значение флага каталогом не считаем — deny остаётся
        if "*" in tok or "?" in tok:
            return None
        out.append(tok)
    return out


def _listing_dir_changed(link: str, base: str, ctx, *,
                         case_insensitive: bool) -> bool:
    """Изменился ли целевой каталог листинга после индексации.

    Целей нет → листинг `base`. Относительная цель → от `base`. Цель берётся,
    только если она попадает в индексированный репозиторий; несуществующий
    каталог свежести не даёт (`dir_changed_since_index` → False).
    """
    targets = _listing_targets(link)
    if targets is None:
        return False
    if not targets:
        targets = ["."]
    for t in targets:
        t = paths.normalize_msys_drives(t.replace("\\", "/"))
        if ":/" in t or t.startswith("/"):
            abs_path = t
        else:
            if not base:
                continue
            abs_path = f"{base.replace(chr(92), '/').rstrip('/')}/{t}"
        m = paths.match_indexed(abs_path, ctx.paths, case_insensitive=case_insensitive)
        if m is None:
            continue
        _alias, rel, root = m
        if index_db.dir_changed_since_index(root, rel):
            return True
    return False


def _unquote(link: str) -> str:
    """Снять с каждого токена обрамляющие `"`/`'`: `ls "/tmp/x"` → `ls /tmp/x`.

    Гейт явного пути смотрит на токены, начинающиеся с `/`; в кавычках он не видел
    абсолютный путь и подменял его индексированным cwd.
    """
    out: list[str] = []
    for tok in link.split():
        tok = tok.strip('"').strip("'")
        out.append(tok)
    return " ".join(out)
