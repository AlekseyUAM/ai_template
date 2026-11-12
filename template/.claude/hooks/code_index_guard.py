#!/usr/bin/env python
"""PreToolUse-хук code-index-guard (Python-порт).

Источник: Regsorm/code-index-mcp, crates/code-index-guard, v1.15.4
(commit fd3199f204183179aad2d39873a0341d5849ddae), лицензия MIT.
Перенаправляет нативные Read/Grep/Glob/Bash/PowerShell по индексированным
каталогам в инструменты code-index. При сомнении воздерживается.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_index_guard_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
