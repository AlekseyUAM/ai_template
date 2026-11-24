#!/usr/bin/env python
"""Shared cache of a successful check-modules run, keyed by the source-tree hash.

Used by both `check-modules.py` (main configuration) and `run-tests.py`
(main configuration and the test extension): a hit means the same sources were
already compiled successfully, so the minute-long Configurator run is skipped.
A failed check is never cached.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

CACHE_SCHEMA = 1


def tree_hash(root: Path) -> str | None:
    """Hash of the check sources; None - no directory (cache is not used)."""
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "ConfigDumpInfo.xml":
            continue
        if path.suffix.lower() not in (".bsl", ".xml"):
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            return None
        digest.update(b"\0")
    return digest.hexdigest()


def cache_path(project_root: Path, extension: str | None) -> Path:
    key = "cf" if not extension else "cfe-" + re.sub(r"[^0-9A-Za-z_.-]+", "_", extension)
    return project_root / "logs" / ".check-modules-cache" / f"{key}.json"


def cache_hit(project_root: Path, extension: str | None,
              source_hash: str | None) -> bool:
    if source_hash is None:
        return False
    path = cache_path(project_root, extension)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(data, dict) and data.get("schema") == CACHE_SCHEMA
            and data.get("hash") == source_hash and data.get("rc") == 0)


def cache_store(project_root: Path, extension: str | None,
                source_hash: str | None) -> None:
    if source_hash is None:
        return
    path = cache_path(project_root, extension)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({
            "schema": CACHE_SCHEMA, "hash": source_hash, "rc": 0,
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
