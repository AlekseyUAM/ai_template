# Инкрементальная загрузка конфигурации: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Грузить в ИБ только файлы, изменившиеся с последней успешной загрузки, без коммитов внутри задачи.

**Architecture:** State-файл задачи (`logs/task#<id>/load-state.json`) хранит манифест `путь → sha256`. Скрипт объединяет сырой git-diff с ключами манифеста, хеширует кандидатов, грузит только изменившихся и обновляет манифест при успехе. Неизменный `Configuration.xml` перестаёт попадать в `-listFile`, поэтому итерации задачи не превращаются в полную перезагрузку.

**Tech Stack:** Python 3.6+ (stdlib: argparse, hashlib, json, subprocess, tempfile, pathlib), pytest.

## Global Constraints

- Только stdlib, Python 3.6+ (в проекте используется `python` из `.venv`; f-strings, `pathlib`, `os.replace` уже применяются).
- `--state PATH` необязателен: без него поведение скрипта не меняется (весь diff vs HEAD).
- State пишется только при успехе: код возврата 0 или «грузить нечего». При ошибке загрузки state не меняется.
- Снимок хешей снимается **до** запуска загрузки.
- State никогда не срывает загрузку: битый/отсутствующий файл — предупреждение в stderr и полный diff. Исключение — `--state` указывает на каталог: код возврата 2.
- Путь `--state` разрешается в абсолютный до `os.chdir(project_root)`.
- Ключи state — пути относительно `src/cf` с прямыми слэшами; `ConfigDumpInfo.xml` (в т.ч. вложенный) в state не попадает.
- Шаблон — единственный источник: правим `template/.claude/...`, не развёрнутые копии.
- Коммиты локально в `main`, без push. Сообщения коммитов — по стилю репозитория (`fix(tools): …`, `docs(tools): …`), в конце строка `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Тесты: `python -m pytest -q app/tests/env/test_load_config_optimized.py` из корня репозитория; в конце — полный `python -m pytest -q`.

## Файловая структура

- Modify: `template/.claude/tools/load-config-optimized.py` — вся логика.
- Modify: `app/tests/env/test_load_config_optimized.py` — тесты.
- Modify: `template/.claude/rules/optimized-config-loading.md` — правило (команда, раздел про state).
- Modify: `template/.claude/skills/task-orchestration/SKILL.md` — вызов с `--state`.

---

### Task 1: Разделить получение diff и разворот путей (без изменения поведения)

**Files:**
- Modify: `template/.claude/tools/load-config-optimized.py:76-176`
- Test: `app/tests/env/test_load_config_optimized.py`

**Interfaces:**
- Produces: `get_dirty_paths() -> List[str]` — нормализованные пути относительно `src/cf` (git diff HEAD + untracked, без `ConfigDumpInfo.xml`, дедуплицированные).
- Produces: `expand_to_load_paths(raw: List[str]) -> List[str]` — разворот путей в список для `-listFile`.
- Produces: `get_changed_files() -> List[str]` — прежняя точка входа (обёртка).

- [ ] **Step 1: Написать падающие тесты на новые функции**

Добавить в `app/tests/env/test_load_config_optimized.py` в конец файла:

```python
def test_get_dirty_paths_normalizes_dedupes_and_filters(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([
        "src/cf/Catalogs/Товары.xml",
        "src/cf/Catalogs/Товары.xml",
        "src/cf/Catalogs/Товары/Ext/ConfigDumpInfo.xml",
    ]))
    monkeypatch.chdir(tmp_path)

    assert mod.get_dirty_paths() == ["Catalogs/Товары.xml"]


def test_expand_to_load_paths_adds_object_root_and_ext(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
    ]
    for rel in files:
        path = tmp_path / "src" / "cf" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")
    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)

    got = mod.expand_to_load_paths(["Catalogs/Товары/Ext/ObjectModule.bsl"])

    assert set(got) == set(files)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py -k "dirty_paths or expand_to_load_paths"`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_dirty_paths'`.

- [ ] **Step 3: Разделить функцию в скрипте**

В `template/.claude/tools/load-config-optimized.py` заменить блок `def get_changed_files() ...` (строки 76–176) на три функции:

```python
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
    return expand_to_load_paths(get_dirty_paths())
```

