#!/usr/bin/env python3
"""
load-config-optimized.py
Кроссплатформенная загрузка конфигурации 1С: грузит в ИБ только изменённые файлы
(git diff относительно HEAD по src/cf) через 1c-batch load-config --list-file.

Использование:
    python .claude/tools/load-config-optimized.py [--full]

--full     выполнить полную загрузку (без --list-file)
"""

import sys
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

def get_project_root() -> Path:
    """Получи корень проекта"""
    script_dir = Path(__file__).parent
    return script_dir.parent.parent

def batch_cmd() -> List[str]:
    """Префикс команды: локальная (проектная) копия 1c-batch через wrapper."""
    wrapper = get_project_root() / ".claude/skills/1c-batch/scripts/1c-batch.py"
    return [sys.executable, str(wrapper)]

def get_changed_files() -> List[str]:
    """Получи список изменённых файлов конфигурации из git"""
    project_root = get_project_root()
    os.chdir(project_root)

    try:
        # Попробуй получить файлы из git diff HEAD
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "src/cf/"],
            capture_output=True,
            text=True,
            check=False
        )

        if result.returncode != 0:
            # Если HEAD не существует, попробуй просто git diff
            result = subprocess.run(
                ["git", "diff", "--name-only", "--", "src/cf/"],
                capture_output=True,
                text=True,
                check=False
            )

        files = result.stdout.strip().split('\n')

        # Преобразуй пути: src/cf/... → ...
        files = [f.replace("src/cf/", "", 1) for f in files if f]

        # Удали пустые строки
        files = [f for f in files if f.strip()]

        return files

    except Exception as e:
        print(f"❌ Ошибка при получении списка файлов: {e}", file=sys.stderr)
        return []

def run_full_load() -> int:
    """Выполни полную загрузку конфигурации"""
    print("🔄 Режим: полная загрузка (--full)")
    print()
    print("Команда: 1c-batch load-config src/cf")

    try:
        result = subprocess.run(
            batch_cmd() + ["load-config", "src/cf"],
            cwd=get_project_root()
        )

        print()
        if result.returncode == 0:
            print("✅ Полная загрузка завершена")
        else:
            print("❌ Ошибка при загрузке конфигурации")

        return result.returncode
    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.", file=sys.stderr)
        return 1

def run_optimized_load(files: List[str]) -> int:
    """Выполни оптимизированную загрузку конфигурации"""
    if not files:
        print("✅ Нет изменённых файлов конфигурации")
        return 0

    print(f"📋 Найдено изменённых файлов: {len(files)}")
    print()

    # Покажи список файлов
    print("Файлы для загрузки:")
    for f in files:
        print(f"  - {f}")
    print()

    # Создай временный файл со списком
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        delete=False,
        dir=os.path.dirname(os.path.abspath(__file__))
    ) as tmp:
        for f in files:
            tmp.write(f + '\n')
        temp_list = tmp.name

    try:
        print("Режим: частичная загрузка (--list-file)")
        print()
        print(f"Команда: 1c-batch load-config src/cf --list-file {temp_list}")

        result = subprocess.run(
            batch_cmd() + ["load-config", "src/cf", "--list-file", temp_list],
            cwd=get_project_root()
        )

        print()
        if result.returncode == 0:
            print("✅ Оптимизированная загрузка завершена")
        else:
            print("❌ Ошибка при загрузке конфигурации")

        return result.returncode

    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.", file=sys.stderr)
        return 1

    finally:
        # Удали временный файл
        try:
            os.unlink(temp_list)
        except:
            pass

def main():
    """Главная функция"""
    print("📦 Загрузка конфигурации 1С (оптимизированная)")
    print()

    # Проверь аргументы
    full_load = "--full" in sys.argv

    if full_load:
        return run_full_load()
    else:
        print("🔍 Определение изменённых файлов...")
        files = get_changed_files()

        if not files:
            print("✅ Нет изменённых файлов конфигурации")
            print()
            print("📊 Совет: для гарантии консистентности выполните полную загрузку:")
            print("   python .claude/tools/load-config-optimized.py --full")
            return 0

        return run_optimized_load(files)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Отменено пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}", file=sys.stderr)
        sys.exit(1)
