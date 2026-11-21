"""Bash/PowerShell command parsing (port of code-index-guard main.rs v1.15.4).

Parsers only: heredoc/here-string bodies are data, chain links are cut
at the first single pipe, directory change is tracked via `cd`/`pushd`/
`Set-Location`. Decisions are made by the calling modules (bash/powershell/redirect).
"""
import ntpath
import os
from pathlib import Path

from . import paths


def _lines(text: str) -> list[str]:
    """Like Rust `str::lines`: lines by `\\n`, `\\r\\n` without trailing `\\r`, without
    an empty line after the final newline."""
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
    """Drops heredoc bodies (`... <<'TAG'` ... line `TAG`): they are DATA.

    Without this, a commit message line starting with `ls ` or `grep ` would look
    like a search link. The line with `<<'TAG'` stays - it is the real command.
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
    """Heredoc tag from the line (`git commit -F - <<'msg'` -> `msg`). None - no heredoc."""
    pos = line.find("<<")
    if pos < 0:
        return None
    after = line[pos + 2:]
    if after.startswith("<"):
        return None  # `<<<` - here-string, it has no body
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
    """Drops PowerShell here-string bodies (`@'` ... `'@`, `@"` ... `"@`): they are DATA."""
    out: list[str] = []
    inside = False
    for line in _lines(cmd):
        t = line.strip()
        if inside:
            # The closing marker is at the start of the line: '@ or "@.
            if t.startswith("'@") or t.startswith('"@'):
                inside = False
            continue
        if t.endswith("@'") or t.endswith('@"'):
            inside = True
            out.append(line)  # the command with the opener itself - real
            continue
        out.append(line)
    return "\n".join(out)


def split_chain(cmd: str) -> list[str]:
    """Links by `&&`, `||`, `;`, newline; CUT at the first single pipe.

    Everything right of a pipe filters foreign output rather than searching files. Quotes
    are respected: `grep -iE '^(PG|POSTGRES)' .env` must not be cut by a pipe inside the pattern.
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
    """`str::trim_matches(ch)` - strip the character from both ends, as many as present."""
    return s.strip(ch)


def parse_assignment(part: str, ps: bool = False) -> tuple[str, str] | None:
    """Simple assignment at the start of a link: `root="/c/tmp"` / `$root = "C:/tmp"`.

    A compound value (substitution, pipeline, several unquoted words) is not
    parsed - guessing the target is worse than abstaining.
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
    # In bash a space before `=` means a command with arguments, not an assignment.
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
        return None  # value built from substitutions - target unknown
    return (name, value)


def dir_change(part: str, base: str, home: str | None) -> str | None:
    """Directory change link -> new base directory.

    None - the link is not a directory change. `""` - the directory became unknown (popd, cd -,
    unresolved substitution): abstain further instead of judging by the old cwd.
    The environment is not read: the home directory is passed by the caller.
    """
    base = base.replace("\\", "/")
    trimmed = base.rstrip("/")
    # The root `/` must not collapse into an empty string: an empty base means "directory unknown".
    if not trimmed and base:
        base = "/"
    else:
        base = trimmed
    # `split_once(char::is_whitespace)`: the first whitespace splits command and argument.
    sp = next((i for i, c in enumerate(part) if c.isspace()), -1)
    if sp >= 0:
        cmd, arg = part[:sp], part[sp:].strip()
    else:
        cmd, arg = part, ""
    # Whole-word match: `cdx foo` is not a directory change.
    word = cmd.lower()
    if word in ("cd", "pushd"):
        ps_no_arg, is_pop = False, False
    elif word in ("set-location", "sl", "push-location"):
        # PowerShell without an argument does not change the directory: `sl` prints the current one.
        ps_no_arg, is_pop = True, False
    elif word in ("popd", "pop-location"):
        ps_no_arg, is_pop = False, True
    else:
        return None
    if is_pop:
        return ""  # where it returned to - unknown
    arg = arg.strip()
    arg = _trim_matches(_trim_matches(arg, '"'), "'")
    # Leading keys: for Set-Location these are -Path/-LiteralPath, for cmd `cd` - /d.
    for key in ("-path ", "-literalpath ", "/d "):
        rest = paths.strip_prefix_ci(arg, key)
        if rest is not None:
            arg = rest
            break
    arg = _trim_matches(_trim_matches(arg.strip(), '"'), "'")
    if not arg:
        # Bare cd in bash goes to the home directory, in PowerShell - nowhere.
        if ps_no_arg:
            return base
        return home if home is not None else ""
    # `cd -` and an unresolved substitution: target unknown.
    if arg == "-" or "$" in arg:
        return ""
    if arg == "~" or arg.startswith("~/"):
        if home is None:
            return ""  # home directory unknown
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
            return ""  # relative from an unknown directory
        abs_path = f"{base}/{arg}"
    return paths.normalize_dir(abs_path)


def home_dir() -> str | None:
    """USERPROFILE, else HOME; `\\`->`/`, MSYS drives normalized, case per system rule."""
    raw = os.environ.get("USERPROFILE")
    if not raw or not raw.strip():
        raw = os.environ.get("HOME")
        if not raw or not raw.strip():
            return None
    norm = paths.normalize_msys_drives(raw.replace("\\", "/"))
    return paths.fold_path(norm.rstrip("/"))


def expand_vars(text: str, vars: dict[str, str]) -> str:
    """Substitutes `$root` and `${root}`. Longest names first, otherwise `$a` would corrupt `$abc`.

    Unknown substitutions stay as is - the caller abstains because of them.
    """
    if not vars or "$" not in text:
        return text
    out = text
    for name in sorted(vars, key=len, reverse=True):
        value = vars[name]
        out = out.replace(f"${{{name}}}", value).replace(f"${name}", value)
    return out


def ls_targets_are_files(link: str, base: str) -> bool:
    """true -> the `ls` link has targets and EVERY one of them is an existing file.

    Then it is a look at file size and date, not a directory walk. A bare `ls`,
    a directory and a mask do not count as file targets.
    """
    base = base.replace("\\", "/").rstrip("/")
    has_target = False
    for word in link.split()[1:]:
        if word.startswith("-"):
            continue
        clean = _trim_matches(_trim_matches(word, '"'), "'")
        if not clean or "*" in clean or "?" in clean:
            return False  # mask - this is a listing
        drive, _ = ntpath.splitdrive(clean)
        if drive or clean.startswith("/"):
            abs_path = clean
        else:
            abs_path = f"{base}/{clean}"
        if not Path(abs_path).is_file():
            return False  # directory or non-existent path - listing
        has_target = True
    return has_target


def has_explicit_path(lower: str) -> bool:
    """true -> the command contains an explicit path: drive (`:/`), home (`~/`) or a `/...` token.

    cwd fallback gate: with an explicit path it must not be replaced by the indexed cwd.
    """
    if ":/" in lower or "~/" in lower:
        return True
    return any(tok.startswith("/") for tok in lower.split())


def cmd_contains_indexed_prefix(lower: str, prefix: str) -> bool:
    """true -> `prefix` occurs at a path boundary, not as part of a longer
    directory name: 'code-index' does not match 'code-index-guard'.
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
            return True  # end of string
        b = lower[after]
        if not ((b.isascii() and b.isalnum()) or b == "-" or b == "_"):
            return True
        start = pos + 1
