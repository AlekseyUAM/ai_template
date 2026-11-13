# Локальные ISO-даты в task.json — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Писать все отметки времени в `tasks/task#<id>/task.json` как ISO 8601 в локальном часовом поясе ОС пишущего процесса, оставив в БД epoch-числа и не сломав UI/арифметику.

**Architecture:** Новый модуль `agentmon.env.timefmt` даёт две операции: `to_local_iso` (epoch → локальная ISO-строка) и `parse_ts` (ISO/число → epoch). Писатели task.json (`task_api2`, `template/.claude/tools/task_status.py`) форматируют даты через него; единственный читатель, переносящий файл в БД (`task_sync`), разбирает обратно в числа. БД, API и UI не меняются.

**Tech Stack:** Python 3.10+ (в окружении 3.14), FastAPI, pytest, SQLite/PostgreSQL. Новых зависимостей нет.

**Spec:** `docs/superpowers/specs/2026-11-13-task-json-local-timestamps-design.md`

## Global Constraints

- Формат в файле: `YYYY-MM-DDTHH:MM:SS+HH:MM`, точность до секунд, `Z` не пишем.
- БД хранит epoch-секунды (float); в колонки `DOUBLE PRECISION`/`REAL` строки не попадают.
- Читатели принимают и ISO-строки, и старые epoch-числа.
- Невалидная дата разбирается как `None`, исключений наружу нет.
- Python >= 3.10, новых зависимостей не добавлять.
- Тесты запускать из каталога `app`: `../.venv/bin/python -m pytest ... -q`.
- Коммиты — локально в `main`, без push.
- В рабочем дереве есть незакоммиченное изменение `app/web/assets/ЮнитТесты.cfe` — **не добавлять его ни в один коммит**; `git add` только перечисленных в задаче файлов.
- Не менять `task_schema.py`, `tree_api.py`, `stack_api.py`, `app/web/start.js`, `benchmark/tasks/*`.

---

### Task 1: Модуль формата дат `timefmt`

**Files:**
- Create: `app/src/agentmon/env/timefmt.py`
- Test: `app/tests/env/test_timefmt.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `to_local_iso(ts: float | int | None) -> str | None`
  - `parse_ts(value) -> float | None`

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/env/test_timefmt.py`:

```python
"""Тесты формата дат task.json: локальная ISO-строка ↔ epoch-секунды."""
import re
from datetime import datetime, timedelta, timezone

from agentmon.env.timefmt import parse_ts, to_local_iso


def test_to_local_iso_none():
    assert to_local_iso(None) is None


def test_to_local_iso_has_offset_and_roundtrips():
    ts = 1794504190.2363446
    text = to_local_iso(ts)

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", text)

    expected_offset = datetime.fromtimestamp(ts).astimezone().utcoffset()
    parsed = datetime.fromisoformat(text)
    assert parsed.utcoffset() == expected_offset
    # Секундная точность: микросекунды отбрасываются.
    assert parse_ts(text) == \
        datetime.fromtimestamp(ts).replace(microsecond=0).timestamp()


def test_parse_ts_numbers():
    assert parse_ts(5) == 5.0
    assert parse_ts(5.5) == 5.5
    assert parse_ts("5.5") == 5.5


def test_parse_ts_iso_with_offsets_and_z():
    expected = datetime(2026, 11, 13, 11, 37, 18,
                        tzinfo=timezone(timedelta(hours=3))).timestamp()
    assert parse_ts("2026-11-13T11:37:18+03:00") == expected
    assert parse_ts("2026-11-13T08:37:18Z") == expected
    assert parse_ts("2026-11-13T08:37:18+00:00") == expected
    assert parse_ts("2026-11-13T08:37:18+0000") == expected


def test_parse_ts_garbage_is_none():
    assert parse_ts("не дата") is None
    assert parse_ts("") is None
    assert parse_ts("   ") is None
    assert parse_ts(None) is None
    assert parse_ts(True) is None
    assert parse_ts({}) is None
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_timefmt.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agentmon.env.timefmt'`.

- [ ] **Step 3: Реализовать модуль**

Создать `app/src/agentmon/env/timefmt.py`:

