#!/usr/bin/env python
"""
load-config-optimized.py
Cross-platform 1C configuration load: loads only changed files into the IB
(git diff against HEAD under src/cf) via 1c-batch load-config --list-file.

Partial load is the only mode: it correctly handles all operations
(adding/removing an attribute, adding/removing an object) with the same result
as a full reload, but faster.

Usage:
    python .claude/tools/load-config-optimized.py [--state PATH]
                                                [--allow-warnings]

With --state only files changed since the last successful load are loaded:
PATH holds a sha256 manifest (usually logs/task#<id>/load-state.json).
Without --state - the whole git diff vs HEAD, as before.

The script prints load progress to stdout. Return codes:
    0 - load applied, no platform warnings (or --allow-warnings
        was passed), or "no changed files";
    2 - load applied, but the platform ignored some properties or
        produced other warnings (facet, Исключение XDTO, invalid
        enum value, etc.): the sources are incorrect, state is not
        saved;
    otherwise - return code of the child 1c-batch load-config.

The orchestrator runs it synchronously (a regular Bash without run_in_background)
with output redirected to a log - see rule `optimized-config-loading`.
"""

import argparse
import re
import sys
import os
import subprocess
import tempfile
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

STATE_VERSION = 1
STATE_HASH = "sha256"

# Platform warning markers for invalid sources: with them the load is
# applied (code 0), but some metadata is silently lost.
_PROPERTY_MARK = "Неверное свойство объекта метаданных"
_PROPERTY_RE = re.compile(
    r"Свойство (\S+) не входит в состав объекта метаданных (\w+)")
# The platform writes "facet" without brackets ("facet фиксации ControlType ..."). A plain
# substring would also catch file names/paths (FacetGroups.xml), so - only the
# word "facet" followed by a platform phrase (фиксации/перечисления/...);
# the summary shows the token as is.
_FACET_RE = re.compile(r"\bfacet\s+(?:фиксации|перечисления|движений)",
                       re.IGNORECASE)
_OTHER_MARKS = ("Исключение XDTO", "Неверное значение перечисления")
# Transient IB lock (background job/another session). Retry the
# load: experience shows the second run passes without source changes.
_LOCK_MARK = "Ошибка исключительной блокировки информационной базы"
_LOCK_RETRY_DELAYS = (30, 60)