- [ ] **Step 4: Прогнать все тесты файла**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py`
Expected: `4 passed` (2 старых + 2 новых).

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/load-config-optimized.py app/tests/env/test_load_config_optimized.py
git commit -m "refactor(tools): разделить git-diff и разворот путей в load-config" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Примитивы состояния (sha256, чтение, атомарная запись)

**Files:**
- Modify: `template/.claude/tools/load-config-optimized.py` — импорты, константы, функции состояния.
- Test: `app/tests/env/test_load_config_optimized.py`

**Interfaces:**
- Produces: `file_sha256(path: Path) -> Optional[str]` — hex-дайджест или `None`, если файл отсутствует/не читается.
- Produces: `load_state(path: Optional[str]) -> Dict[str, str]` — толерантное чтение; `{}` при любой проблеме.
- Produces: `save_state(path: Optional[str], files: Dict[str, str]) -> None` — атомарная запись, ошибка только логируется.
- Produces: константы `STATE_VERSION = 1`, `STATE_HASH = "sha256"`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_load_config_optimized.py`. В начало файла добавить `import json` (после `import importlib.util`):

```python
import json
```

В конец файла:

```python
def test_file_sha256_missing_returns_none(tmp_path):
    mod = _load()
    assert mod.file_sha256(tmp_path / "нет-такого") is None


def test_save_and_load_state_roundtrip(tmp_path):
    mod = _load()
    path = tmp_path / "logs" / "task#1" / "load-state.json"
    files = {"Catalogs/Товары.xml": "abc", "Configuration.xml": "def"}

    mod.save_state(str(path), files)

    assert mod.load_state(str(path)) == files
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["hash"] == "sha256"
    assert data["files"] == files


def test_load_state_tolerates_missing_and_broken(tmp_path):
    mod = _load()
    assert mod.load_state(None) == {}
    assert mod.load_state(str(tmp_path / "absent.json")) == {}

    broken = tmp_path / "broken.json"
    broken.write_text("{oops", encoding="utf-8")
    assert mod.load_state(str(broken)) == {}

    broken.write_text(json.dumps({"version": 99, "files": {"a": "b"}}),
                      encoding="utf-8")
    assert mod.load_state(str(broken)) == {}
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py -k "sha256 or state"`
Expected: FAIL — нет `file_sha256`/`save_state`/`load_state`.

- [ ] **Step 3: Добавить импорты, константы и функции**

В шапке файла заменить импорты:

```python
import sys
import os
import subprocess
import tempfile
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
```

Сразу после импортов добавить константы:

```python
STATE_VERSION = 1
STATE_HASH = "sha256"
```

После `get_changed_files()` (перед `run_optimized_load`) вставить:

```python
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
```

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py`
Expected: `7 passed`.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/load-config-optimized.py app/tests/env/test_load_config_optimized.py
git commit -m "feat(tools): манифест sha256 состояния загрузки конфигурации" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Фильтрация по состоянию (skip/revert/deleted)

**Files:**
- Modify: `template/.claude/tools/load-config-optimized.py` — `filter_loaded`, `collect_changes`, обёртка `get_changed_files`.
- Test: `app/tests/env/test_load_config_optimized.py`

**Interfaces:**
- Consumes: `file_sha256`, `get_project_root`, `get_dirty_paths`, `expand_to_load_paths`.
- Produces: `filter_loaded(candidates: List[str], state: Dict[str, str]) -> Tuple[List[str], Dict[str, str], List[str], List[str]]` — `(changed, snapshot, deleted, skipped)`. `snapshot` включает **все** существующие кандидаты (изменённые и нет).
- Produces: `collect_changes(state: Optional[Dict[str, str]] = None) -> Tuple[List[str], Optional[Dict[str, str]], List[str], List[str]]` — `(files, snapshot, deleted, skipped)`; при `state=None` снимок `None` и полный diff.
- Изменяет: `get_changed_files()` делегирует в `collect_changes(None)`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_load_config_optimized.py`:

