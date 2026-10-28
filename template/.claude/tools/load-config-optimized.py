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

def _force_utf8_output() -> None:
    """Перевести stdout/stderr в UTF-8.

    При перенаправлении вывода в файл (правило optimized-config-loading пишет лог)
    Python на Windows берёт ANSI-кодировку локали (cp1251), в которой нет эмодзи
    из print() — скрипт падал бы на «'charmap' codec can't encode character».
    reconfigure доступен с Python 3.7; errors="replace" — чтобы вывод не ронял
    загрузку даже на несовместимом символе.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

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

    Корневой файл объекта (<Вид>/<Имя>.xml) платформа в -listFile грузит вместе
    с его дочерними объектами, но НЕ с их содержимым: формы, макеты и модули
    нужно перечислять отдельными файлами (это делает get_changed_files). Здесь
    по любому подфайлу вычисляется только корень объекта.

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
    """Список файлов изменённых объектов конфигурации для -listFile (из git).

    Учитывает и отслеживаемые изменения (git diff), и новые untracked-файлы
    (git ls-files --others). Пути — относительно src/cf. По образцу навыка
    db-load-git в список попадают:
      - корневой файл каждого изменённого объекта (<Вид>/<Имя>.xml);
      - сам изменённый файл (XML вложенных объектов: Forms/<Ф>.xml,
        Templates/<М>.xml; модули; Ext/*) — платформа по корню вложенные
        объекты и их содержимое не грузит;
      - для изменённого не-XML файла или файла внутри Ext — все файлы каталога
        Ext объекта (как в db-load-git).

    Удалённые файлы пропускаются: платформа молча игнорирует отсутствующий файл
    в -listFile. ConfigDumpInfo.xml (в т.ч. вложенный) исключается: это не объект
    метаданных, через -listFile он даёт ошибку «URL ... не может быть
    преобразован в полное имя объекта метаданных»; платформа обновит его сама по
    флагу -updateConfigDumpInfo.
    """
    project_root = get_project_root()
    os.chdir(project_root)

    # core.quotePath=false — чтобы кириллические имена не экранировались в \nnn.
    # encoding="utf-8" — git выводит UTF-8 (при quotePath=false); без явной
    # кодировки text=True декодирует выводом локали (cp1251) и падает на кириллице.
    raw: List[str] = []
    try:
        diff = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", "HEAD",
             "--", "src/cf/"],
            capture_output=True, text=True, check=False, encoding="utf-8",
        )
        if diff.returncode != 0:
            # HEAD может не существовать (пустой репозиторий)
            diff = subprocess.run(
                ["git", "-c", "core.quotePath=false", "diff", "--name-only",
                 "--", "src/cf/"],
                capture_output=True, text=True, check=False, encoding="utf-8",
            )
        raw.extend(diff.stdout.splitlines())

        others = subprocess.run(
            ["git", "-c", "core.quotePath=false", "ls-files", "--others",
             "--exclude-standard", "--", "src/cf/"],
            capture_output=True, text=True, check=False, encoding="utf-8",
        )
        raw.extend(others.stdout.splitlines())
    except Exception as e:
        print(f"❌ Ошибка при получении списка файлов: {e}", file=sys.stderr)
        return []

    cf_dir = project_root / "src" / "cf"
    seen = set()
    result: List[str] = []

    def add(rel: str) -> None:
        rel = rel.replace("\\", "/")
        if rel in seen:
            return
        seen.add(rel)
        result.append(rel)

    for f in raw:
        f = f.strip().replace("\\", "/")
        if not f:
            continue
        rel = f.replace("src/cf/", "", 1)
        # ConfigDumpInfo.xml (в т.ч. вложенный) — не объект метаданных.
        if rel == "ConfigDumpInfo.xml" or rel.endswith("/ConfigDumpInfo.xml"):
            continue

        # Корневой файл объекта грузим всегда, если он существует. Configuration.xml
        # остаётся в списке и при удалении объекта — через него платформа подхватит
        # изменённый состав.
        root = _object_root(rel)
        if root == "Configuration.xml" or (cf_dir / root).exists():
            add(root)

        # Удалённый файл платформа в -listFile молча пропускает — не добавляем.
        if not (cf_dir / rel).exists():
            continue

        parts = rel.split("/")
        # Файл верхнего уровня или сам корень объекта уже обработаны выше.
        if len(parts) <= 2:
            continue

        # Сам изменённый подфайл: XML вложенных объектов (Forms/*.xml,
        # Templates/*.xml), модули, Ext/*.
        add(rel)

        # Для не-XML файла или файла внутри Ext — все файлы каталога Ext объекта
        # (как в db-load-git): отдельный изменённый модуль не несёт остального Ext.
        if (not rel.endswith(".xml")) or "Ext" in parts:
            ext_dir = cf_dir / parts[0] / parts[1] / "Ext"
            if ext_dir.is_dir():
                for p in sorted(ext_dir.rglob("*")):
                    if p.is_file():
                        add(str(p.relative_to(cf_dir)).replace("\\", "/"))

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

    # Создай временный файл со списком. encoding='utf-8' обязателен: конфигуратор
    # читает -listFile как UTF-8, а без явной кодировки файл пишется в кодировке
    # локали (cp1251 на Windows) и пути с кириллицей ломаются.
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.txt',
        delete=False,
        encoding='utf-8',
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
    _force_utf8_output()
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
