#!/usr/bin/env python3
"""CLI benchmark-прогона: задачи в claude-ds, метрики и анализ template."""
from __future__ import annotations

import sys
from pathlib import Path

# Windows-консоль часто cp1251/cp866: emoji и «→» в логах роняют print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_run import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
