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
                                                [--allow-warnings]

С --state грузятся только файлы, изменившиеся с последней успешной загрузки:
в PATH хранится манифест sha256 (обычно logs/task#<id>/load-state.json).
Без --state — весь git diff vs HEAD, как раньше.

Скрипт печатает ход загрузки в stdout. Коды возврата:
    0 — загрузка применена, предупреждений платформы нет (или передано
        --allow-warnings), либо «нет изменённых файлов»;
    2 — загрузка применена, но платформа проигнорировала часть свойств
        (facet, Исключение XDTO, неверное значение перечисления и т.п.):
        исходники некорректны, state не сохраняется;
    иное — код возврата дочернего 1c-batch load-config.

Оркестратор запускает его синхронно (обычный Bash без run_in_background)
с перенаправлением вывода в лог — см. правило `optimized-config-loading`.
"""

import argparse
import re
import sys
import os
import subprocess
import tempfile
import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

STATE_VERSION = 1
STATE_HASH = "sha256"

# Маркеры предупреждений платформы на неверные исходники: загрузка при них
# применяется (код 0), но часть метаданных молча теряется.
_PROPERTY_MARK = "Неверное свойство объекта метаданных"
_PROPERTY_RE = re.compile(
    r"Свойство (\S+) не входит в состав объекта метаданных (\w+)")
# «facet» платформа пишет без скобок («facet фиксации ControlType …»), ищем
# подстроку без учёта регистра; в сводке показываем токен как есть.
_OTHER_MARKS = ("facet", "Исключение XDTO", "Неверное значение перечисления")

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
    parser.add_argument(
        "--allow-warnings", action="store_true",
        help="не считать предупреждения платформы (проигнорированные свойства) "
             "ошибкой: успех и сохранение состояния даже при них")
    return parser.parse_args(argv)

@dataclass
class PlatformWarnings:
    """Сводка предупреждений платформы о неверных исходниках.

    - count: всего предупреждений по всем проверяемым маркерам;
    - groups: (вид объекта, свойство) → count по строкам
      «Свойство X не входит в состав объекта метаданных <Вид>» — счёт по
      строкам, а не по уникальным значениям, поэтому повторяющаяся в логе
      строка учитывается каждый раз;
    - other: (маркер, count) по остальным проверяемым маркерам.
    """
    count: int
    groups: "OrderedDict[Tuple[str, str], int]"
    other: List[Tuple[str, int]]

    def __bool__(self) -> bool:
        return self.count > 0


def platform_warnings(text: str) -> PlatformWarnings:
    """Собрать сводку предупреждений платформы о неверных исходниках."""
    groups: "OrderedDict[Tuple[str, str], int]" = OrderedDict()
    other: "OrderedDict[str, int]" = OrderedDict()
    for line in text.splitlines():
        if _PROPERTY_MARK in line:
            match = _PROPERTY_RE.search(line)
            if match:
                # В сообщении: «Свойство <имя> … <Вид>», в группе (Вид, имя).
                key = (match.group(2), match.group(1))
                groups[key] = groups.get(key, 0) + 1
            else:
                other[_PROPERTY_MARK] = other.get(_PROPERTY_MARK, 0) + 1
        low = line.lower()
        for mark in _OTHER_MARKS:
            if mark.lower() in low:
                other[mark] = other.get(mark, 0) + 1
    total = sum(groups.values()) + sum(other.values())
    return PlatformWarnings(total, groups, list(other.items()))


def print_platform_warnings(summary: PlatformWarnings) -> None:
    """Напечатать сводку предупреждений платформы."""
    if not summary:
        return
    print()
    print(f"⚠️ Платформа проигнорировала {summary.count} свойств "
          f"(загрузка применена):")
    for (kind, prop), count in summary.groups.items():
        print(f"  - {kind} {prop}: {count}")
    for mark, count in summary.other:
        print(f"  - {mark}: {count}")


def run_optimized_load(files: List[str], allow_warnings: bool = False) -> int:
    """Выполни оптимизированную загрузку конфигурации и проверь предупреждения."""
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

        # Вывод дочернего процесса перехватывается, печатается в лог как раньше
        # и анализируется: платформа при неверном свойстве метаданных только
        # пишет предупреждение, но завершается кодом 0.
        result = subprocess.run(
            batch_cmd() + ["load-config", "src/cf", "--list-file", temp_list],
            cwd=get_project_root(),
            capture_output=True, encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "") + (result.stderr or "")
        if output:
            print(output, end="" if output.endswith("\n") else "\n")

        warnings = platform_warnings(output)
        print()
        if result.returncode != 0:
            print("❌ Ошибка при загрузке конфигурации")
            print_platform_warnings(warnings)
            return result.returncode

        if warnings and not allow_warnings:
            print_platform_warnings(warnings)
            print("❌ Загрузка применена, но исходники некорректны: платформа "
                  "проигнорировала перечисленные свойства. Исправь их или "
                  "запусти с --allow-warnings, если это осознанно.")
            return 2

        if warnings:
            print("✅ Оптимизированная загрузка завершена "
                  "(с предупреждениями, --allow-warnings)")
        else:
            print("✅ Оптимизированная загрузка завершена")
        return 0

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

    code = run_optimized_load(files, allow_warnings=args.allow_warnings)
    # Сохраняем состояние только на успех: при коде 2 (проигнорированные
    # свойства) исходники нужно чинить, и повторный запуск должен взять те же
    # файлы, а не считать их загруженными.
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
