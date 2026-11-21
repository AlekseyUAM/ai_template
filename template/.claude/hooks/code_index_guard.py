#!/usr/bin/env python
"""PreToolUse hook code-index-guard (Python port).

Source: Regsorm/code-index-mcp, crates/code-index-guard, v1.15.4
(commit fd3199f204183179aad2d39873a0341d5849ddae), MIT license.
Redirects native Read/Grep/Glob/Bash/PowerShell over indexed
directories to code-index tools. When in doubt, it abstains.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_index_guard_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
