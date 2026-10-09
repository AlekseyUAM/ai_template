#!/usr/bin/env python3
"""Запуск ЛОКАЛЬНОЙ (проектной) копии 1c-batch из .claude/skills.

В отличие от глобальной консольной команды `1c-batch` (editable-install, общий
для всех проектов), этот wrapper исполняет копию, лежащую рядом с ним. Так в
каждом проекте работает своя версия инструмента — как у остальных навыков,
которые зовутся по пути `python .claude/skills/<skill>/scripts/<name>.py`.

Использование:
    python .claude/skills/1c-batch/scripts/1c-batch.py <команда> [аргументы]

Пример:
    python .claude/skills/1c-batch/scripts/1c-batch.py run-enterprise \
        -C "ВыполнитьЗапускЮнитТестов=/abs/configs/test.json"
"""

import os
import sys
import importlib.util

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_local_package() -> None:
    """Зарегистрировать каталог скрипта как пакет onec_batch ДО любого импорта.

    Пакет регистрируется в sys.modules под именем onec_batch с путём поиска
    подмодулей = SCRIPTS_DIR, поэтому `from onec_batch.cli import ...` и
    относительные импорты внутри (`from .config import ...`) резолвятся в
    локальную копию, а не в глобальный editable-install.
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
    cli()  # standalone-режим: click сам печатает ошибки и выставляет код возврата


if __name__ == "__main__":
    main()
