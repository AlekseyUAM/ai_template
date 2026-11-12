#!/usr/bin/env python
"""
load-config-optimized.py
Кроссплатформенная загрузка конфигурации 1С: грузит в ИБ только изменённые файлы
(git diff относительно HEAD по src/cf) через 1c-batch load-config --list-file.

Частичная загрузка — единственный режим: она корректно отрабатывает все операции
(добавление/удаление реквизита, добавление/удаление объекта) с тем же результатом,
что и полная перезагрузка, но быстрее.

Использование:
    python .claude/tools/load-config-optimized.py [--state PATH]

С --state грузятся только файлы, изменившиеся с последней успешной загрузки:
в PATH хранится манифест sha256 (обычно logs/task#<id>/load-state.json).
Без --state — весь git diff vs HEAD, как раньше.

Скрипт печатает ход загрузки в stdout и завершается кодом 0 при успехе
(или «нет изменённых файлов») и ненулевым кодом при ошибке загрузки. Оркестратор
запускает его в фоне с перенаправлением вывода в лог — см. правило
`optimized-config-loading`.
"""

import argparse
import sys
import os
import subprocess
import tempfile
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STATE_VERSION = 1
STATE_HASH = "sha256"

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


def get_dirty_paths() -> List[str]:
    """Сырые изменённые пути (относительно src/cf) из git.

    Учитывает отслеживаемые изменения (git diff HEAD) и новые untracked-файлы
    (git ls-files --others). Пути нормализуются к прямым слэшам, префикс
    src/cf/ отбрасывается, ConfigDumpInfo.xml (в т.ч. вложенный) исключается:
    это не объект метаданных, через -listFile он даёт ошибку «URL ... не может
    быть преобразован в полное имя объекта метаданных»; платформа обновит его
    сама по флагу -updateConfigDumpInfo.
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

    result: List[str] = []
    seen = set()
    for f in raw:
        f = f.strip().replace("\\", "/")
        if not f:
            continue
        rel = f.replace("src/cf/", "", 1)
        if rel == "ConfigDumpInfo.xml" or rel.endswith("/ConfigDumpInfo.xml"):
            continue
        if rel in seen:
            continue
        seen.add(rel)
        result.append(rel)
    return result


def expand_to_load_paths(raw: List[str]) -> List[str]:
    """Развернуть изменённые пути в список файлов для -listFile.

    По образцу навыка db-load-git в список попадают:
      - корневой файл каждого изменённого объекта (<Вид>/<Имя>.xml);
      - сам изменённый файл (XML вложенных объектов: Forms/<Ф>.xml,
        Templates/<М>.xml; модули; Ext/*) — платформа по корню вложенные
        объекты и их содержимое не грузит;
      - для изменённого не-XML файла или файла внутри Ext — все файлы каталога
        Ext объекта (как в db-load-git).

    Удалённые файлы пропускаются: платформа молча игнорирует отсутствующий файл
    в -listFile; корень объекта при этом добавляется, если существует, — через
    него платформа подхватит изменённый состав.
    """
    cf_dir = get_project_root() / "src" / "cf"
    seen = set()
    result: List[str] = []

    def add(rel: str) -> None:
        rel = rel.replace("\\", "/")
        if rel in seen:
            return
        seen.add(rel)
        result.append(rel)

    for rel in raw:
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


def get_changed_files() -> List[str]:
    """Изменённые файлы конфигурации для -listFile (без учёта состояния)."""
    files, _, _, _ = collect_changes(None)
    return files

def file_sha256(path: Path) -> Optional[str]:
    """sha256 содержимого файла; None, если файл отсутствует или не читается."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def load_state(path: Optional[str]) -> Dict[str, str]:
    """Прочитать манифест «что уже загружено»; при любой проблеме — пусто.

    Битый JSON, неизвестная версия/алгоритм или отсутствие файла не срывают
    загрузку: вызывающий грузит полный diff vs HEAD. Проблема только логируется.
    """
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"⚠️  Не удалось прочитать состояние {path}: {e} — гружу весь diff",
              file=sys.stderr)
        return {}

    if (not isinstance(data, dict)
            or data.get("version") != STATE_VERSION
            or data.get("hash", STATE_HASH) != STATE_HASH
            or not isinstance(data.get("files"), dict)):
        print(f"⚠️  Неизвестный формат состояния {path} — гружу весь diff",
              file=sys.stderr)
        return {}

    return {k: v for k, v in data["files"].items()
            if isinstance(k, str) and isinstance(v, str)}


def save_state(path: Optional[str], files: Dict[str, str]) -> None:
    """Атомарно записать манифест; ошибка записи не срывает загрузку."""
    if not path:
        return
    data = {
        "version": STATE_VERSION,
        "hash": STATE_HASH,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": {k: files[k] for k in sorted(files)},
    }
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    except OSError as e:
        print(f"⚠️  Не удалось сохранить состояние {path}: {e}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def filter_loaded(
    candidates: List[str], state: Dict[str, str]
) -> Tuple[List[str], Dict[str, str], List[str], List[str]]:
    """Разделить кандидатов на изменённых и уже загруженных.

    Кандидаты — объединение сырых путей из git и ключей прежнего состояния:
    второе ловит «изменил → загрузил → откатил к HEAD» — файл исчез из diff,
    но его текущее содержимое отличается от загруженного. Возвращает
    (изменённые, снимок для нового состояния, удалённые, пропущенные).
    Снимок включает все существующие кандидаты — и изменённые, и нет.
    """
    cf_dir = get_project_root() / "src" / "cf"
    order: List[str] = []
    seen = set()
    for rel in list(candidates) + sorted(state):
        if rel in seen:
            continue
        seen.add(rel)
        order.append(rel)

    changed: List[str] = []
    snapshot: Dict[str, str] = {}
    deleted: List[str] = []
    skipped: List[str] = []
    for rel in order:
        digest = file_sha256(cf_dir / rel)
        if digest is None:
            if rel in state:
                deleted.append(rel)
            continue
        snapshot[rel] = digest
        if state.get(rel) == digest:
            skipped.append(rel)
        else:
            changed.append(rel)
    return changed, snapshot, deleted, skipped


def collect_changes(
    state: Optional[Dict[str, str]] = None
) -> Tuple[List[str], Optional[Dict[str, str]], List[str], List[str]]:
    """Собрать файлы для загрузки с учётом состояния.

    state=None — без состояния (весь diff vs HEAD), снимок не снимается.
    state={} — состояние включено, но файла ещё нет: снимок будет создан.
    """
    dirty = get_dirty_paths()
    if state is None:
        return expand_to_load_paths(dirty), None, [], []
    changed, snapshot, deleted, skipped = filter_loaded(dirty, state)
    return expand_to_load_paths(changed), snapshot, deleted, skipped

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Частичная загрузка изменённых файлов конфигурации 1С")
    parser.add_argument(
        "--state", metavar="PATH",
        help="манифест «что уже загружено» (обычно "
             "logs/task#<id>/load-state.json); без него грузится весь diff vs HEAD")
    return parser.parse_args(argv)

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

def main(argv: Optional[List[str]] = None) -> int:
    """Главная функция"""
    _force_utf8_output()
    args = parse_args(argv)
    state_path = os.path.abspath(args.state) if args.state else None
    if state_path and os.path.isdir(state_path):
        print(f"❌ --state указывает на каталог: {state_path}", file=sys.stderr)
        return 2

    print("📦 Загрузка конфигурации 1С (частичная, только изменённые файлы)")
    print()

    print("🔍 Определение изменённых файлов...")
    state = load_state(state_path) if state_path else None
    files, snapshot, deleted, skipped = collect_changes(state)

    for rel in deleted:
        print(f"⚠️  Удалён ранее загруженный файл (забыт в состоянии): {rel}")
    if skipped:
        print(f"⏭️  Пропущено как уже загруженное: {len(skipped)}")
        for rel in skipped:
            print(f"  - {rel}")
        print()

    if not files:
        print("✅ Нет изменённых файлов конфигурации — загрузка не требуется")
        if state_path is not None:
            save_state(state_path, snapshot or {})
        return 0

    code = run_optimized_load(files)
    if code == 0 and state_path is not None:
        save_state(state_path, snapshot or {})
    return code

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Отменено пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}", file=sys.stderr)
        sys.exit(1)
