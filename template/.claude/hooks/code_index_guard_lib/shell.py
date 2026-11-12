"""Разбор Bash/PowerShell-команд (порт code-index-guard main.rs v1.15.4).

Только разборщики: тела heredoc/here-string — данные, звенья цепочки обрываются
на первой одиночной трубе, смена каталога отслеживается по `cd`/`pushd`/
`Set-Location`. Решения принимают вызывающие модули (bash/powershell/redirect).
"""
import os
from pathlib import Path

from . import paths


def _lines(text: str) -> list[str]:
    """Как Rust `str::lines`: строки по `\\n`, `\\r\\n` без хвостового `\\r`, без
    пустой строки после завершающего перевода."""
    out: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = text.find("\n", start)
        if end < 0:
            line = text[start:]
            start = n
        else:
            line = text[start:end]
            start = end + 1
        if line.endswith("\r"):
            line = line[:-1]
        out.append(line)
    return out


def strip_heredocs(cmd: str) -> str:
    """Выбрасывает тела heredoc'ов (`… <<'TAG'` … строка `TAG`): это ДАННЫЕ.

    Без этого строка сообщения коммита, начинающаяся с `ls ` или `grep `, выглядела
    поисковым звеном. Строка с `<<'TAG'` остаётся — она настоящая команда.
    """
    out: list[str] = []
    closing: str | None = None
    for line in _lines(cmd):
        if closing is not None:
            if line.strip() == closing:
                closing = None
            continue
        tag = heredoc_tag(line)
        if tag is not None:
            closing = tag
        out.append(line)
    return "\n".join(out)


def heredoc_tag(line: str) -> str | None:
    """Тег heredoc из строки (`git commit -F - <<'msg'` → `msg`). None — heredoc'а нет."""
    pos = line.find("<<")
    if pos < 0:
        return None
    after = line[pos + 2:]
    if after.startswith("<"):
        return None  # `<<<` — here-string, тела у неё нет
    if after.startswith("-"):
        after = after[1:]
    after = after.lstrip()
    if after.startswith("'"):
        tag = after[1:].split("'", 1)[0]
    elif after.startswith('"'):
        tag = after[1:].split('"', 1)[0]
    else:
        chars: list[str] = []
        for c in after:
            if c.isalnum() or c == "_":
                chars.append(c)
            else:
                break
        tag = "".join(chars)
    return tag or None


def strip_here_strings(cmd: str) -> str:
    """Выбрасывает тела here-string'ов PowerShell (`@'` … `'@`, `@"` … `"@`): это ДАННЫЕ."""
    out: list[str] = []
    inside = False
    for line in _lines(cmd):
        t = line.strip()
        if inside:
            # Закрывающая метка стоит в начале строки: '@ либо "@.
            if t.startswith("'@") or t.startswith('"@'):
                inside = False
            continue
        if t.endswith("@'") or t.endswith('@"'):
            inside = True
            out.append(line)  # сама команда с открытием — настоящая
            continue
        out.append(line)
    return "\n".join(out)


def split_chain(cmd: str) -> list[str]:
    """Звенья по `&&`, `||`, `;`, переводу строки; ОБРЫВ на первой одиночной трубе.

    Всё правее трубы фильтрует чужой вывод, а не ищет по файлам. Кавычки учитываются:
    `grep -iE '^(PG|POSTGRES)' .env` не должен резаться по трубе внутри образца.
    """
    out: list[str] = []
    cur: list[str] = []
    quote: str | None = None
    i = 0
    n = len(cmd)
    while i < n:
        c = cmd[i]
        if quote is not None:
            if c == quote:
                quote = None
            cur.append(c)
            i += 1
            continue
        if c == '"' or c == "'":
            quote = c
            cur.append(c)
            i += 1
            continue
        pair = cmd[i:i + 2]
        if pair == "&&" or pair == "||":
            out.append("".join(cur))
            cur = []
            i += 2
            continue
        if c == ";" or c == "\n":
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        if c == "|":
            out.append("".join(cur))
            return out
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _trim_matches(s: str, ch: str) -> str:
    """`str::trim_matches(ch)` — снять символ с обоих концов, сколько есть."""
    return s.strip(ch)


def parse_assignment(part: str, ps: bool = False) -> tuple[str, str] | None:
    """Простое присваивание в начале звена: `root="/c/tmp"` / `$root = "C:/tmp"`.

    Составное значение (подстановка, конвейер, несколько слов без кавычек) не
    разбираем — гадать о цели хуже, чем воздержаться.
    """
    s = part.strip()
    if ps:
        if not s.startswith("$"):
            return None
        s = s[1:]
    eq = s.find("=")
    if eq < 0:
        return None
    name_raw, value_raw = s[:eq], s[eq + 1:]
    # В bash пробел перед `=` означает не присваивание, а команду с аргументами.
    if not ps and name_raw and name_raw[-1].isspace():
        return None
    name = name_raw.strip()
    if not name or not all((c.isascii() and c.isalnum()) or c == "_" for c in name):
        return None
    raw = value_raw.strip()
    quoted = len(raw) > 1 and (
        (raw.startswith('"') and raw.endswith('"'))
        or (raw.startswith("'") and raw.endswith("'"))
    )
    if quoted:
        value = raw[1:-1]
    elif not raw or any(c.isspace() for c in raw):
        return None
    else:
        value = raw
    if "$" in value or "`" in value:
        return None  # значение собрано из подстановок — цель неизвестна
    return (name, value)


