"""Decisions for the PowerShell tool (port of code-index-guard main.rs v1.15.4).

The same reads as in Bash, under other names: Get-Content/gc/cat/type - per file,
Select-String/sls/Get-ChildItem/gci/ls/dir/findstr - the search link over the whole
chain. Without this branch PowerShell would be a complete bypass of the guard.
None - abstain: `when in doubt, skip`.
"""
from . import index_db, paths, shell, tools
from .decisions import Decision
from .redirect import redirect_for_link

# Search cmdlets with aliases (with a space: `ls ` does not match `lsx`).
# Per-file readers (get-content/gc/cat/type) are NOT looked up here - they are in
# decide_ps_file_read.
PS_READ_UTILS = ("select-string ", "sls ", "get-childitem ", "gci ", "ls ",
                 "dir ", "findstr ")
PS_LISTING_UTILS = ("ls ", "dir ", "gci ", "get-childitem ")


def decide_powershell(tool_input: dict, cwd: str | None, ctx) -> Decision | None:
    cmd = tool_input.get("command")
    if not isinstance(cmd, str) or not cmd:
        return None
    cmd = shell.strip_here_strings(cmd)
    # As in Bash: paths follow the system case rule, cmdlets are case-insensitive.
    lower = paths.fold_path(paths.normalize_msys_drives(cmd.replace("\\", "/")),
                            ctx.case_insensitive)

    d = decide_ps_file_read(cmd, lower, cwd, ctx)
    if d is not None:
        return d

    # Chain of links: as in Bash (cut at the first single pipe - to the right
    # foreign output is filtered by objects, not files being read).
    # `""` - directory unknown: match_indexed("") abstains.
    base = cwd or ""
    home = shell.home_dir()
    link: str | None = None
    assignments: dict[str, str] = {}
    for part in shell.split_chain(lower):
        part = shell.expand_vars(part.strip(), assignments)
        if not part:
            continue
        # `$root = "C:/tmp"` - not a command but a value for the following links.
        assign = shell.parse_assignment(part, True)
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
        if any(head.startswith(u) for u in PS_READ_UTILS):
            # A directory listing replaces list_files, but a look at size/date of
            # specific existing files is not served by MCP - a ban would be a dead end.
            if (any(head.startswith(u) for u in PS_LISTING_UTILS)
                    and shell.ls_targets_are_files(part, base)):
                continue
            link = part
            break
    if link is None:
        return None
    return redirect_for_link(link, base, "PowerShell read", ctx)


def decide_ps_file_read(cmd: str, lower: str, cwd: str | None,
                        ctx) -> Decision | None:
    """Get-Content (aliases gc/cat/type) on a SINGLE indexed file -> Deny."""
    s = lower.strip().lower()
    util = None
    for u in ("get-content", "gc", "cat", "type"):
        if s.startswith(u + " "):
            util = u
            break
    if util is None:
        return None

    # Any compound construct - not our scope, abstain.
    # '$' covers PowerShell variables and subexpressions, '`' - escaping.
    if ("|" in cmd or ">" in cmd or "<" in cmd or "`" in cmd or "$" in cmd
            or ";" in cmd or "*" in cmd or "?" in cmd or "~" in cmd
            or "&&" in cmd or "||" in cmd):
        return None

    # toks[0] is the cmdlet; then named parameters and EXACTLY one file.
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
                    return None  # several files
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
                pass  # they do not change the file output - keep reading
            elif name == "-encoding":
                i += 1  # skip the parameter value
            else:
                return None  # unknown parameter -> abstain
        else:
            if file is not None:
                return None  # several files
            file = t
        i += 1
    if file is None:
        return None
    file = file.strip('"').strip("'")
    if (head is not None and head <= 0) or (tail is not None and tail <= 0):
        return None

    # Absolute path as is; relative path from the session cwd.
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
        return None  # not indexed / oversize / index is behind

    if head is not None:
        n = head
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", line_start=1, line_end={n})'
    elif tail is not None:
        n = tail
        how = (f'{tools.tool("stat_file")}(repo="{alias}", path="{rel}") for lines_total, then '
               f'{tools.tool("read_file")}(repo="{alias}", path="{rel}", '
               f"line_start=lines_total-{n}+1)")
    else:
        how = f'{tools.tool("read_file")}(repo="{alias}", path="{rel}")'
    reason = (
        f"PowerShell read '{util}' on an indexed file (repo='{alias}') is denied. "
        f"MCP returns it cheaper and more precisely with code-index tools: {how}."
    )
    return Decision(False, reason)


def _parse_int(s: str) -> int | None:
    """Rust `str::parse::<i64>()`: signed integer, no trailing garbage."""
    if not s or not s.isascii():
        return None
    body = s[1:] if s[0] in "+-" else s
    if not body or not body.isdigit():
        return None
    return int(s)
