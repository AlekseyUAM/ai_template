"""Членство пути в локальном index.db и исключения (порт code-index-guard main.rs).

`sqlite3` импортируется лениво: на горячем пути хука (вне тестов) БД трогается
только когда путь попал в индексированный префикс.
"""
import json
import sys
from pathlib import Path

from .paths import default_case_insensitive, fold_path, glob_match

# Встроенные исключения — то, что walker code-index не обходит никогда.
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
    """mtime файла на диске в unix-секундах — для сравнения с `files.mtime`.

    None → файла нет или он недоступен (тогда свежесть не проверяем).
    """
    try:
        return int(Path(path).stat().st_mtime)
    except OSError:
        return None


def serveability(db: str, rel: str, *, case_insensitive: bool | None = None
                 ) -> tuple[bool, int | None] | None:
    """(отдаётся ли файл через MCP, mtime записи в индексе) либо None при сбое.

    Отдаётся, если есть text_contents-строка (v5) либо text_files-строка (v4),
    либо file_contents с oversize=0. Нет строки в files / oversize=1 / прочее —
    MCP не отдаст.
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
            # Схема v5 хранит текст в text_contents, v4 — в text_files. Неверная
            # таблица дала бы «no such table» → guard молча перестал бы блокировать.
            table = "text_contents" if has_text_contents else "text_files"
            # Регистр — по правилу системы: на Linux `README.md` не находит `readme.md`.
            collate = " COLLATE NOCASE" if case_insensitive else ""
            sql = (
                f"SELECT (SELECT 1 FROM {table} t WHERE t.file_id = f.id LIMIT 1), "
                "(SELECT c.oversize FROM file_contents c WHERE c.file_id = f.id LIMIT 1), "
                f"f.mtime FROM files f WHERE f.path = ?1{collate} LIMIT 1"
            )
            row = conn.execute(sql, (rel,)).fetchone()
        except sqlite3.Error as e:
            # Реальную SQL/схема-ошибку логируем, чтобы рассинхрон схемы был виден.
            _warn(f"serveability query failed on {db}: {e}")
            return None
    finally:
        conn.close()
    if row is None:
        # «Строки нет» — не в индексе: ни serveable, ни mtime.
        return (False, None)
    is_text, oversize, mtime = row
    if is_text is not None:
        # Есть text_contents-строка (v5) / text_files-строка (v4) → read_file отдаст.
        serve = True
    elif oversize is not None:
        # Код: отдаётся, только если контент сохранён (oversize=0).
        serve = oversize == 0
    else:
        # «Голая» строка в files без контента — MCP не отдаст.
        serve = False
    return (serve, mtime)


def read_is_blockable(root: str, rel: str, *, case_insensitive: bool | None = None
                      ) -> bool:
    """True → файл доказуемо отдаётся через MCP (можно блокировать нативный Read).

    Блокируем ТОЛЬКО при наличии локального index.db: без него (индекс на
    удалённой ноде, путь ещё не проиндексирован) членство не проверить → воздержание.
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
    # Свежесть: диск новее записи в индексе → наблюдатель ещё не догнал, MCP
    # отдаст устаревшее содержимое. Воздерживаемся — пусть Read прочтёт актуальное.
    disk = file_mtime_secs(f"{root}/{rel}")
    if idx_mtime is not None and disk is not None and disk > idx_mtime:
        return False
    return True


def dir_changed_since_index(root: str, rel: str) -> bool:
    """True → каталог `root/rel` (mtime) новее локального index.db.

    Новые файлы → нативный листинг может показать то, чего нет в MCP:
    list_files знает только проиндексированное. При отсутствии БД или
    каталога свежесть не доказать — False (решает вызывающий по своей политике).
    """
    try:
        dir_mtime = int((Path(root) / rel).stat().st_mtime)
        db_mtime = int((Path(root) / ".code-index" / "index.db").stat().st_mtime)
    except OSError:
        return False
    # int-секунды, как в file_mtime_secs: округление вниз не даёт ложной
    # «свежести» в ту же секунду, что и запись индекса.
    # Одиночное сравнение в `if` (не в выражении): значения mtime могут быть
    # больше 2^31, а сравнение-выражение там ненадёжно.
    if dir_mtime > db_mtime:
        return True
    return False


def _read_project_config(root: str) -> dict | None:
    # Только чтение: у хука нет причин трогать файлы проекта.
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
    """Исключён ли путь из индекса — по встроенному списку И по настройкам проекта.

    Без второй половины гард выдаёт дед-энды: `exclude_dirs` и
    `exclude_file_patterns` из `<repo>/.code-index/config.json` не попадают
    в индекс, и MCP их не отдаст. Сравнение — ПО СЕГМЕНТАМ, а не подстрокой:
    встроенный список задан как `/.venv/`, а путь обычно относительный.
    """
    if case_insensitive is None:
        case_insensitive = default_case_insensitive()
    rel_l = fold_path(rel.replace("\\", "/"), case_insensitive)
    segments = [s for s in rel_l.split("/") if s]

    if any(s in NEVER_INDEXED for s in segments):
        return True

    # Конкретный существующий файл — спрашиваем ФАКТ у индекса, а не гадаем по
    # расширению: так отсекаются дотфайлы, `Dockerfile`, `.svg` и прочее, чего
    # walker не берёт (списка типов снаружи нет — он зашит в индексаторе).
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
        # Образец сверяем с КАЖДЫМ сегментом: цель бывает и файлом, и маской.
        for p in pats:
            if not isinstance(p, str):
                continue
            p = fold_path(p, case_insensitive)
            if any(glob_match(p, s) for s in segments):
                return True
    return False
