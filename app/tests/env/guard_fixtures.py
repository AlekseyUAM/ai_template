"""Общие фикстуры для тестов code-index-guard: временное репо и index.db."""
import os
import sqlite3
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib.config import GuardConfig, indexed_paths  # noqa: E402
from code_index_guard_lib.context import GuardContext  # noqa: E402
from code_index_guard_lib.paths import default_case_insensitive  # noqa: E402

MTIME = 1700000000

_FILES = {
    "src/main.rs": ("code", "fn main() {}\n"),
    "Cargo.toml": ("text", "[package]\nname = \"demo\"\n"),
    "README.md": ("text", "# demo\n"),
    "Cargo.lock": ("plain", "version = 3\n"),
    ".gitignore": ("plain", "target/\n"),
    "target/release/demo": ("plain", "binary\n"),
}


def build_repo(tmp_path: Path, *, v4: bool = False, stale: bool = False,
               oversize: bool = False) -> Path:
    root = tmp_path / "repo"
    for rel, (_kind, text) in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        # mtime на диске должен совпадать с files.mtime индекса, иначе
        # read_is_blockable решит, что индекс отстал.
        os.utime(p, (MTIME, MTIME))
    db = root / ".code-index" / "index.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, mtime INTEGER)")
    conn.execute("CREATE TABLE file_contents (file_id INTEGER, oversize INTEGER)")
    ids = {}
    for i, (rel, (kind, _text)) in enumerate(_FILES.items(), start=1):
        conn.execute("INSERT INTO files (id, path, mtime) VALUES (?, ?, ?)",
                     (i, rel, MTIME))
        ids[rel] = i
    # ровно одна таблица текста, как в настоящей схеме:
    # v4 — text_files, v5 — text_contents.
    table = "text_files" if v4 else "text_contents"
    conn.execute(f"CREATE TABLE {table} (file_id INTEGER)")
    for rel in ("Cargo.toml", "README.md"):
        conn.execute(f"INSERT INTO {table} (file_id) VALUES (?)", (ids[rel],))
    # main.rs — код с сохранённым контентом (oversize=0) либо oversized (oversize=1).
    # Строки в таблице текста у него нет: serveability решает по file_contents.
    conn.execute("INSERT INTO file_contents (file_id, oversize) VALUES (?, ?)",
                 (ids["src/main.rs"], 1 if oversize else 0))
    conn.commit()
    conn.close()
    # Каталоги тоже относим к MTIME: иначе корень репо с mtime «сейчас» выглядит
    # изменившимся после индексации, и листинг каталога законно пропускается.
    for d in sorted((p for p in root.rglob("*") if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
        os.utime(d, (MTIME, MTIME))
    os.utime(root, (MTIME, MTIME))
    if stale:
        p = root / "Cargo.toml"
        p.write_text("[package]\nname = \"changed\"\n", encoding="utf-8")
        os.utime(p, (MTIME + 100, MTIME + 100))
    return root


def make_ctx(root: Path, *, alias: str = "repo") -> GuardContext:
    ci = default_case_insensitive()
    cfg = GuardConfig(local=[(str(root), alias)], mcp_prefix="mcp__code_index__")
    return GuardContext(cfg, indexed_paths(cfg, case_insensitive=ci), ci)