```python
def _write_cf(root, rels):
    cf_dir = root / "src" / "cf"
    for rel in rels:
        path = cf_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<x/>", encoding="utf-8")


def _hashes(mod, root, rels):
    cf_dir = root / "src" / "cf"
    return {rel: mod.file_sha256(cf_dir / rel) for rel in rels}


def test_collect_changes_skips_unchanged_metadata_and_configuration(
        tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Configuration.xml",
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
    ]
    _write_cf(tmp_path, files)
    state = _hashes(mod, tmp_path, files)

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got, snapshot, deleted, skipped = mod.collect_changes(state)

    assert got == []
    assert deleted == []
    assert set(skipped) == set(files)
    assert snapshot == state


def test_collect_changes_loads_only_changed_module(tmp_path, monkeypatch):
    mod = _load()
    files = [
        "Configuration.xml",
        "Catalogs/Товары.xml",
        "Catalogs/Товары/Ext/ObjectModule.bsl",
        "Catalogs/Услуги.xml",
        "Catalogs/Услуги/Ext/ObjectModule.bsl",
    ]
    _write_cf(tmp_path, files)
    state = _hashes(mod, tmp_path, files)
    (tmp_path / "src" / "cf" / "Catalogs/Товары/Ext/ObjectModule.bsl"
     ).write_text("// изменено\n", encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.chdir(tmp_path)

    got, _snapshot, _deleted, _skipped = mod.collect_changes(state)

    assert "Configuration.xml" not in got
    assert "Catalogs/Товары/Ext/ObjectModule.bsl" in got
    assert "Catalogs/Товары.xml" in got          # корень изменённого объекта
    assert "Catalogs/Услуги.xml" not in got      # чужой объект не тронут


def test_collect_changes_detects_revert_to_head(tmp_path, monkeypatch):
    mod = _load()
    rel = "Catalogs/Товары.xml"
    _write_cf(tmp_path, [rel])

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))  # файл откатили к HEAD
    monkeypatch.chdir(tmp_path)

    got, _snapshot, _deleted, _skipped = mod.collect_changes({rel: "0" * 64})

    assert got == [rel]


def test_collect_changes_forgets_deleted_state_file(tmp_path, monkeypatch):
    mod = _load()
    missing = "Catalogs/Старый/Ext/OldModule.bsl"

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))
    monkeypatch.chdir(tmp_path)

    got, snapshot, deleted, skipped = mod.collect_changes({missing: "0" * 64})

    assert got == []
    assert deleted == [missing]
    assert missing not in snapshot
    assert skipped == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py -k collect_changes`
Expected: FAIL — нет `collect_changes`.

- [ ] **Step 3: Реализовать фильтрацию**

После `save_state` вставить:

```python
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
```

Заменить тело `get_changed_files()` на делегирование:

```python
def get_changed_files() -> List[str]:
    """Изменённые файлы конфигурации для -listFile (без учёта состояния)."""
    files, _, _, _ = collect_changes(None)
    return files
```

