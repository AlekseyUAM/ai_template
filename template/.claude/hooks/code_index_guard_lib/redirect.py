"""Common tail of the Bash and PowerShell redirect branches (port of main.rs:790-858 v1.15.4).

Finds the indexed root by the command link (or by the working directory for a
bare command), filters project exclusions and returns Deny with an MCP hint.
"""
from . import decisions, index_db, paths, shell, tools
from .decisions import Decision


def redirect_for_link(link: str, base: str, tool_label: str, ctx) -> Decision | None:
    """`tool_label` - the start of the deny text (`Bash read`, `PowerShell search`)."""
    # Unresolved substitution ($var from the environment, $(...), backticks) - the
    # target of the link is unknown. Abstain: substituting the session directory instead
    # means denying based on a repo the command may have nothing to do with.
    if "$" in link or "`" in link:
        return None
    # The command touches a binary -> abstain (it is not in the index, a dead end is unacceptable).
    link_lc = link.lower()
    if any(e in link_lc for e in decisions.BINARY_EXT):
        return None
    # Prefixes in ctx.paths are already folded by the system case - compare against the folded
    # link; the explicit path gate looks at the ORIGINAL link (as the agent writes the path).
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
    # cwd fallback only for truly bare commands (without an explicit path argument):
    # `ls ~/.claude/...` and `ls /tmp` from an indexed cwd do not relate to the repo.
    # Look at the link WITHOUT quotes: `ls "/tmp/x"` is also an explicit path.
    if alias is None and not shell.has_explicit_path(_unquote(link)):
        m = paths.match_indexed(base, paths_list, case_insensitive=ctx.case_insensitive)
        if m is not None:
            a, _rel, root = m
            alias = a
            matched_root = root
    if alias is None:
        return None
    # Project exclusions - for EVERY word of the link: the target is both a path and a mask.
    if matched_root is not None:
        for word in link.split()[1:]:
            if word.startswith("-"):
                continue
            clean = word.strip('"').strip("'")
            if not clean:
                continue
            # Reduce an absolute path to a path relative to ITS OWN root:
            # gluing root + "c:/repo/file" gives nonsense, and a non-indexed file
            # looks non-excluded.
            m = paths.match_indexed(clean, paths_list, case_insensitive=ctx.case_insensitive)
            if m is not None:
                _a, rel, check_root = m
            else:
                check_root, rel = matched_root, clean
            if rel and index_db.excluded_from_index(
                    check_root, rel, case_insensitive=ctx.case_insensitive):
                return None
        # Freshness of the target directory: the directory changed after indexing (new
        # objects) -> list_files does not know them, a native listing is the only way.
        # Only for listings: `cat`/`grep` on indexed files are blocked.
        if _is_directory_listing(link) and _listing_dir_changed(
                link, base, ctx, case_insensitive=ctx.case_insensitive):
            return None
    reason = (
        f"{tool_label} on an indexed path (repo='{alias}') is denied. "
        "On indexed files MCP is 3-10x cheaper: use code-index tools "
        f'{tools.tool("grep_code")}/{tools.tool("grep_text")}/{tools.tool("read_file")}/'
        f'{tools.tool("list_files")}(repo="{alias}", ...). '
        f'Repo list - {tools.tool("get_stats")}().'
    )
    return Decision(False, reason)


_LISTING_UTILS = ("ls", "dir", "find", "get-childitem", "gci")


def _is_directory_listing(link: str) -> bool:
    """The link is a directory listing (`ls`/`dir`/`find`/`Get-ChildItem`/`gci`)."""
    toks = link.split()
    return bool(toks) and toks[0].lower() in _LISTING_UTILS


def _listing_targets(link: str) -> list[str] | None:
    """Listing targets without flags. None -> the target cannot be parsed (mask, flag with value).

    A mask (`*`, `?`) is a selection by directory content, not a listing of a specific
    directory: freshness of such a directory does not determine what the command finds.
    """
    out: list[str] = []
    for tok in link.split()[1:]:
        tok = tok.strip('"').strip("'")
        if not tok:
            continue
        if tok.startswith("-"):
            continue  # flag; the flag value is not considered a directory - the deny remains
        if "*" in tok or "?" in tok:
            return None
        out.append(tok)
    return out


def _listing_dir_changed(link: str, base: str, ctx, *,
                         case_insensitive: bool) -> bool:
    """Whether the target listing directory changed after indexing.

    No targets -> listing `base`. Relative target -> from `base`. A target is taken
    only if it falls into an indexed repository; a non-existent
    directory gives no freshness (`dir_changed_since_index` -> False).
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
    """Strip surrounding `"`/`'` from each token: `ls "/tmp/x"` -> `ls /tmp/x`.

    The explicit path gate looks at tokens starting with `/`; inside quotes it did not see
    an absolute path and replaced it with the indexed cwd.
    """
    out: list[str] = []
    for tok in link.split():
        tok = tok.strip('"').strip("'")
        out.append(tok)
    return " ".join(out)
