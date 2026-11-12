"""Нормализация и сравнение путей (порт code-index-guard)."""
import os
import sys


def default_case_insensitive() -> bool:
    """Windows и macOS сравнивают пути без учёта регистра, Linux — с учётом."""
    return os.name == "nt" or sys.platform == "darwin"


def fold_path(s: str, case_insensitive: bool | None = None) -> str:
    ci = default_case_insensitive() if case_insensitive is None else case_insensitive
    return s.lower() if ci else s


def norm_prefix(p: str, case_insensitive: bool | None = None) -> str:
    """Префикс репозитория: прямые слэши, без хвостового, регистр по правилу."""
    return fold_path(p.replace("\\", "/").rstrip("/"), case_insensitive)


def _ascii_lower(s: str) -> str:
    """Понижение регистра только для ASCII — как `eq_ignore_ascii_case` в Rust."""
    return "".join(ch.lower() if ch.isascii() else ch for ch in s)


def strip_prefix_ci(s: str, prefix: str) -> str | None:
    """`strip_prefix` без учёта регистра ASCII — для ключей команд (`-Path`, `/D`)."""
    if len(s) < len(prefix):
        return None
    if _ascii_lower(s[: len(prefix)]) != _ascii_lower(prefix):
        return None
    return s[len(prefix):]


def normalize_dir(path: str) -> str:
    """Нормализация пути.

    Сегменты `.` и пустые (кроме корня) выбрасываются, `..` снимает предыдущий
    сегмент, но не выше корня (`c:` либо ведущего `/`). Хвостового `/` нет.
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
    """`/c/...` → `c:/...` только на границе пути (начало или после не-алфанумерика)."""
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
    """Если raw попадает в индексированный префикс → (alias, rel, root в исходном регистре)."""
    if not raw:
        return None
    norm = normalize_msys_drives(raw.replace("\\", "/"))
    norm_cmp = fold_path(norm, case_insensitive)
    # Длинные префиксы первыми: C:/Projects/app/core выигрывает над C:/Projects/app.
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
    """Простейший glob: `*` — любой отрезок, остальное буквально. Для `*_run_*.json`."""
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
