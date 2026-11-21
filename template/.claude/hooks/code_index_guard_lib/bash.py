"""Decisions for the Bash tool (port of code-index-guard main.rs v1.15.4).

Per-file read `cat`/`head`/`tail` first, then the search link over the whole
chain. None - abstain: `when in doubt, skip`.
"""
from . import index_db, paths, shell, tools
from .decisions import BINARY_EXT, Decision  # noqa: F401  (BINARY_EXT - re-export)
from .redirect import redirect_for_link

# Search links (with a space: `grep ` does not match `grepx`).
READ_UTILS = ("grep ", "rg ", "find ", "ls ")


def decide_bash(tool_input: dict, cwd: str | None, ctx) -> Decision | None:
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd:
        return None
    # Paths in the command follow the system case rule; command names are compared
    # separately, on a copy of the link in lower case.
    lower = paths.fold_path(paths.normalize_msys_drives(cmd.replace("\\", "/")),
                            ctx.case_insensitive)

    d = decide_bash_file_read(cmd, lower, cwd, ctx)
    if d is not None:
        return d

    # The search link is looked up across the WHOLE chain: `cd <repo> && grep -rn "x" src/`
    # starts with `cd`. The chain also gives the working directory for the next links.
    # We do not look at a link after a single pipe: foreign output is filtered there.
    base = cwd or ""
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
        if b is not None:
            base = b
            continue
        head = part.lower()
        # git grep / git log -S - history and commit contents, not covered by the index.
        if head.startswith("git "):
            continue
        if any(head.startswith(u) for u in READ_UTILS):
            # `ls` is intercepted in any form: a directory listing is replaced by list_files.
            # Exception: `ls -la <existing files>` - a look at size and date,
            # list_files does not provide that.
            if head.startswith("ls ") and shell.ls_targets_are_files(part, base):
                continue
            link = part
            break
    if link is None:
        return None
    return redirect_for_link(link, base, "Bash read", ctx)


def decide_bash_file_read(cmd: str, lower: str, cwd: str | None,
                          ctx) -> Decision | None:
    """`cat`/`head`/`tail` on a SINGLE indexed file -> Deny with read_file."""
    s = lower.strip().lower()
    if s.startswith("cat "):
        util = "cat"
    elif s.startswith("head "):
        util = "head"
    elif s.startswith("tail "):
        util = "tail"
    else:
        return None

    # Any compound construct - not our scope, abstain.
    if ("|" in cmd or ">" in cmd or "<" in cmd or "`" in cmd or "$" in cmd
            or ";" in cmd or "*" in cmd or "?" in cmd or "~" in cmd
            or "&&" in cmd or "||" in cmd):
        return None

    # toks[0] is the utility; then flags and EXACTLY one file (in any order).
    toks = cmd.split()
    file: str | None = None
    n = 10  # head/tail default
    i = 1
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            rest = t[1:]
            # cat with any flag changes output (-n numbering, -A, etc.).
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
                return None  # -f / -F / -c / unknown flag
        else:
            if file is not None:
                return None  # several files
            file = t
        i += 1
    if file is None:
        return None
    file = file.strip('"').strip("'")
    if n <= 0:
        return None

    # Absolute path as is; relative path from the session cwd.
    if ":/" in file or file.startswith("/"):
        abs_path = file
    else:
        if not cwd:
            return None  # session directory unknown
        abs_path = f"{cwd.replace(chr(92), '/').rstrip('/')}/{file}"

    m = paths.match_indexed(abs_path, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return None
    alias, rel, root = m
    if not index_db.read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive):
        return None  # not indexed / oversize / index is behind

    if util == "head":
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", line_start=1, line_end={n})'
    elif util == "tail":
        how = (f'{tools.tool("stat_file")}(repo="{alias}", path="{rel}") for lines_total, then '
               f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", '
               f"line_start=lines_total-{n}+1)")
    else:
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}")'
    reason = (
        f"Bash read '{util}' on an indexed file (repo='{alias}') is denied. "
        f"MCP returns it cheaper and more precisely with code-index tools: {how}. "
        f"The rule applies only to src/cf/**; src/cfe/**, tasks/**, logs/**, tmp/**, "
        f"configs/**, docs/** are not indexed - cat/grep are allowed there."
    )
    return Decision(False, reason)


def _is_int(s: str) -> bool:
    return bool(s) and s.isascii() and s.isdigit()