```python
"""Формат отметок времени в task.json: локальный ISO 8601 и разбор обратно.

task.json — человекочитаемый файл: даты пишутся строками вида
``2026-11-13T11:37:18+03:00`` (часовой пояс ОС пишущего процесса). БД и UI
продолжают работать с epoch-секундами, поэтому на границе файл→БД значения
разбираются обратно в число. Старые файлы с epoch-числами поддерживаются.
"""
from datetime import datetime


def to_local_iso(ts) -> str | None:
    """epoch-секунды → ISO 8601 в локальном поясе ОС. None → None."""
    if ts is None:
        return None
    return (datetime.fromtimestamp(float(ts))
            .astimezone()
            .isoformat(timespec="seconds"))


def parse_ts(value) -> float | None:
    """ISO-строка/число/числовая строка → epoch-секунды; мусор → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(
                text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return None
    return None
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_timefmt.py -q
```
Expected: `5 passed`.

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/timefmt.py app/tests/env/test_timefmt.py
git commit -m "feat(env): формат локальных ISO-дат для task.json"
```

---

### Task 2: `task_status.py` пишет ISO и нормализует старые epoch-даты

**Files:**
- Modify: `template/.claude/tools/task_status.py` (строки 8-19 — импорты/константы; 57-69 — запись; 150-165 — `set_db_update`; 193-221 — `_apply_update`)
- Test: `app/tests/env/test_task_status_cli.py`

**Interfaces:**
- Consumes: ничего из Task 1 (скрипт standalone, деплоится в проекты без agentmon).
- Produces: в task.json все даты — строки ISO с локальным смещением; числовые даты при записи нормализуются.

- [ ] **Step 1: Обновить тесты под ISO и добавить тест нормализации**

В `app/tests/env/test_task_status_cli.py`:

1. Добавить импорт `datetime` после `import json`:

```python
from datetime import datetime
```

2. Добавить helper после `_load()`:

```python
def _iso_dt(value: str) -> datetime:
    """Разбор ISO-даты из task.json для сравнений в тестах."""
    return datetime.fromisoformat(value)
