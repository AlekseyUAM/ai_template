#!/usr/bin/env python
"""
load-config-optimized.py
Кроссплатформенная загрузка конфигурации 1С: грузит в ИБ только изменённые файлы
(git diff относительно HEAD по src/cf) через 1c-batch load-config --list-file.

Частичная загрузка — единственный режим: она корректно отрабатывает все операции
(добавление/удаление реквизита, добавление/удаление объекта) с тем же результатом,
что и полная перезагрузка, но быстрее.

Использование:
    python .claude/tools/load-config-optimized.py

Скрипт печатает ход загрузки в stdout и завершается кодом 0 при успехе
(или «нет изменённых файлов») и ненулевым кодом при ошибке загрузки. Оркестратор
запускает его в фоне с перенаправлением вывода в лог — см. правило
`optimized-config-loading`.
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

def _object_root(rel: str) -> str:
    """Свести путь файла внутри src/cf к корневому файлу объекта метаданных.

    Платформа в -listFile принимает только корневые файлы объектов
    (<Вид>/<Имя>.xml), а не подфайлы (модули, формы, макеты). Любой изменённый
    подфайл сводим к корню объекта.

        Configuration.xml                           -> Configuration.xml
        Catalogs/Номенклатура.xml                   -> Catalogs/Номенклатура.xml
        Catalogs/Номенклатура/Ext/ObjectModule.bsl  -> Catalogs/Номенклатура.xml
        Catalogs/Номенклатура/Forms/Ф.xml           -> Catalogs/Номенклатура.xml
    """
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if len(parts) <= 1:
        # Файл верхнего уровня (Configuration.xml и т.п.)
        return rel
    kind, name = parts[0], parts[1]
    if name.endswith(".xml"):
        name = name[:-4]
    return f"{kind}/{name}.xml"


def get_changed_files() -> List[str]:
    """Список корневых файлов изменённых объектов конфигурации из git.

    Учитывает и отслеживаемые изменения (git diff), и новые untracked-файлы
    (git ls-files --others). Каждый изменённый подфайл объекта сводится к
    корневому файлу объекта. Пути — относительно src/cf.

    ConfigDumpInfo.xml исключается: это не объект метаданных, через -listFile он
    даёт ошибку «URL ... не может быть преобразован в полное имя объекта
    метаданных»; платформа обновит его сама по флагу -updateConfigDumpInfo.
    """
    project_root = get_project_root()
    os.chdir(project_root)

    # core.quotePath=false — чтобы кириллические имена не экранировались в \nnn
    raw: List[str] = []
    try:
        diff = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", "HEAD",
             "--", "src/cf/"],
            capture_output=True, text=True, check=False,
        )
        if diff.returncode != 0:
            # HEAD может не существовать (пустой репозиторий)
            diff = subprocess.run(
                ["git", "-c", "core.quotePath=false", "diff", "--name-only",
                 "--", "src/cf/"],
                capture_output=True, text=True, check=False,
            )
        raw.extend(diff.stdout.splitlines())

        others = subprocess.run(
            ["git", "-c", "core.quotePath=false", "ls-files", "--others",
             "--exclude-standard", "--", "src/cf/"],
            capture_output=True, text=True, check=False,
        )
        raw.extend(others.stdout.splitlines())
    except Exception as e:
        print(f"❌ Ошибка при получении списка файлов: {e}", file=sys.stderr)
        return []

    cf_dir = project_root / "src" / "cf"
    seen = set()
    result: List[str] = []
    for f in raw:
        f = f.strip()
        if not f:
            continue
        rel = f.replace("src/cf/", "", 1)
        if rel == "ConfigDumpInfo.xml":
            continue
        root = _object_root(rel)
        if root in seen:
            continue
        # Грузим только существующие файлы; удалённые объекты подхватятся через
        # изменённый Configuration.xml, который остаётся в списке.
        if root != "Configuration.xml" and not (cf_dir / root).exists():
            continue
        seen.add(root)
        result.append(root)

    return result

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
    print("📦 Загрузка конфигурации 1С (частичная, только изменённые файлы)")
    print()

    print("🔍 Определение изменённых файлов...")
    files = get_changed_files()

    if not files:
        print("✅ Нет изменённых файлов конфигурации — загрузка не требуется")
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
