"""Path membership in the local index.db and exclusions (port of code-index-guard main.rs).

`sqlite3` is imported lazily: on the hook hot path (outside tests) the DB is touched
only when the path falls under an indexed prefix.
"""
import json
import sys
from pathlib import Path

from .paths import default_case_insensitive, fold_path, glob_match

# Built-in exclusions - what the code-index walker never traverses.
NEVER_INDEXED = frozenset({
    ".git",
    "node_modules",
    ".code-index",
    "target",
    "__pycache__",
    ".venv",
})


def _warn(msg: str) -> None:
    print(f"[code-index-guard] {msg}", file=sys.stderr)


def file_mtime_secs(path: str) -> int | None:
    """File mtime on disk in unix seconds - for comparison with `files.mtime`.

    None -> no file or it is unavailable (then freshness is not checked).
    """
    try:
        return int(Path(path).stat().st_mtime)
    except OSError:
        return None


def serveability(db: str, rel: str, *, case_insensitive: bool | None = None
                 ) -> tuple[bool, int | None] | None:
    """(whether the file is served via MCP, mtime of the index record) or None on failure.

    Served if there is a text_contents row (v5) or a text_files row (v4),
    or file_contents with oversize=0. No row in files / oversize=1 / otherwise -
    MCP will not serve it.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error as e:
        _warn(f"serveability open failed on {db}: {e}")
        return None
    try:
        try:
            has_text_contents = conn.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='text_contents' LIMIT 1"
            ).fetchone() is not None
            # Schema v5 stores text in text_contents, v4 in text_files. A wrong
            # table would give "no such table" -> the guard would silently stop blocking.
            table = "text_contents" if has_text_contents else "text_files"
            # Case follows the system rule: on Linux `README.md` does not find `readme.md`.
            collate = " COLLATE NOCASE" if case_insensitive else ""
            sql = (
                f"SELECT (SELECT 1 FROM {table} t WHERE t.file_id = f.id LIMIT 1), "
                "(SELECT c.oversize FROM file_contents c WHERE c.file_id = f.id LIMIT 1), "
                f"f.mtime FROM files f WHERE f.path = ?1{collate} LIMIT 1"
            )
            row = conn.execute(sql, (rel,)).fetchone()
        except sqlite3.Error as e:
            # Log the real SQL/schema error so schema drift is visible.
            _warn(f"serveability query failed on {db}: {e}")
            return None
    finally:
        conn.close()
    if row is None:
        # "No row" - not in the index: neither serveable nor mtime.
        return (False, None)
    is_text, oversize, mtime = row
    if is_text is not None:
        # There is a text_contents row (v5) / text_files row (v4) -> read_file will serve it.
        serve = True
    elif oversize is not None:
        # Code: served only if the content is stored (oversize=0).
        serve = oversize == 0
    else:
        # "Bare" row in files without content - MCP will not serve it.
        serve = False
    return (serve, mtime)


def read_is_blockable(root: str, rel: str, *, case_insensitive: bool | None = None
                      ) -> bool:
    """True -> the file is provably served via MCP (native Read may be blocked).

    Block ONLY when a local index.db exists: without it (index on a
    remote node, path not indexed yet) membership cannot be verified -> abstain.
    """
    db = Path(root) / ".code-index" / "index.db"
    if not db.exists():
        return False
    res = serveability(str(db), rel, case_insensitive=case_insensitive)
    if res is None:
        return False
    serve, idx_mtime = res
    if not serve:
        return False
    # Freshness: disk newer than the index record -> the watcher has not caught up, MCP
    # would serve stale content. Abstain - let Read read the current version.
    disk = file_mtime_secs(f"{root}/{rel}")
    if idx_mtime is not None and disk is not None and disk > idx_mtime:
        return False
    return True


def dir_changed_since_index(root: str, rel: str) -> bool:
    """True -> directory `root/rel` (mtime) is newer than the local index.db.

    New files -> a native listing may show what MCP does not have:
    list_files knows only the indexed content. Without a DB or
    directory, freshness cannot be proven - False (the caller decides by its own policy).
    """
    try:
        dir_mtime = int((Path(root) / rel).stat().st_mtime)
        db_mtime = int((Path(root) / ".code-index" / "index.db").stat().st_mtime)
    except OSError:
        return False
    # int seconds, as in file_mtime_secs. Fraction-of-a-second cutoff: a change in
    # the same second as the index record looks "not newer" - such a directory
    # is considered fresh per the index. Python compares ints without overflow, so
    # large mtime values (e.g. the far future) do not break the comparison.
    if dir_mtime > db_mtime:
        return True
    return False


def _read_project_config(root: str) -> dict | None:
    # Read only: the hook has no reason to touch project files.
    try:
        with open(f"{root}/.code-index/config.json", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    try:
        cfg = json.loads(text)
    except ValueError:
        return None
    return cfg if isinstance(cfg, dict) else None


def excluded_from_index(root: str, rel: str, *, case_insensitive: bool | None = None
                        ) -> bool:
    """Whether a path is excluded from the index - by the built-in list AND by project settings.

    Without the second half the guard produces dead ends: `exclude_dirs` and
    `exclude_file_patterns` from `<repo>/.code-index/config.json` are not indexed,
    and MCP will not serve them. Comparison is BY SEGMENTS, not by substring:
    the built-in list is given as `/.venv/`, while a path is usually relative.
    """
    if case_insensitive is None:
        case_insensitive = default_case_insensitive()
    rel_l = fold_path(rel.replace("\\", "/"), case_insensitive)
    segments = [s for s in rel_l.split("/") if s]

    if any(s in NEVER_INDEXED for s in segments):
        return True

    # A specific existing file - ask the index for the FACT instead of guessing by
    # extension: this filters out dotfiles, `Dockerfile`, `.svg` and other things the
    # walker does not take (there is no type list outside - it is hardcoded in the indexer).
    if "*" not in rel_l and "?" not in rel_l:
        full = f"{root.replace(chr(92), '/').rstrip('/')}/{rel_l}"
        if Path(full).is_file() and not read_is_blockable(
                root, rel_l, case_insensitive=case_insensitive):
            return True

    cfg = _read_project_config(root)
    if cfg is None:
        return False
    dirs = cfg.get("exclude_dirs")
    if isinstance(dirs, list):
        for d in dirs:
            if not isinstance(d, str):
                continue
            d = fold_path(d, case_insensitive)
            if d in segments:
                return True
    pats = cfg.get("exclude_file_patterns")
    if isinstance(pats, list):
        # Compare the pattern with EVERY segment: the target is both a file and a mask.
        for p in pats:
            if not isinstance(p, str):
                continue
            p = fold_path(p, case_insensitive)
            if any(glob_match(p, s) for s in segments):
                return True
    return False
