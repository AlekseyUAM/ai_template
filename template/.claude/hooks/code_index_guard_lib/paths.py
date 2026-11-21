"""Path normalization and comparison (port of code-index-guard)."""
import os
import sys


def default_case_insensitive() -> bool:
    """Windows and macOS compare paths case-insensitively, Linux case-sensitively."""
    return os.name == "nt" or sys.platform == "darwin"


def fold_path(s: str, case_insensitive: bool | None = None) -> str:
    ci = default_case_insensitive() if case_insensitive is None else case_insensitive
    return s.lower() if ci else s


def norm_prefix(p: str, case_insensitive: bool | None = None) -> str:
    """Repository prefix: forward slashes, no trailing one, case per rule."""
    return fold_path(p.replace("\\", "/").rstrip("/"), case_insensitive)


def _ascii_lower(s: str) -> str:
    """Lowercase ASCII only - like `eq_ignore_ascii_case` in Rust."""
    return "".join(ch.lower() if ch.isascii() else ch for ch in s)


def strip_prefix_ci(s: str, prefix: str) -> str | None:
    """`strip_prefix` ignoring ASCII case - for command keys (`-Path`, `/D`)."""
    if len(s) < len(prefix):
        return None
    if _ascii_lower(s[: len(prefix)]) != _ascii_lower(prefix):
        return None
    return s[len(prefix):]


def normalize_dir(path: str) -> str:
    """Path normalization.

    `.` and empty segments (except the root) are dropped, `..` pops the previous
    segment but not above the root (`c:` or a leading `/`). No trailing `/`.
    """
    if path.startswith("/"):
        root, rest = "/", path[1:]
    elif len(path) >= 2 and path[1] == ":":
        root, rest = path[:2], path[2:].lstrip("/")
    else:
        root, rest = "", path
    segs: list[str] = []
    for seg in rest.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if segs:
                segs.pop()
            continue
        segs.append(seg)
    joined = "/".join(segs)
    if root == "":
        return joined
    if root == "/":
        return "/" + joined if joined else "/"
    return f"{root}/{joined}" if joined else root


def _is_ascii_alnum(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def normalize_msys_drives(s: str) -> str:
    """`/c/...` -> `c:/...` only at a path boundary (start or after a non-alphanumeric)."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        boundary = i == 0 or not _is_ascii_alnum(s[i - 1])
        if (
            boundary
            and s[i] == "/"
            and i + 2 < n
            and s[i + 1].isascii()
            and s[i + 1].isalpha()
            and s[i + 2] == "/"
        ):
            out.append(s[i + 1])
            out.append(":")
            out.append("/")
            i += 3
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def match_indexed(raw: str, paths: list[tuple[str, str]], *,
                  case_insensitive: bool | None = None
                  ) -> tuple[str, str, str] | None:
    """If raw falls under an indexed prefix -> (alias, rel, root in original case)."""
    if not raw:
        return None
    norm = normalize_msys_drives(raw.replace("\\", "/"))
    norm_cmp = fold_path(norm, case_insensitive)
    # Longest prefixes first: C:/Projects/app/core wins over C:/Projects/app.
    sorted_paths = sorted(paths, key=lambda entry: len(entry[0]), reverse=True)
    for prefix, alias in sorted_paths:
        matched = norm_cmp == prefix or norm_cmp.startswith(prefix + "/")
        if not matched:
            continue
        if len(norm) < len(prefix):
            root, rel = norm, ""
        else:
            root = norm[: len(prefix)]
            rel = norm[len(prefix):].lstrip("/")
        return (alias, rel, root)
    return None


def glob_match(pattern: str, text: str) -> bool:
    """Simplest glob: `*` - any span, everything else literal. For `*_run_*.json`."""
    parts = pattern.split("*")
    if len(parts) == 1:
        return pattern == text
    pos = 0
    for i, part in enumerate(parts):
        if not part:
            continue
        if i == 0:
            if not text.startswith(part):
                return False
            pos = len(part)
            continue
        k = text.find(part, pos)
        if k < 0:
            return False
        pos = k + len(part)
    last = parts[-1]
    if last and not text.endswith(last):
        return False
    return True
