"""Changed BSL modules with actual code.

A metadata-only task often creates empty module files (BOM + a newline). The
main-configuration `check-modules` then compiles nothing and costs a minute.
This helper answers whether the working tree has changed `.bsl` files with
non-whitespace content. `None` means git is unavailable or the repository is
unreadable - the caller runs the check to be safe.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_BOM = b"\xef\xbb\xbf"


def _git_lines(project_root: Path, args: list[str]) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_bsl_files(project_root: Path,
                      subdir: str | None = None) -> list[Path] | None:
    """Changed/added `.bsl` files in the working tree (tracked and untracked).

    `subdir` limits the search (e.g. `"src/cf"` for the main configuration);
    `None` returns all changed `.bsl`, including extensions.
    """
    if not (project_root / ".git").exists():
        return None
    tracked = _git_lines(
        project_root,
        ["diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--", "*.bsl"],
    )
    if tracked is None:
        # No HEAD yet (fresh repository) - compare with the index/working tree.
        tracked = _git_lines(
            project_root,
            ["diff", "--name-only", "--diff-filter=ACMR", "--", "*.bsl"],
        )
    if tracked is None:
        return None
    untracked = _git_lines(
        project_root,
        ["ls-files", "--others", "--exclude-standard", "--", "*.bsl"],
    )
    if untracked is None:
        return None
    names = sorted({name for name in tracked + untracked
                    if name.lower().endswith(".bsl")})
    if subdir:
        prefix = subdir.replace("\\", "/").strip("/") + "/"
        names = [name for name in names
                 if name.replace("\\", "/").startswith(prefix)]
    return [project_root / name for name in names]


def has_nonempty_changed_bsl(project_root: Path,
                             subdir: str | None = None) -> bool | None:
    """True if a changed `.bsl` has code; False if all are empty; None if unknown.

    `subdir` limits the search to one source root, e.g. `"src/cf"`: extension
    modules do not make the main-configuration check necessary.
    """
    files = changed_bsl_files(project_root, subdir)
    if files is None:
        return None
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            return True  # unreadable - let the module check report it
        if data.startswith(_BOM):
            data = data[len(_BOM):]
        if data.strip():
            return True
    return False