def dir_change(part: str, base: str, home: str | None) -> str | None:
    """Звено смены каталога → новый базовый каталог.

    None — звено не смена каталога. `""` — каталог стал неизвестен (popd, cd -,
    нераскрытая подстановка): дальше воздерживаемся, а не судим по прежнему cwd.
    Окружение не читается: домашний каталог передаёт вызывающий.
    """
    base = base.replace("\\", "/")
    trimmed = base.rstrip("/")
    # Корень `/` не должен схлопнуться в пустую строку: пустая база — «каталог неизвестен».
    if not trimmed and base:
        base = "/"
    else:
        base = trimmed
    # `split_once(char::is_whitespace)`: первый пробельный символ делит команду и аргумент.
    sp = next((i for i, c in enumerate(part) if c.isspace()), -1)
    if sp >= 0:
        cmd, arg = part[:sp], part[sp:].strip()
    else:
        cmd, arg = part, ""
    # Совпадение по слову целиком: `cdx foo` — не смена каталога.
    word = cmd.lower()
    if word in ("cd", "pushd"):
        ps_no_arg, is_pop = False, False
    elif word in ("set-location", "sl", "push-location"):
        # PowerShell без аргумента каталог не меняет: `sl` печатает текущий.
        ps_no_arg, is_pop = True, False
    elif word in ("popd", "pop-location"):
        ps_no_arg, is_pop = False, True
    else:
        return None
    if is_pop:
        return ""  # куда вернулись — неизвестно
    arg = arg.strip()
    arg = _trim_matches(_trim_matches(arg, '"'), "'")
    # Ведущие ключи: у Set-Location это -Path/-LiteralPath, у cmd-шного cd — /d.
    for key in ("-path ", "-literalpath ", "/d "):
        rest = paths.strip_prefix_ci(arg, key)
        if rest is not None:
            arg = rest
            break
    arg = _trim_matches(_trim_matches(arg.strip(), '"'), "'")
    if not arg:
        # Голый cd в bash уводит в домашний каталог, в PowerShell — никуда.
        if ps_no_arg:
            return base
        return home if home is not None else ""
    # `cd -` и нераскрытая подстановка: цель неизвестна.
    if arg == "-" or "$" in arg:
        return ""
    if arg == "~" or arg.startswith("~/"):
        if home is None:
            return ""  # домашнего каталога не знаем
        rest = arg.lstrip("~").lstrip("/")
        if not rest:
            abs_path = home
        else:
            abs_path = f"{home.rstrip('/')}/{rest}"
        return paths.normalize_dir(abs_path)
    if ":/" in arg or arg.startswith("/"):
        abs_path = arg
    else:
        if not base:
            return ""  # относительный от неизвестного каталога
        abs_path = f"{base}/{arg}"
    return paths.normalize_dir(abs_path)


def home_dir() -> str | None:
    """USERPROFILE, иначе HOME; `\\`→`/`, MSYS-диски приведены, регистр по правилу системы."""
    raw = os.environ.get("USERPROFILE")
    if not raw or not raw.strip():
        raw = os.environ.get("HOME")
        if not raw or not raw.strip():
            return None
    norm = paths.normalize_msys_drives(raw.replace("\\", "/"))
    return paths.fold_path(norm.rstrip("/"))


def expand_vars(text: str, vars: dict[str, str]) -> str:
    """Подставляет `$root` и `${root}`. Длинные имена первыми, иначе `$a` испортит `$abc`.

    Неизвестные подстановки остаются как есть — по ним вызывающий воздерживается.
    """
    if not vars or "$" not in text:
        return text
    out = text
    for name in sorted(vars, key=len, reverse=True):
        value = vars[name]
        out = out.replace(f"${{{name}}}", value).replace(f"${name}", value)
    return out


def ls_targets_are_files(link: str, base: str) -> bool:
    """true → у звена `ls` есть цели и КАЖДАЯ из них — существующий файл.

    Тогда это взгляд на размер и дату файлов, а не обход каталога. Голый `ls`,
    каталог и маска целями-файлами не считаются.
    """
    base = base.replace("\\", "/").rstrip("/")
    has_target = False
    for word in link.split()[1:]:
        if word.startswith("-"):
            continue
        clean = _trim_matches(_trim_matches(word, '"'), "'")
        if not clean or "*" in clean or "?" in clean:
            return False  # маска — это список
        if ":/" in clean or clean.startswith("/"):
            abs_path = clean
        else:
            abs_path = f"{base}/{clean}"
        if not Path(abs_path).is_file():
            return False  # каталог или несуществующий путь — список
        has_target = True
    return has_target


def has_explicit_path(lower: str) -> bool:
    """true → команда содержит явный путь: диск (`:/`), home (`~/`) или `/...`-токен.

    Гейт cwd-fallback: при явном пути нельзя подменять его на индексированный cwd.
    """
    if ":/" in lower or "~/" in lower:
        return True
    return any(tok.startswith("/") for tok in lower.split())


def cmd_contains_indexed_prefix(lower: str, prefix: str) -> bool:
    """true → `prefix` встречается на границе пути, а не как часть более длинного
    имени каталога: 'code-index' не матчит 'code-index-guard'.
    """
    start = 0
    n = len(lower)
    plen = len(prefix)
    while True:
        pos = lower.find(prefix, start)
        if pos < 0:
            return False
        after = pos + plen
        if after >= n:
            return True  # конец строки
        b = lower[after]
        if not ((b.isascii() and b.isalnum()) or b == "-" or b == "_"):
            return True
        start = pos + 1