- [ ] **Step 4: Прогнать тесты**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py`
Expected: `11 passed`.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/load-config-optimized.py app/tests/env/test_load_config_optimized.py
git commit -m "feat(tools): дельта загрузки по манифесту sha256" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: CLI `--state` и запись состояния в `main`

**Files:**
- Modify: `template/.claude/tools/load-config-optimized.py` — `argparse`, `main`.
- Test: `app/tests/env/test_load_config_optimized.py`

**Interfaces:**
- Consumes: `load_state`, `save_state`, `collect_changes`, `run_optimized_load`.
- Produces: `parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace` с полем `state`.
- Produces: `main(argv: Optional[List[str]] = None) -> int`.
- Печатает в stdout: `⏭️  Пропущено как уже загруженное: N` + список; `⚠️  Удалён ранее загруженный файл (забыт в состоянии): PATH`.

- [ ] **Step 1: Написать падающие тесты**

Добавив в начало тестового файла `import json` уже сделано в Task 2. Добавить в конец:

```python
def test_main_saves_state_after_successful_load(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    calls = []

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load", lambda fs: calls.append(fs) or 0)
    monkeypatch.chdir(tmp_path)
    state_path = tmp_path / "logs" / "task#1" / "load-state.json"

    rc = mod.main(["--state", str(state_path)])

    assert rc == 0
    assert calls == [["Configuration.xml", "Catalogs/Товары.xml"]]
    assert mod.load_state(str(state_path)) == _hashes(mod, tmp_path, files)


def test_main_keeps_state_on_failed_load(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    state_path = tmp_path / "load-state.json"
    mod.save_state(str(state_path), {"Configuration.xml": "0" * 64})
    before = state_path.read_text(encoding="utf-8")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load", lambda fs: 1)
    monkeypatch.chdir(tmp_path)

    rc = mod.main(["--state", str(state_path)])

    assert rc == 1
    assert state_path.read_text(encoding="utf-8") == before


def test_main_updates_state_when_nothing_to_load(tmp_path, monkeypatch):
    mod = _load()
    state_path = tmp_path / "load-state.json"
    mod.save_state(str(state_path), {"Catalogs/Старый/Ext/Old.bsl": "0" * 64})

    def _must_not_load(files):
        raise AssertionError("загрузка не нужна")

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess", _fake_git([]))
    monkeypatch.setattr(mod, "run_optimized_load", _must_not_load)
    monkeypatch.chdir(tmp_path)

    rc = mod.main(["--state", str(state_path)])

    assert rc == 0
    assert mod.load_state(str(state_path)) == {}


def test_main_without_state_uses_full_diff(tmp_path, monkeypatch):
    mod = _load()
    files = ["Configuration.xml", "Catalogs/Товары.xml"]
    _write_cf(tmp_path, files)
    calls = []

    monkeypatch.setattr(mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(mod, "subprocess",
                        _fake_git([f"src/cf/{rel}" for rel in files]))
    monkeypatch.setattr(mod, "run_optimized_load", lambda fs: calls.append(fs) or 0)
    monkeypatch.chdir(tmp_path)

    rc = mod.main([])

    assert rc == 0
    assert calls == [["Configuration.xml", "Catalogs/Товары.xml"]]


def test_main_rejects_directory_as_state(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.chdir(tmp_path)

    assert mod.main(["--state", str(tmp_path)]) == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py -k "main_"`
Expected: FAIL — `main()` не принимает аргументов / нет `--state`.

- [ ] **Step 3: Добавить argparse и переписать `main`**

Добавить `import argparse` в блок импортов (первым):

```python
import argparse
import sys
import os
```

Перед `run_optimized_load` вставить:

```python
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Частичная загрузка изменённых файлов конфигурации 1С")
    parser.add_argument(
        "--state", metavar="PATH",
        help="манифест «что уже загружено» (обычно "
             "logs/task#<id>/load-state.json); без него грузится весь diff vs HEAD")
    return parser.parse_args(argv)
```

Заменить `main()` целиком:

```python
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
```

`sys.exit(main())` в `if __name__ == "__main__":` не меняется.

- [ ] **Step 4: Прогнать тесты файла**

Run: `python -m pytest -q app/tests/env/test_load_config_optimized.py`
Expected: `16 passed`.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/load-config-optimized.py app/tests/env/test_load_config_optimized.py
git commit -m "feat(tools): --state для инкрементальной загрузки конфигурации" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Документация (правило, навык, docstring)

**Files:**
- Modify: `template/.claude/rules/optimized-config-loading.md`
- Modify: `template/.claude/skills/task-orchestration/SKILL.md:110-115`
- Modify: `template/.claude/tools/load-config-optimized.py:1-18` — docstring.

**Interfaces:**
- Consumes: CLI `--state` из Task 4.

- [ ] **Step 1: Обновить правило**

В `template/.claude/rules/optimized-config-loading.md` после абзаца про состав списка (заканчивается словами «Если изменённых файлов нет — загрузка пропускается.») добавить раздел:

```markdown
## Инкрементальная загрузка (`--state`)

Оркестратор передаёт `--state logs/task#<id>/load-state.json` — манифест «что уже
успешно загружено» (`путь → sha256`). Из diff грузятся только файлы, изменившиеся
с момента последней успешной загрузки. Неизменные метаданные и `Configuration.xml`
не попадают в список — иначе каждая итерация задачи после добавления объекта
превращалась бы в полную перезагрузку (наличие `Configuration.xml` в `-listFile`
заставляет платформу грузить конфигурацию полностью).

- state пишется только при успехе — код возврата `0` или «грузить нечего»; при
  ошибке загрузки state не меняется, и повторный запуск возьмёт те же файлы;
- снимок хешей снимается до запуска загрузки: правки «во время загрузки» попадут
  в следующий запуск;
- файла состояния нет, JSON битый или версия чужая — грузится весь diff vs `HEAD`
  (в логе предупреждение);
- без `--state` — прежнее поведение (весь diff vs `HEAD`);
- удалённые части объектов (модули, `Ext/`) частичная загрузка не удаляет — как и
  раньше; ранее загруженные, но исчезнувшие файлы просто забываются из состояния.
```

В блоке «Запуск в фоне и лог процесса» заменить команду на:

```bash
# <id> — идентификатор задачи; каталог logs/task#<id> создать заранее
python .claude/tools/load-config-optimized.py --state logs/task#<id>/load-state.json > logs/task#<id>/load-config.log 2>&1
```

- [ ] **Step 2: Обновить вызов в навыке оркестрации**

В `template/.claude/skills/task-orchestration/SKILL.md` (шаг 3 раздела «Загрузка в базу после этапа `develop`») заменить команду на:

```bash
python .claude/tools/load-config-optimized.py --state logs/task#<id>/load-state.json > logs/task#<id>/load-config.log 2>&1
```

- [ ] **Step 3: Обновить docstring скрипта**

В шапке `template/.claude/tools/load-config-optimized.py` заменить блок «Использование» на:

```
Использование:
    python .claude/tools/load-config-optimized.py [--state PATH]

С --state грузятся только файлы, изменившиеся с последней успешной загрузки:
в PATH хранится манифест sha256 (обычно logs/task#<id>/load-state.json).
Без --state — весь git diff vs HEAD, как раньше.
```

- [ ] **Step 4: Проверить документацию и тесты**

Run: `grep -n -- "--state logs/task#<id>/load-state.json" template/.claude/rules/optimized-config-loading.md template/.claude/skills/task-orchestration/SKILL.md`
Expected: по одной строке в каждом файле.

Run: `python -m pytest -q app/tests/env/test_content_files.py`
Expected: PASS — frontmatter правил и навыков не сломан.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/rules/optimized-config-loading.md template/.claude/skills/task-orchestration/SKILL.md template/.claude/tools/load-config-optimized.py
git commit -m "docs(tools): --state в правиле и навыке оркестрации" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Финальная проверка

**Files:**
- Нет изменений кода; только проверки и, при необходимости, исправления.

- [ ] **Step 1: Полный прогон тестов**

Run: `python -m pytest -q`
Expected: PASS, без ошибок.

- [ ] **Step 2: Синтаксис и справка скрипта**

Run: `python -m py_compile template/.claude/tools/load-config-optimized.py`
Expected: код 0, без вывода.

Run: `python template/.claude/tools/load-config-optimized.py --help`
Expected: справка с `--state PATH`, код 0.

- [ ] **Step 3: Проверить сценарий вручную на временном git-репозитории**

`run_optimized_load` подменяется заглушкой, поэтому 1С не нужна:

```bash
(
tmp=$(mktemp -d)
mkdir -p "$tmp/src/cf/Catalogs/Товары/Ext" "$tmp/.claude/tools" "$tmp/logs/task#1"
cp template/.claude/tools/load-config-optimized.py "$tmp/.claude/tools/"
cd "$tmp"
git init -q && git config user.email t@t && git config user.name t
printf '<x/>' > src/cf/Configuration.xml
printf '<x/>' > src/cf/Catalogs/Товары.xml
printf '// v1\n' > src/cf/Catalogs/Товары/Ext/ObjectModule.bsl
git add . && git commit -qm init
printf '<x2/>' > src/cf/Configuration.xml          # как добавление объекта в состав
printf '<x/>' > src/cf/Catalogs/Услуги.xml          # новый untracked-объект
python - "$tmp" <<'PY'
import importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "lco", root / ".claude/tools/load-config-optimized.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
calls = []
mod.run_optimized_load = lambda files: calls.append(list(files)) or 0
state = root / "logs/task#1/load-state.json"

assert mod.main(["--state", str(state)]) == 0
first = calls[-1]
assert "Configuration.xml" in first and "Catalogs/Услуги.xml" in first

assert mod.main(["--state", str(state)]) == 0
assert len(calls) == 1, "повторный запуск не должен грузить неизменённые файлы"
print("SMOKE OK:", first)
PY
)
```

Expected: `SMOKE OK: [...]` — первый запуск грузит `Configuration.xml` и новый объект, второй не грузит ничего.

- [ ] **Step 4: Проверить состояние репозитория**

Run: `git status --short`
Expected: пусто (все изменения закоммичены локально в `main`).