def _force_utf8_output() -> None:
    """Switch stdout/stderr to UTF-8.

    When output is redirected to a file (the optimized-config-loading rule writes a log),
    Python on Windows uses the ANSI locale encoding (cp1251), which lacks emoji
    from print() - the script would fail with "'charmap' codec can't encode character".
    reconfigure is available since Python 3.7; errors="replace" - so output does not crash
    the load even on an incompatible character.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

def get_project_root() -> Path:
    """Get the project root"""
    script_dir = Path(__file__).parent
    return script_dir.parent.parent

def batch_cmd() -> List[str]:
    """Command prefix: local (project) copy of 1c-batch via wrapper."""
    wrapper = get_project_root() / ".claude/skills/1c-batch/scripts/1c-batch.py"
    return [sys.executable, str(wrapper)]

def _object_root(rel: str) -> str:
    """Reduce a file path inside src/cf to the root file of the metadata object.

    The root file of an object (<Kind>/<Name>.xml) is loaded by the platform in -listFile together
    with its child objects, but NOT with their content: forms, templates and modules
    must be listed as separate files (get_changed_files does that). Here
    only the object root is computed from any subfile.

        Configuration.xml                           -> Configuration.xml
        Catalogs/Номенклатура.xml                   -> Catalogs/Номенклатура.xml
        Catalogs/Номенклатура/Ext/ObjectModule.bsl  -> Catalogs/Номенклатура.xml
        Catalogs/Номенклатура/Forms/Ф.xml           -> Catalogs/Номенклатура.xml
    """
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    if len(parts) <= 1:
        # Top-level file (Configuration.xml etc.)
        return rel
    kind, name = parts[0], parts[1]
    if name.endswith(".xml"):
        name = name[:-4]
    return f"{kind}/{name}.xml"


def get_dirty_paths() -> List[str]:
    """Raw changed paths (relative to src/cf) from git.

    Accounts for tracked changes (git diff HEAD) and new untracked files
    (git ls-files --others). Paths are normalized to forward slashes, the
    src/cf/ prefix is dropped, ConfigDumpInfo.xml (including nested) is excluded:
    it is not a metadata object, via -listFile it gives the error "URL ... не может
    быть преобразован в полное имя объекта метаданных"; the platform will update it
    itself with the -updateConfigDumpInfo flag.
    """
    project_root = get_project_root()
    os.chdir(project_root)

    # core.quotePath=false - so Cyrillic names are not escaped to \nnn.
    # encoding="utf-8" - git outputs UTF-8 (with quotePath=false); without an explicit
    # encoding text=True decodes with the locale output (cp1251) and fails on Cyrillic.
    raw: List[str] = []
    try:
        diff = subprocess.run(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only", "HEAD",
             "--", "src/cf/"],
            capture_output=True, text=True, check=False, encoding="utf-8",
        )
        if diff.returncode != 0:
            # HEAD may not exist (empty repository)
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
    """Expand changed paths into a file list for -listFile.

    Following the db-load-git skill pattern, the list includes:
      - the root file of each changed object (<Kind>/<Name>.xml);
      - the changed file itself (XML of nested objects: Forms/<F>.xml,
        Templates/<T>.xml; modules; Ext/*) - the platform does not load nested
        objects and their content by root;
      - for a changed non-XML file or a file inside Ext - all files of the
        object's Ext directory (as in db-load-git).

    Deleted files are skipped: the platform silently ignores a missing file
    in -listFile; the object root is still added if it exists - through
    it the platform picks up the changed composition.
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
        # The object root file is always loaded if it exists. Configuration.xml
        # stays in the list even when an object is deleted - through it the platform picks up
        # the changed composition.
        root = _object_root(rel)
        if root == "Configuration.xml" or (cf_dir / root).exists():
            add(root)

        # The platform silently skips a deleted file in -listFile - do not add it.
        if not (cf_dir / rel).exists():
            continue

        parts = rel.split("/")
        # Top-level file or the object root itself already handled above.
        if len(parts) <= 2:
            continue

        # The changed subfile itself: XML of nested objects (Forms/*.xml,
        # Templates/*.xml), modules, Ext/*.
        add(rel)

        # For a non-XML file or a file inside Ext - all files of the object's Ext directory
        # (as in db-load-git): a separate changed module does not carry the rest of Ext.
        if (not rel.endswith(".xml")) or "Ext" in parts:
            ext_dir = cf_dir / parts[0] / parts[1] / "Ext"
            if ext_dir.is_dir():
                for p in sorted(ext_dir.rglob("*")):
                    if p.is_file():
                        add(str(p.relative_to(cf_dir)).replace("\\", "/"))

    return result


def get_changed_files() -> List[str]:
    """Changed configuration files for -listFile (ignoring state)."""
    files, _, _, _ = collect_changes(None)
    return files

def file_sha256(path: Path) -> Optional[str]:
    """sha256 of file content; None if the file is missing or unreadable."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def load_state(path: Optional[str]) -> Dict[str, str]:
    """Read the "what is already loaded" manifest; on any problem - empty.

    Broken JSON, unknown version/algorithm or a missing file do not break the
    load: the caller loads the full diff vs HEAD. The problem is only logged.
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
    """Atomically write the manifest; a write error does not break the load."""
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
    """Split candidates into changed and already loaded.

    Candidates are the union of raw git paths and keys of the previous state:
    the latter catches "changed -> loaded -> reverted to HEAD" - the file disappeared from the diff,
    but its current content differs from what was loaded. Returns
    (changed, snapshot for the new state, deleted, skipped).
    The snapshot includes all existing candidates - both changed and not.
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
    """Collect files for loading considering state.

    state=None - without state (whole diff vs HEAD), no snapshot is taken.
    state={} - state is enabled, but the file does not exist yet: a snapshot will be created.
    """
    dirty = get_dirty_paths()
    if state is None:
        return expand_to_load_paths(dirty), None, [], []
    changed, snapshot, deleted, skipped = filter_loaded(dirty, state)
    return expand_to_load_paths(changed), snapshot, deleted, skipped

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Command line arguments."""
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
    """Summary of platform warnings about invalid sources.

    - count: total warnings across all checked markers;
    - groups: (object kind, property) -> count by lines
      "Свойство X не входит в состав объекта метаданных <Вид>" - counted by
      lines, not unique values, so a repeated log line
      counts every time;
    - other: (marker, count) by the remaining checked markers.
    """
    count: int
    groups: "OrderedDict[Tuple[str, str], int]"
    other: List[Tuple[str, int]]

    def __bool__(self) -> bool:
        return self.count > 0


def platform_warnings(text: str) -> PlatformWarnings:
    """Build a summary of platform warnings about invalid sources."""
    groups: "OrderedDict[Tuple[str, str], int]" = OrderedDict()
    other: "OrderedDict[str, int]" = OrderedDict()
    for line in text.splitlines():
        if _PROPERTY_MARK in line:
            match = _PROPERTY_RE.search(line)
            if match:
                # In the message: "Свойство <name> ... <Kind>", in the group (Kind, name).
                key = (match.group(2), match.group(1))
                groups[key] = groups.get(key, 0) + 1
            else:
                other[_PROPERTY_MARK] = other.get(_PROPERTY_MARK, 0) + 1
            # A line with a property marker is not counted also as "other".
            continue
        if _FACET_RE.search(line):
            other["facet"] = other.get("facet", 0) + 1
        low = line.lower()
        for mark in _OTHER_MARKS:
            if mark.lower() in low:
                other[mark] = other.get(mark, 0) + 1
    total = sum(groups.values()) + sum(other.values())
    return PlatformWarnings(total, groups, list(other.items()))


def print_platform_warnings(summary: PlatformWarnings) -> None:
    """Print the platform warning summary."""
    if not summary:
        return
    print()
    if summary.groups:
        print(f"⚠️ Платформа проигнорировала "
              f"{sum(summary.groups.values())} свойств (загрузка применена):")
        for (kind, prop), count in summary.groups.items():
            print(f"  - {kind} {prop}: {count}")
    if summary.other:
        print(f"⚠️ Прочие предупреждения платформы "
              f"({sum(count for _m, count in summary.other)}):")
        for mark, count in summary.other:
            print(f"  - {mark}: {count}")


def run_optimized_load(files: List[str], allow_warnings: bool = False,
                       *, retry_delays=_LOCK_RETRY_DELAYS,
                       sleep=time.sleep) -> int:
    """Perform the optimized configuration load and check warnings.

    IB lock (`Ошибка исключительной блокировки…`) is transient: the load is retried
    per `retry_delays` (30 and 60 s by default). `sleep` is parameterized
    for tests.
    """
    if not files:
        print("✅ Нет изменённых файлов конфигурации")
        return 0

    print(f"📋 Найдено изменённых файлов: {len(files)}")
    print()

    # Show the file list
    print("Файлы для загрузки:")
    for f in files:
        print(f"  - {f}")
    print()

    # Create a temporary file with the list. encoding='utf-8' is mandatory: the Configurator
    # reads -listFile as UTF-8, and without an explicit encoding the file is written in the
    # locale encoding (cp1251 on Windows) and paths with Cyrillic break.
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

        # The child process output is captured, printed to the log as before
        # and analyzed: on an invalid metadata property the platform only
        # writes a warning, but exits with code 0.
        attempt = 0
        while True:
            result = subprocess.run(
                batch_cmd() + ["load-config", "src/cf", "--list-file", temp_list],
                cwd=get_project_root(),
                capture_output=True, encoding="utf-8", errors="replace",
            )
            output = (result.stdout or "") + (result.stderr or "")
            if output:
                print(output, end="" if output.endswith("\n") else "\n")

            if (result.returncode != 0 and _LOCK_MARK in output
                    and attempt < len(retry_delays)):
                delay = retry_delays[attempt]
                attempt += 1
                print(f"⚠️ ИБ заблокирована (попытка {attempt} из "
                      f"{len(retry_delays)}): повтор через {delay} с")
                sleep(delay)
                continue
            break

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
        # Remove the temporary file
        try:
            os.unlink(temp_list)
        except:
            pass

def main(argv: Optional[List[str]] = None) -> int:
    """Main function"""
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
    # Save state only on success: on code 2 (ignored
    # properties) the sources must be fixed, and a repeated run should take the same
    # files instead of considering them loaded.
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
