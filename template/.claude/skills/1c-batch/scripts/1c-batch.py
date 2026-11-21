#!/usr/bin/env python
"""Run a LOCAL (project) copy of 1c-batch from .claude/skills.

Unlike the global `1c-batch` console command (editable install, shared by all
projects), this wrapper runs the copy next to it. Thus each project uses its
own version of the tool - like the other skills, which are invoked by path
`python .claude/skills/<skill>/scripts/<name>.py`.

Usage:
    python .claude/skills/1c-batch/scripts/1c-batch.py <command> [arguments]

Example:
    python .claude/skills/1c-batch/scripts/1c-batch.py run-enterprise \
        -C "ВыполнитьЗапускЮнитТестов=/abs/configs/test.json"
"""

import os
import sys
import importlib.util

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_local_package() -> None:
    """Register the script directory as the onec_batch package BEFORE any import.

    The package is registered in sys.modules under the name onec_batch with
    submodule search path = SCRIPTS_DIR, so `from onec_batch.cli import ...` and
    relative imports inside (`from .config import ...`) resolve to the local
    copy, not to the global editable install.
    """
    init_path = os.path.join(SCRIPTS_DIR, "__init__.py")
    spec = importlib.util.spec_from_file_location(
        "onec_batch", init_path, submodule_search_locations=[SCRIPTS_DIR]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["onec_batch"] = module
    spec.loader.exec_module(module)


def main() -> None:
    _load_local_package()
    from onec_batch.cli import cli
    cli()  # standalone mode: click prints errors itself and sets the exit code


if __name__ == "__main__":
    main()
