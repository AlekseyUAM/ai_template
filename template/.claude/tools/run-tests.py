#!/usr/bin/env python3
"""
run-tests.py
Кроссплатформенный запуск юнит-тестов 1С: стартует базу в режиме предприятия
через `1c-batch run-enterprise -C "ВыполнитьЗапускЮнитТестов=<абс. путь к конфигу>"`.

Использование:
    python .claude/tools/run-tests.py [КОНФИГ]

КОНФИГ    путь к JSON-файлу конфигурации тестов (по умолчанию configs/test.json),
          передаётся в конфигурацию как абсолютный путь.
"""

import sys
import os
import subprocess
from pathlib import Path

# Имя параметра запуска, который конфигурация обрабатывает в /C
LAUNCH_PARAM = "ВыполнитьЗапускЮнитТестов"
DEFAULT_CONFIG = "configs/test.json"


def get_project_root() -> Path:
    """Корень проекта (на два уровня выше .claude/tools)."""
    return Path(__file__).resolve().parent.parent.parent


def batch_cmd() -> list[str]:
    """Префикс команды: локальная (проектная) копия 1c-batch через wrapper."""
    wrapper = get_project_root() / ".claude/skills/1c-batch/scripts/1c-batch.py"
    return [sys.executable, str(wrapper)]


def run_tests(config_arg: str) -> int:
    """Запусти предприятие с параметром /C для прогона тестов."""
    project_root = get_project_root()

    # Абсолютный путь к конфигу тестов
    config_path = Path(config_arg)
    if not config_path.is_absolute():
        config_path = (project_root / config_path).resolve()
    else:
        config_path = config_path.resolve()

    # Проверки файла
    if not config_path.exists():
        print(f"❌ Файл конфигурации тестов не найден: {config_path}", file=sys.stderr)
        return 1
    if config_path.stat().st_size == 0:
        print(f"⚠️  Файл конфигурации тестов пуст: {config_path}")
        print("   Прогон может ничего не выполнить — проверьте содержимое.")

    c_value = f"{LAUNCH_PARAM}={config_path}"

    print("🧪 Запуск юнит-тестов 1С")
    print(f"   Конфиг: {config_path}")
    print(f"   Параметр /C: {c_value}")
    print()
    print(f'Команда: 1c-batch run-enterprise -C "{c_value}"')

    try:
        result = subprocess.run(
            batch_cmd() + ["run-enterprise", "-C", c_value],
            cwd=project_root,
        )
    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.",
              file=sys.stderr)
        return 1

    print()
    if result.returncode == 0:
        print("✅ Предприятие запущено (прогон тестов идёт в сеансе 1С).")
        print("   Результаты смотри там, куда их пишет обработчик тестов в конфигурации.")
    else:
        print("❌ Ошибка запуска предприятия")
    return result.returncode


def main() -> int:
    args = [a for a in sys.argv[1:] if a not in ("--help", "-h")]
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        return 0

    config_arg = args[0] if args else DEFAULT_CONFIG
    return run_tests(config_arg)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Отменено пользователем")
        sys.exit(1)