```

3. Заменить тело `test_cli_sets_started_and_finished_at` (строки 77-90) на:

```python
def test_cli_sets_started_and_finished_at(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    running = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(running["started_at"], str)
    assert _iso_dt(running["started_at"]).tzinfo is not None
    assert running.get("finished_at") is None

    mod.main([str(d), "develop", "done"])
    done = json.loads((d / "task.json").read_text(encoding="utf-8"))
    # started_at не перезаписывается, finished_at проставляется и не раньше старта
    assert done["started_at"] == running["started_at"]
    assert isinstance(done["finished_at"], str)
    assert _iso_dt(done["finished_at"]) >= _iso_dt(done["started_at"])
```

4. Заменить тело `test_cli_stamps_stage_timing` (строки 125-138) на:

```python
def test_cli_stamps_stage_timing(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(dev["started_at"], str)
    assert dev["finished_at"] is None
    assert dev["iteration"] == 1
    mod.main([str(d), "develop", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(dev["finished_at"], str)
    assert _iso_dt(dev["finished_at"]) >= _iso_dt(dev["started_at"])
```

5. Заменить тело `test_cli_db_update_start_and_done` (строки 153-163) на:

```python
def test_cli_db_update_start_and_done(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "db-update", "start"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(data["db_update"]["started_at"], str)
    assert data["db_update"]["finished_at"] is None
    mod.main([str(d), "db-update", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(data["db_update"]["finished_at"], str)
    assert _iso_dt(data["db_update"]["finished_at"]) >= \
        _iso_dt(data["db_update"]["started_at"])
```

6. Добавить в конец файла тест нормализации старых чисел:

```python
def test_cli_normalizes_old_epoch_dates_to_iso(tmp_path):
    """Числовые даты старого файла при записи конвертируются в ISO."""
    mod = _load()
    d = _one_stage_task(tmp_path)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    data["created_at"] = 1000.0
    data["started_at"] = 800.0
    data["db_update"] = {"started_at": 700.0, "finished_at": None}
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    dev["started_at"] = 900.0
    (d / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    mod.main([str(d), "develop", "running"])

    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(data["created_at"], str)
    assert _iso_dt(data["created_at"]).timestamp() == 1000.0
    assert isinstance(data["started_at"], str)
    assert _iso_dt(data["started_at"]).timestamp() == 800.0
    assert isinstance(data["db_update"]["started_at"], str)
    assert _iso_dt(data["db_update"]["started_at"]).timestamp() == 700.0
    # Этап уже был в running — started_at перезаписан текущим запуском (ISO).
    assert isinstance(dev["started_at"], str)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_status_cli.py -q
```
Expected: FAIL на `assert isinstance(running["started_at"], str)` (сейчас float), плюс падение теста нормализации.

- [ ] **Step 3: Реализовать ISO и нормализацию в `task_status.py`**

В `template/.claude/tools/task_status.py`:

1. Добавить импорт после `import contextlib`:

```python
from datetime import datetime
```

2. Добавить helpers после `TRUTHY = ...` (строка 71):

```python
def _now_iso() -> str:
    """Текущее время в ISO 8601 с локальным смещением ОС."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_times(data: dict) -> None:
    """Числовые даты в task.json → ISO-строки (старые файлы, без миграции)."""
    def _convert(container: dict) -> None:
        for key in ("created_at", "started_at", "finished_at"):
            value = container.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                container[key] = (
                    datetime.fromtimestamp(value)
                    .astimezone()
                    .isoformat(timespec="seconds"))

    _convert(data)
    for stage in data.get("stages", []):
        if isinstance(stage, dict):
            _convert(stage)
    db_update = data.get("db_update")
    if isinstance(db_update, dict):
        _convert(db_update)
```

3. В `set_db_update` (строка 157) заменить:

```python
        now = time.time()
```
на:
```python
        now = _now_iso()
```

и перед `_atomic_write_json(path, data)` (строка 165) добавить:

```python
        _normalize_times(data)
```

4. В `_apply_update` заменить `now_stage = time.time()` (строка 194) на `now_stage = _now_iso()` и `now = time.time()` (строка 214) на `now = _now_iso()`.

5. В `update()` перед `_atomic_write_json(path, data)` (строка 230) добавить:

```python
        _normalize_times(data)
```

6. Заменить устаревший комментарий над `now = _now_iso()` (строки 209-213) на:

```python
            # Отметки времени — ISO 8601 в локальном поясе ОС. В БД их
            # переводит обратно в epoch task_sync; фолбэк для неотмеченных
            # этапов остаётся числовым. started_at ставится при первом
            # переходе задачи в running, finished_at — при терминальном
            # статусе; при возврате в нетерминальный статус снимаем
            # устаревший finished_at.
```

Важно: `time.time()` в `_locked` (проверка `STALE_LOCK_SECONDS`) не трогать — это не данные task.json.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_status_cli.py -q
```
Expected: все тесты PASS.

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add template/.claude/tools/task_status.py app/tests/env/test_task_status_cli.py
git commit -m "feat(tools): ISO-даты в task.json вместо epoch"
```

---

### Task 3: `task_sync` разбирает ISO в epoch для БД

**Files:**
- Modify: `app/src/agentmon/env/task_sync.py` (импорты; `_apply_stage_timings` строки 27-51; `sync_task_from_file` строки 72-92)
- Test: `app/tests/env/test_task_sync.py`

**Interfaces:**
- Consumes: `parse_ts` из Task 1.
- Produces: `sync_task_from_file` кладёт в БД только числа или `None` — для task-level дат, дат этапов и `db_update`.

- [ ] **Step 1: Добавить падающие тесты**

В `app/tests/env/test_task_sync.py`:

1. Добавить импорт после `from pathlib import Path`:

```python
from datetime import datetime, timedelta, timezone
```

2. Добавить тесты в конец файла:

```python
# ─── ISO-даты task.json → epoch в БД ─────────────────────────────────────────

_MSK = timezone(timedelta(hours=3))


def _epoch_11_msk():
    return datetime(2026, 11, 13, 11, 0, tzinfo=_MSK).timestamp()


def _epoch_0830_utc():
    return datetime(2026, 11, 13, 8, 30, tzinfo=timezone.utc).timestamp()


def test_sync_converts_iso_stage_timings(tmp_path):
    """ISO-даты этапов из файла → epoch-числа в БД."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = "2026-11-13T11:00:00+03:00"
            s["finished_at"] = "2026-11-13T08:30:00Z"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == _epoch_11_msk()
    assert analyze["finished_at"] == _epoch_0830_utc()


def test_sync_mixed_epoch_and_iso_timings(tmp_path):
    """Старое число и новая ISO-строка в одном файле — оба в БД числами."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = 5.0
            s["finished_at"] = "2026-11-13T08:30:00Z"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 5.0
    assert analyze["finished_at"] == _epoch_0830_utc()


def test_sync_converts_task_level_iso_timings(tmp_path):
    """Task-level started_at/finished_at из файла → числа в колонках БД."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "started_at": "2026-11-13T11:00:00+03:00",
        "finished_at": None,
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    assert tr.get(tid)["started_at"] == _epoch_11_msk()
    assert tr.get(tid)["finished_at"] is None


def test_sync_converts_db_update_iso_timings(tmp_path):
    """db_update: ISO внутри словаря → числа в JSON-строке БД, прочее сохраняется."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "db_update": {
            "started_at": "2026-11-13T11:00:00+03:00",
            "finished_at": "2026-11-13T08:30:00Z",
            "note": "keep",
        },
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    db_update = json.loads(tr.get(tid)["db_update_json"])
    assert db_update["started_at"] == _epoch_11_msk()
    assert db_update["finished_at"] == _epoch_0830_utc()
    assert db_update["note"] == "keep"


def test_sync_invalid_iso_falls_back_to_now(tmp_path):
    """Мусор вместо даты не роняет синк: этап done получает фолбэк now."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = "не дата"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 1000.0
    assert analyze["finished_at"] == 1000.0


def test_sync_invalid_task_level_iso_becomes_none(tmp_path):
    """Невалидная task-level дата — как отсутствующая (None), без исключения."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "started_at": "не дата",
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    assert tr.get(tid)["started_at"] is None
```

- [ ] **Step 2: Убедиться, что новые тесты падают**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_sync.py -q
```
Expected: новые тесты FAIL (в БД/`stages_json` остаются строки или сравнение с epoch не проходит); старые 6 тестов PASS.

- [ ] **Step 3: Реализовать разбор в `task_sync.py`**

1. Добавить импорт после `from agentmon.env.task_model import overall_status`:

```python
from agentmon.env.timefmt import parse_ts
```

2. Заменить цикл `_apply_stage_timings` (строки 38-50) на версию, которая
нормализует и даты файла, и даты из БД (последние могли попасть туда строками
раньше — в БД они тоже не должны просачиваться):

```python
    for s in file_stages:
        prev = prev_by_name.get(s.get("name"), {})
        # В файле даты — ISO-строки; в БД и для сравнений — epoch-числа.
        s["started_at"] = parse_ts(s.get("started_at"))
        s["finished_at"] = parse_ts(s.get("finished_at"))
        prev_started = parse_ts(prev.get("started_at"))
        prev_finished = parse_ts(prev.get("finished_at"))
        status = s.get("status")
        if s.get("started_at") is None:
            if prev_started is not None:
                s["started_at"] = prev_started
            elif status in ("running", "done", "failed"):
                s["started_at"] = now
        if status in ("done", "failed") and s.get("finished_at") is None:
            if prev_finished is not None:
                s["finished_at"] = prev_finished
            else:
                s["finished_at"] = now
    return file_stages
```

3. В `sync_task_from_file` заменить блок:

```python
    fields = {}
    for key in ("stage", "started_at", "finished_at"):
        if key in data:
            fields[key] = data.get(key)
```
на:

```python
    fields = {}
    if "stage" in data:
        fields["stage"] = data.get("stage")
    for key in ("started_at", "finished_at"):
        if key in data:
            fields[key] = parse_ts(data.get(key))
```

4. Заменить блок:

```python
    if "db_update" in data:
        fields["db_update_json"] = json.dumps(data["db_update"], ensure_ascii=False)
```
на:

```python
    if "db_update" in data:
        db_update = data["db_update"]
        if isinstance(db_update, dict):
            db_update = dict(db_update)
            for key in ("started_at", "finished_at"):
                if key in db_update:
                    db_update[key] = parse_ts(db_update.get(key))
        fields["db_update_json"] = json.dumps(db_update, ensure_ascii=False)
```

- [ ] **Step 4: Убедиться, что все тесты `task_sync` проходят**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_sync.py -q
```
Expected: все тесты PASS (включая старые 6).

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/task_sync.py app/tests/env/test_task_sync.py
git commit -m "feat(env): task_sync конвертирует ISO-даты task.json в epoch для БД"
```

---

### Task 4: `created_at` при создании задачи + ISO-дамп task.json

**Files:**
- Modify: `app/src/agentmon/env/task_api2.py` (импорты; вызов `task_repo.add` строки 100-115; запись task.json строки 144-161)
- Test: `app/tests/env/test_task_api2.py`

**Interfaces:**
- Consumes: `to_local_iso` из Task 1.
- Produces: свежий task.json содержит `created_at` (и прочие непустые даты) локальным ISO; в БД `tasks.created_at` — число (epoch).

- [ ] **Step 1: Написать падающий тест**

В `app/tests/env/test_task_api2.py` добавить в конец файла:

```python
def test_create_task_writes_iso_created_at(tmp_path):
    """created_at в task.json — локальный ISO, в БД — epoch-число."""
    from datetime import datetime

    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача с датой",
        "identifier": "C-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert isinstance(task["created_at"], (int, float))

    task_json_data = json.loads(
        (project_path / "tasks" / "task#C-1" / "task.json").read_text())
    created = task_json_data["created_at"]
    assert isinstance(created, str)
    parsed = datetime.fromisoformat(created)
    assert parsed.tzinfo is not None
    # Точность до секунд: с БД-временем расходится меньше чем на секунду.
    assert abs(parsed.timestamp() - float(task["created_at"])) < 1.0
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_api2.py::test_create_task_writes_iso_created_at -q
```
Expected: FAIL — `task["created_at"]` равен `None`.

- [ ] **Step 3: Реализовать запись**

В `app/src/agentmon/env/task_api2.py`:

1. Добавить импорты после `import json`:

```python
import time
```
и после `from .task_model import build_stages, overall_status, validate_task`:

```python
from .timefmt import to_local_iso
```

2. В вызов `task_repo.add(...)` добавить `now=time.time(),` (рядом с `status="planned", stage=None,`):

```python
            status="planned",
            stage=None,
            now=time.time(),
```

3. После строки `task_data["stages"] = stages` и перед записью файла добавить:

```python
        # task.json — человекочитаемые даты: ISO в локальном поясе ОС.
        for key in ("created_at", "started_at", "finished_at"):
            if key in task_data:
                task_data[key] = to_local_iso(task_data.get(key))
        for stage in task_data["stages"]:
            for key in ("started_at", "finished_at"):
                if key in stage:
                    stage[key] = to_local_iso(stage.get(key))
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest tests/env/test_task_api2.py -q
```
Expected: все тесты `test_task_api2.py` PASS.

- [ ] **Step 5: Полный прогон тестов**

Run:
```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python -m pytest -q
```
Expected: PASS всего набора. Если падает что-то не связанное с этой задачей — зафиксировать в ответе, не «чинить» молча.

- [ ] **Step 6: Смоук формата (CLI на старом файле)**

Проверяет, что деплоируемый `task_status.py` пишет ISO и заодно нормализует
старую epoch-дату, созданную legacy-путём `task_schema`:

```bash
cd /home/uam/projects/ai_template/app && ../.venv/bin/python - <<'PY'
import json, subprocess, sys, tempfile
from pathlib import Path
from agentmon.env import task_schema as ts

root = Path(tempfile.mkdtemp())
spec = ts.create_task(root, title="smoke", goal="", plan="", constraints="",
                      enabled_stages=["develop"], now=1794504190.0)
d = ts.task_dir(root, spec.id)
cli = Path("..") / "template" / ".claude" / "tools" / "task_status.py"
subprocess.run([sys.executable, str(cli), str(d), "develop", "running"],
               check=True)
data = json.loads((d / "task.json").read_text(encoding="utf-8"))
print("created_at:", data["created_at"])
print("stage started_at:", next(s for s in data["stages"]
                                if s["name"] == "develop")["started_at"])
PY
```
Expected: обе строки — ISO с локальным смещением (например,
`2026-11-13T11:37:18+03:00`); `created_at` не `null` и не число. Скрипт ничего
не коммитит.

- [ ] **Step 7: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/task_api2.py app/tests/env/test_task_api2.py
git commit -m "feat(env): ISO-даты в task.json при создании задачи + created_at"
```

---

## Раскатка после реализации (вручную, не входит в коммиты)

1. Перезапустить монитор (`python -m agentmon` перезапуск процесса), чтобы подхватить новый Python-код.
2. Для каждого проекта выполнить `POST /api/env/projects/{pid}/update-env` (кнопка обновления окружения в UI), чтобы доставить новый `template/.claude/tools/task_status.py`.
3. Проверить на новом task.json: `created_at` — строка `...+03:00`, у выполненного этапа — ISO-даты; в UI время/длительности отображаются как раньше.

## Самопроверка плана

- Покрытие спеки: формат/поля (Task 1, 2, 4), `created_at` при создании (Task 4), ISO→epoch на границе (Task 3), нормализация старых файлов (Task 2), тесты (все задачи), UI/БД без изменений (Global Constraints), раскатка (раздел выше).
- Заглушек/TODO нет; во всех шагах код и команды целиком.
- Сигнатуры согласованы: `timefmt.to_local_iso`, `timefmt.parse_ts`, `_now_iso`, `_normalize_times`; имена файлов и тестов совпадают между задачами.
