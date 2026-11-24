#!/usr/bin/env python
"""Run the main-configuration check-modules only when real BSL code changed.

The check is mandatory after the infobase load: `/CheckModules` checks the
configuration loaded in the DB, so before the load it would check the previous
state. For a metadata-only task the new modules are empty (BOM + newline), so
compilation has nothing to check and the run only costs a minute. This wrapper
delegates to the same `1c-batch check-modules --thin-client --server` when at
least one changed `.bsl` has code. Extension modules are checked separately by
`run-tests.py`.

The successful result is cached by the source-tree hash in
logs/.check-modules-cache/cf.json - the same cache `run-tests.py` reuses, so the
main configuration is not compiled twice.

Usage:
    python .claude/tools/check-modules.py [--force]

--force runs the check even when every changed module is empty, ignores the
cache and refreshes it after a successful run.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from module_changes import has_nonempty_changed_bsl  # noqa: E402
from check_cache import cache_hit, cache_store, tree_hash  # noqa: E402


def get_project_root() -> Path:
    """Project root (two levels above .claude/tools)."""
    return Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in args
    root = get_project_root()

    if not force:
        has_code = has_nonempty_changed_bsl(root, "src/cf")
        if has_code is False:
            print("⏭️  check-modules: пропуск — изменённых непустых .bsl нет "
                  "(метаданные или пустые модули).")
            return 0
        if has_code is None:
            print("⚠️  check-modules: git недоступен — выполняю проверку.")

    source = root / "src" / "cf"
    source_hash = tree_hash(source)
    if not force and cache_hit(root, None, source_hash):
        print("♻️  check-modules: исходники не менялись с прошлой успешной "
              "проверки — пропускаю компиляцию (кэш).")
        return 0

    wrapper = root / ".claude/skills/1c-batch/scripts/1c-batch.py"
    if not wrapper.is_file():
        print(f"❌ не найден wrapper 1c-batch: {wrapper}", file=sys.stderr)
        return 1

    cmd = [sys.executable, str(wrapper), "check-modules", "--thin-client", "--server"]
    print("🔎 check-modules (1c-batch): есть непустые изменённые .bsl")
    rc = subprocess.run(cmd, cwd=root).returncode
    if rc == 0:
        cache_store(root, None, source_hash)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
