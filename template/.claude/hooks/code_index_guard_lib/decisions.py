"""Decisions for Read / Grep / Glob (port of code-index-guard main.rs v1.15.4).

None - abstain (the hook stays silent, the native tool works). `when in doubt -
skip`: block only when it is proven that MCP returns the same thing.
"""
from dataclasses import dataclass
from pathlib import Path

from . import index_db, paths, tools


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str | None = None


# Binary / non-indexed extensions. They are absent from `files`; in Glob -
# the marker "we touch non-indexed" -> abstain.
BINARY_EXT = (".epf", ".erf", ".cf", ".cfe", ".png", ".jpg", ".jpeg", ".gif",
              ".ico", ".bmp", ".zip", ".7z", ".gz", ".rar", ".exe", ".dll",
              ".bin", ".pdf", ".mxl", ".grs")


def _str(ti: dict, key: str) -> str:
    v = ti.get(key)
    return v if isinstance(v, str) else ""


def _int(ti: dict, key: str) -> int | None:
    v = ti.get(key)
    # JSON number; bool is not a number (in Python isinstance(True, int) is true).
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def decide_read(ti: dict, ctx) -> Decision | None:
    """File reading - the main branch with an exact membership check."""
    fp = _str(ti, "file_path")
    if not fp:
        return None
    m = paths.match_indexed(fp, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return None
    alias, rel, root = m

    # Ritual Read of EXACTLY one first line to clear the Edit gate - skip it.
    # Any other read (even 2-5 lines, and a line from the middle of the file) goes through
    # the index/cache. The Edit gate only needs Read(offset=1, limit=1).
    if _int(ti, "limit") == 1 and _int(ti, "offset") in (None, 0, 1):
        return Decision(True)

    if not index_db.read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive):
        return None  # not proven that MCP will return it -> abstain (native Read)

    read_file = tools.tool("read_file")
    get_function = tools.tool("get_function")
    get_file_summary = tools.tool("get_file_summary")
    reason = (
        f"Read is denied on an indexed path (repo='{alias}'). The file is in the index - "
        "MCP returns it 3-10x cheaper in tokens. Use the code-index tools "
        "(named as the server is named in this session - see the tool list): "
        f'{read_file}(repo="{alias}", path="{rel}", line_start=N, line_end=M). '
        f"Full function: {get_function}(repo=\"{alias}\", function_name=\"...\"). "
        f'File map: {get_file_summary}(repo="{alias}", path="{rel}"). '
        f'For the Edit gate, Read(file_path="{fp}", offset=1, limit=1) is allowed. '
        f'The rule applies only to indexed src/cf/**; src/cfe/**, tasks/**, '
        f'logs/**, tmp/**, configs/**, docs/** are not indexed - Read/Grep/'
        f'cat are allowed there.'
    )
    return Decision(False, reason)


def decide_grep(ti: dict, cwd: str | None, ctx) -> Decision | None:
    """Grep over the whole repo: block only if the MCP search gives the same result."""
    path = _str(ti, "path")
    glob = _str(ti, "glob")
    ci = ctx.case_insensitive
    if path:
        norm = path.replace("\\", "/")
        if not Path(norm).exists():
            return None  # explicit path does not exist -> do not block
        m = paths.match_indexed(path, ctx.paths, case_insensitive=ci)
    else:
        # path not set -> Grep starts from the session cwd
        m = paths.match_indexed(cwd or "", ctx.paths, case_insensitive=ci)
    if m is None:
        return None
    alias, rel, root = m
    # Project exclusions are checked BOTH by path AND by pattern: `Grep(glob=".env")` from
    # the repo root points to a non-indexed file just like an explicit path.
    if (index_db.excluded_from_index(root, rel, case_insensitive=ci)
            or (glob and index_db.excluded_from_index(root, glob, case_insensitive=ci))):
        return None
    reason = (
        f"Grep is denied on an indexed path (repo='{alias}'). Use code-index tools: "
        f'{tools.tool("grep_code")}(repo="{alias}", regex="...", language="...") for code or '
        f'{tools.tool("grep_text")}(repo="{alias}", regex="...", path_glob="...") for yaml/md/json.'
    )
    return Decision(False, reason)


def decide_glob(ti: dict, cwd: str | None, ctx) -> Decision | None:
    """Glob over a directory: list_files returns only indexed content."""
    path = _str(ti, "path")
    pattern = _str(ti, "pattern")
    # Glob by binary extension - list_files will not return it (not indexed).
    if any(pattern.lower().endswith(e) for e in BINARY_EXT):
        return None
    ci = ctx.case_insensitive
    # cwd is ALWAYS a candidate when there is no explicit path: the most common agent call -
    # `Glob(pattern="services/**/*.py")` from the repo root: a relative pattern is not a path,
    # so without cwd it would slip through.
    candidates = [path, pattern]
    if not path:
        candidates.append(cwd or "")
    # Target directory for the freshness check: an explicit `path`; without it `cwd`
    # only for a bare pattern - a relative one like `src/**/*.rs` is not a directory,
    # and its freshness does not determine what the pattern finds there.
    if path:
        target_dir = path
    elif "/" in pattern.replace("\\", "/"):
        target_dir = ""
    else:
        target_dir = cwd or ""
    if target_dir and _dir_changed_since_index(target_dir, ctx):
        return None
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
        list_files = tools.tool("list_files")
        hint = (f' First call: {list_files}(repo="{alias}", path_prefix="{rel}").'
                if rel else f' First call: {list_files}(repo="{alias}", pattern="*").')
        reason = (
            f"Glob is denied on an indexed path (repo='{alias}'). Use the code-index tool "
            f'{list_files}(repo="{alias}", pattern="...", language="...").'
            + hint
            + " If the index is stale and list_files misses new files, read those "
            "exact paths with native Read/meta-info."
        )
        return Decision(False, reason)
    return None


def _dir_changed_since_index(target: str, ctx) -> bool:
    """A directory inside an indexed root changed after indexing.

    The same freshness rule as for Bash listings (`redirect.py`): list_files does
    not know new files -> a native Glob is the only way, do not create a dead end.
    Only the resolved target directory is checked, not the whole tree.
    A non-directory target cannot be proven stale: an explicit `path` that Glob
    cannot find gives nothing to return (the native Glob would be empty anyway).
    """
    m = paths.match_indexed(target, ctx.paths, case_insensitive=ctx.case_insensitive)
    if m is None:
        return False
    _alias, rel, root = m
    if rel and not Path(paths.normalize_msys_drives(target.replace("\\", "/"))).is_dir():
        return False
    return index_db.dir_changed_since_index(root, rel)
