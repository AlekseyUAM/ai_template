# Telegram-интеграция AgentMon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Управление и наблюдение за агентскими сессиями AgentMon из Telegram: уведомления о статусах задач/стеков, управление стеком (запуск/продолжение/остановка), просмотр отчётов этапов и текстовые замечания агенту.

**Architecture:** Новый опциональный пакет `app/src/agentmon/telegram/`. Long-polling в фоновой asyncio-задаче рядом с `dispatch_loop`. Уведомления — поллер-диффер, сравнивающий статусы с таблицей `tg_notify_state`. Мутации (стоп стека, approve) хендлеры делают через локальный REST приложения (`http://127.0.0.1:{PORT}`) своим httpx-клиентом — без дублирования логики роутов. Чтение артефактов — с диска, замечания — в таблицу `task_feedback` + файл `USER_FEEDBACK.md`.

**Tech Stack:** Python 3.10+, FastAPI, httpx (тонкий клиент Bot API), sqlite/postgres через адаптер `Db`, pytest.

## Global Constraints

- Фича полностью опциональна: нет `AGENTMON_TG_TOKEN` → ни бот, ни нотификатор не стартуют, нулевое влияние на остальное.
- SQL переносимый (sqlite + postgres), плейсхолдеры только `?`, операции через адаптер `Db` (`execute`/`query`/`one`/`returning_id`/`transaction`/`autopk`).
- Авторизация: `chat_id` апдейта сверяется со списком `AGENTMON_TG_CHAT_IDS`; чужой чат игнорируется; мутации — только авторизованным.
- Тесты без реальной сети: HTTP через `httpx.MockTransport`; БД — sqlite in-memory из существующих фикстур.
- Лимит сообщения Telegram — 4096 символов; длинный текст режется на части.
- Коммиты частые, по одному на задачу; ветка `main` локально (без PR).
- Статусы задачи: `planned/queued/running/stopped/awaiting_user/done/failed`. Статус гейта — `awaiting_user` (считает `overall_status`). Стек: `idle/running`.

---

### Task 1: Runtime-зависимость httpx + конфиг Telegram

**Files:**
- Modify: `app/pyproject.toml:10-16` (dependencies), `app/pyproject.toml:18-23` (dev)
- Modify: `app/src/agentmon/config.py`
- Test: `app/tests/test_config_telegram.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `config.TG_TOKEN: str | None` — токен бота (`AGENTMON_TG_TOKEN`), пустой/отсутствует → `None`.
  - `config.TG_CHAT_IDS: list[str]` — разрешённые chat_id из `AGENTMON_TG_CHAT_IDS` (через запятую, обрезка пробелов, пустые отброшены).
  - `config.TG_API_BASE: str` — `https://api.telegram.org`.
  - `config.local_base_url() -> str` — `f"http://127.0.0.1:{PORT}"` (для REST-вызовов изнутри процесса).

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/test_config_telegram.py`:

```python
import importlib
import agentmon.config as config


def _reload(monkeypatch, **env):
    for k in ("AGENTMON_TG_TOKEN", "AGENTMON_TG_CHAT_IDS", "AGENTMON_PORT"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(config)


def test_token_none_when_unset(monkeypatch):
    cfg = _reload(monkeypatch)
    assert cfg.TG_TOKEN is None
    assert cfg.TG_CHAT_IDS == []


def test_chat_ids_parsed(monkeypatch):
    cfg = _reload(monkeypatch, AGENTMON_TG_TOKEN="t", AGENTMON_TG_CHAT_IDS=" 111, 222 ,,333 ")
    assert cfg.TG_TOKEN == "t"
    assert cfg.TG_CHAT_IDS == ["111", "222", "333"]


def test_local_base_url(monkeypatch):
    cfg = _reload(monkeypatch, AGENTMON_PORT="9000")
    assert cfg.local_base_url() == "http://127.0.0.1:9000"


def teardown_module(module):
    importlib.reload(config)
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/test_config_telegram.py -q`
Expected: FAIL (`AttributeError: module 'agentmon.config' has no attribute 'TG_TOKEN'`)

- [ ] **Step 3: Реализация конфига**

В конец `app/src/agentmon/config.py` добавить:

```python
# --- Telegram-интеграция (опционально) ---
# Нет токена → фича выключена: ни бот, ни нотификатор не стартуют.
TG_TOKEN = os.environ.get("AGENTMON_TG_TOKEN") or None

# Разрешённые chat_id (через запятую). Чужие чаты игнорируются.
TG_CHAT_IDS = [
    part.strip()
    for part in os.environ.get("AGENTMON_TG_CHAT_IDS", "").split(",")
    if part.strip()
]

# База Bot API и локальный REST приложения (вызовы изнутри процесса).
TG_API_BASE = os.environ.get("AGENTMON_TG_API_BASE", "https://api.telegram.org")


def local_base_url() -> str:
    return f"http://127.0.0.1:{PORT}"
```

- [ ] **Step 4: Перенести httpx в runtime-зависимости**

В `app/pyproject.toml` в список `dependencies` (строки 10–16) добавить `"httpx",`. Из `dev` (строки 18–23) строку `"httpx",` убрать (останется в runtime; dev наследует).

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/test_config_telegram.py -q`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add app/pyproject.toml app/src/agentmon/config.py app/tests/test_config_telegram.py
git commit -m "Telegram: конфиг (токен, allowlist chat_id) и httpx в runtime"
```

---

### Task 2: Схема БД и репозитории нотификаций/замечаний

**Files:**
- Modify: `app/src/agentmon/store/schema.py` (новые таблицы + индексы)
- Create: `app/src/agentmon/store/telegram_store.py`
- Test: `app/tests/test_telegram_store.py`

**Interfaces:**
- Consumes: `Db` (`execute`/`one`/`returning_id`/`query`/`autopk`).
- Produces:
  - Таблицы `tg_notify_state(id, scope, ref_id, last_status, UNIQUE(scope,ref_id))`, `task_feedback(id, task_id, chat_id, text, created_at, consumed)`.
  - `NotifyStateRepo(db)`: `get(scope: str, ref_id: int) -> str | None`; `set(scope: str, ref_id: int, status: str) -> None` (upsert).
  - `FeedbackRepo(db)`: `add(task_id: int, chat_id: str, text: str, now=None) -> int`; `list_for_task(task_id: int) -> list[dict]`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/test_telegram_store.py`:

```python
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.telegram_store import NotifyStateRepo, FeedbackRepo


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


def test_notify_state_upsert():
    repo = NotifyStateRepo(_db())
    assert repo.get("task", 1) is None
    repo.set("task", 1, "running")
    assert repo.get("task", 1) == "running"
    repo.set("task", 1, "done")              # второй set — update, не дубль
    assert repo.get("task", 1) == "done"


def test_feedback_add_and_list():
    repo = FeedbackRepo(_db())
    fid = repo.add(task_id=5, chat_id="111", text="почини X", now=1.0)
    assert isinstance(fid, int)
    rows = repo.list_for_task(5)
    assert len(rows) == 1
    assert rows[0]["text"] == "почини X"
    assert rows[0]["chat_id"] == "111"
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/test_telegram_store.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.store.telegram_store`)

- [ ] **Step 3: Добавить таблицы в схему**

В `app/src/agentmon/store/schema.py` внутри `init_schema`, после создания таблицы `runs` (перед блоком миграций `_ensure_columns`), добавить:

```python
    db.execute(f"""CREATE TABLE IF NOT EXISTS tg_notify_state (
        id {pk}, scope TEXT NOT NULL, ref_id INTEGER NOT NULL,
        last_status TEXT, UNIQUE(scope, ref_id))""")
    db.execute(f"""CREATE TABLE IF NOT EXISTS task_feedback (
        id {pk}, task_id INTEGER NOT NULL, chat_id TEXT NOT NULL,
        text TEXT NOT NULL, created_at {ts}, consumed INTEGER NOT NULL DEFAULT 0)""")
```

В `_ensure_indexes` в список `indexes` добавить:

```python
        ("idx_task_feedback_task_id", "task_feedback(task_id)"),
```

- [ ] **Step 4: Реализовать репозитории**

Создать `app/src/agentmon/store/telegram_store.py`:

```python
"""Репозитории Telegram-интеграции: состояние уведомлений и замечания."""


class NotifyStateRepo:
    """Последнее уведомлённое состояние задач/стеков (scope+ref_id)."""

    def __init__(self, db):
        self._db = db

    def get(self, scope: str, ref_id: int) -> str | None:
        row = self._db.one(
            "SELECT last_status FROM tg_notify_state WHERE scope=? AND ref_id=?",
            [scope, ref_id],
        )
        return row["last_status"] if row else None

    def set(self, scope: str, ref_id: int, status: str) -> None:
        # upsert без диалект-специфики: UPDATE, затем INSERT при отсутствии строки.
        changed = self._db.execute_rowcount(
            "UPDATE tg_notify_state SET last_status=? WHERE scope=? AND ref_id=?",
            [status, scope, ref_id],
        )
        if not changed:
            self._db.returning_id(
                "tg_notify_state", ["scope", "ref_id", "last_status"],
                [scope, ref_id, status],
            )


class FeedbackRepo:
    """Пользовательские замечания к задаче."""

    def __init__(self, db):
        self._db = db

    def add(self, task_id: int, chat_id: str, text: str, now=None) -> int:
        return self._db.returning_id(
            "task_feedback", ["task_id", "chat_id", "text", "created_at"],
            [task_id, chat_id, text, now],
        )

    def list_for_task(self, task_id: int) -> list[dict]:
        return self._db.query(
            "SELECT * FROM task_feedback WHERE task_id=? ORDER BY id", [task_id],
        )
```

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/test_telegram_store.py -q`
Expected: PASS

- [ ] **Step 6: Прогнать существующие тесты схемы — не сломали ли миграции**

Run: `cd app && python -m pytest tests/env/test_store_hardening.py -q`
Expected: PASS

- [ ] **Step 7: Коммит**

```bash
git add app/src/agentmon/store/schema.py app/src/agentmon/store/telegram_store.py app/tests/test_telegram_store.py
git commit -m "Telegram: таблицы tg_notify_state/task_feedback и репозитории"
```

---

### Task 3: Тонкий клиент Bot API

**Files:**
- Create: `app/src/agentmon/telegram/__init__.py` (пустой)
- Create: `app/src/agentmon/telegram/client.py`
- Test: `app/tests/telegram/__init__.py` (пустой), `app/tests/telegram/test_client.py`

**Interfaces:**
- Consumes: `httpx`.
- Produces:
  - `inline_keyboard(rows) -> dict` — где `rows: list[list[tuple[str, str]]]` = строки кнопок `(text, callback_data)`; возвращает `{"inline_keyboard": [[{"text":..,"callback_data":..}, ...], ...]}`.
  - `class BotClient`:
    - `__init__(self, token: str, api_base: str, transport=None)` — если `transport` задан, используется в `httpx.AsyncClient` (тесты).
    - `async get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]` — возвращает массив `result` из ответа Bot API.
    - `async send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict`.
    - `async answer_callback(self, callback_query_id: str, text: str | None = None) -> dict`.
    - `async aclose(self) -> None`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/__init__.py` (пусто) и `app/tests/telegram/test_client.py`:

```python
import json
import httpx
import pytest
from agentmon.telegram.client import BotClient, inline_keyboard


def _transport(capture):
    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(request)
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})
    return httpx.MockTransport(handler)


def test_inline_keyboard_shape():
    kb = inline_keyboard([[("OK", "ok:1"), ("Нет", "no:1")]])
    assert kb == {"inline_keyboard": [[
        {"text": "OK", "callback_data": "ok:1"},
        {"text": "Нет", "callback_data": "no:1"},
    ]]}


@pytest.mark.asyncio
async def test_get_updates_calls_api_with_offset():
    cap = []
    client = BotClient("TOK", "https://api.telegram.org", transport=_transport(cap))
    res = await client.get_updates(offset=100, timeout=0)
    await client.aclose()
    assert res == [{"update_id": 7}]
    req = cap[0]
    assert "/botTOK/getUpdates" in str(req.url)
    body = json.loads(req.content)
    assert body["offset"] == 100


@pytest.mark.asyncio
async def test_send_message_includes_markup():
    cap = []
    client = BotClient("TOK", "https://api.telegram.org", transport=_transport(cap))
    await client.send_message("111", "привет", reply_markup=inline_keyboard([[("A", "a")]]))
    await client.aclose()
    body = json.loads(cap[0].content)
    assert body["chat_id"] == "111"
    assert body["text"] == "привет"
    assert body["reply_markup"]["inline_keyboard"][0][0]["text"] == "A"
```

Примечание: для async-тестов нужен `pytest-asyncio`. Добавить его в `dev`-зависимости (`app/pyproject.toml`) строкой `"pytest-asyncio",` и в `app/pytest.ini` в секцию `[pytest]` строку `asyncio_mode = auto`.

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && pip install -e ".[dev]" -q && python -m pytest tests/telegram/test_client.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.client`)

- [ ] **Step 3: Реализовать клиент**

Создать `app/src/agentmon/telegram/__init__.py` (пустой) и `app/src/agentmon/telegram/client.py`:

```python
"""Тонкий async-клиент Telegram Bot API поверх httpx."""
import httpx


def inline_keyboard(rows):
    """rows: list[list[(text, callback_data)]] → разметка inline-клавиатуры."""
    return {"inline_keyboard": [
        [{"text": t, "callback_data": cb} for (t, cb) in row] for row in rows
    ]}


class BotClient:
    def __init__(self, token: str, api_base: str, transport=None):
        self._base = f"{api_base}/bot{token}"
        kwargs = {"timeout": httpx.Timeout(60.0)}
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**kwargs)

    async def _call(self, method: str, payload: dict) -> dict:
        resp = await self._http.post(f"{self._base}/{method}", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def get_updates(self, offset=None, timeout: int = 25) -> list[dict]:
        payload = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        data = await self._call("getUpdates", payload)
        return data.get("result", [])

    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._call("sendMessage", payload)

    async def answer_callback(self, callback_query_id: str, text=None) -> dict:
        payload = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text
        return await self._call("answerCallbackQuery", payload)

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_client.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/pyproject.toml app/pytest.ini app/src/agentmon/telegram/ app/tests/telegram/
git commit -m "Telegram: тонкий клиент Bot API (httpx) + inline-клавиатуры"
```

---

### Task 4: Чтение отчётов этапов

**Files:**
- Create: `app/src/agentmon/telegram/reports.py`
- Test: `app/tests/telegram/test_reports.py`

**Interfaces:**
- Consumes: `agentmon.env.task_schema.task_folder_name`, `agentmon.env.task_model.DEFAULT_STAGES`.
- Produces:
  - `TG_LIMIT = 4096`.
  - `chunk(text: str, limit: int = TG_LIMIT) -> list[str]` — режет текст на части ≤ limit по границам строк, где возможно.
  - `enabled_stages(task: dict) -> list[dict]` — список `{"name","artifact"}` включённых этапов из `stages_json`.
  - `read_report(project_path: str, task: dict, stage_name: str) -> str | None` — содержимое артефакта этапа или None, если файла нет.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_reports.py`:

```python
import json
from agentmon.telegram.reports import chunk, enabled_stages, read_report, TG_LIMIT


def test_chunk_splits_on_limit():
    parts = chunk("a\n" * 5000, limit=100)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts).replace("\n", "") == "a" * 5000


def test_chunk_short_text_single():
    assert chunk("короткий") == ["короткий"]


def test_enabled_stages_filters():
    task = {"stages_json": json.dumps([
        {"name": "analyze", "artifact": "ANALYZE.md", "enabled": True},
        {"name": "plan", "artifact": "ARCHITECT.md", "enabled": False},
    ])}
    names = [s["name"] for s in enabled_stages(task)]
    assert names == ["analyze"]


def test_read_report(tmp_path):
    folder = tmp_path / "tasks" / "task#001"
    folder.mkdir(parents=True)
    (folder / "ANALYZE.md").write_text("# Анализ\nтекст", encoding="utf-8")
    task = {"id": 1, "identifier": "001", "stages_json": json.dumps([
        {"name": "analyze", "artifact": "ANALYZE.md", "enabled": True}])}
    assert "Анализ" in read_report(str(tmp_path), task, "analyze")
    assert read_report(str(tmp_path), task, "review") is None  # нет артефакта
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_reports.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.reports`)

- [ ] **Step 3: Реализовать reports.py**

Создать `app/src/agentmon/telegram/reports.py`:

```python
"""Чтение артефактов этапов задачи для показа в Telegram."""
import json
from pathlib import Path

from agentmon.env.task_schema import task_folder_name

TG_LIMIT = 4096


def chunk(text: str, limit: int = TG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, buf = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:            # очень длинная строка — режем жёстко
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) > limit:
            parts.append(buf)
            buf = line
        else:
            buf += line
    if buf:
        parts.append(buf)
    return parts


def _stages(task: dict) -> list[dict]:
    try:
        return json.loads(task.get("stages_json") or "[]")
    except (ValueError, TypeError):
        return []


def enabled_stages(task: dict) -> list[dict]:
    return [{"name": s["name"], "artifact": s.get("artifact")}
            for s in _stages(task) if s.get("enabled")]


def read_report(project_path: str, task: dict, stage_name: str) -> str | None:
    stage = next((s for s in _stages(task) if s.get("name") == stage_name), None)
    if not stage or not stage.get("artifact"):
        return None
    folder = task_folder_name(task["id"], task.get("identifier"))
    path = Path(project_path) / "tasks" / folder / stage["artifact"]
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_reports.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/telegram/reports.py app/tests/telegram/test_reports.py
git commit -m "Telegram: чтение артефактов этапов и нарезка под лимит"
```

---

### Task 5: Запись замечаний (БД + USER_FEEDBACK.md)

**Files:**
- Create: `app/src/agentmon/telegram/feedback.py`
- Test: `app/tests/telegram/test_feedback.py`

**Interfaces:**
- Consumes: `FeedbackRepo` (Task 2), `task_folder_name`.
- Produces:
  - `save_feedback(db, project_path: str, task: dict, chat_id: str, text: str, now=None) -> None` — пишет в `task_feedback` и дозаписывает секцию в `<project>/tasks/task#<id>/USER_FEEDBACK.md`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_feedback.py`:

```python
from pathlib import Path
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.telegram_store import FeedbackRepo
from agentmon.telegram.feedback import save_feedback


def test_save_feedback_writes_db_and_file(tmp_path):
    db = connect(":memory:")
    init_schema(db)
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    task = {"id": 1, "identifier": "001"}
    save_feedback(db, str(tmp_path), task, chat_id="111", text="почини отбор", now=1.0)

    rows = FeedbackRepo(db).list_for_task(1)
    assert rows[0]["text"] == "почини отбор"

    md = (tmp_path / "tasks" / "task#001" / "USER_FEEDBACK.md").read_text(encoding="utf-8")
    assert "почини отбор" in md


def test_save_feedback_appends(tmp_path):
    db = connect(":memory:")
    init_schema(db)
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    task = {"id": 1, "identifier": "001"}
    save_feedback(db, str(tmp_path), task, "111", "первое", now=1.0)
    save_feedback(db, str(tmp_path), task, "111", "второе", now=2.0)
    md = (tmp_path / "tasks" / "task#001" / "USER_FEEDBACK.md").read_text(encoding="utf-8")
    assert "первое" in md and "второе" in md
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_feedback.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.feedback`)

- [ ] **Step 3: Реализовать feedback.py**

Создать `app/src/agentmon/telegram/feedback.py`:

```python
"""Приём пользовательских замечаний: БД + зеркало в USER_FEEDBACK.md."""
from pathlib import Path

from agentmon.env.task_schema import task_folder_name
from agentmon.store.telegram_store import FeedbackRepo

HEADER = "# Замечания пользователя\n\n"


def save_feedback(db, project_path: str, task: dict, chat_id: str, text: str, now=None) -> None:
    FeedbackRepo(db).add(task_id=task["id"], chat_id=chat_id, text=text, now=now)

    folder = task_folder_name(task["id"], task.get("identifier"))
    path = Path(project_path) / "tasks" / folder / "USER_FEEDBACK.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else HEADER
    stamp = f"- (chat {chat_id}, t={now}) {text}\n"
    path.write_text(existing + stamp, encoding="utf-8")
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_feedback.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/telegram/feedback.py app/tests/telegram/test_feedback.py
git commit -m "Telegram: запись замечаний в БД и USER_FEEDBACK.md"
```

---

### Task 6: Нотификатор (дифф статусов)

**Files:**
- Create: `app/src/agentmon/telegram/notifier.py`
- Test: `app/tests/telegram/test_notifier.py`

**Interfaces:**
- Consumes: `TaskRepo.list()`, `StackRepo.list()`/`items()`, `NotifyStateRepo` (Task 2), `BotClient.send_message` (Task 3).
- Produces:
  - `class TelegramNotifier`:
    - `__init__(self, db, send, chat_ids: list[str])` — `send(chat_id, text)` — awaitable-функция отправки (в тестах — фейк; в бою — `BotClient.send_message`). Такое разделение убирает httpx из тестов нотификатора.
    - `async tick(self) -> None` — один проход диффа.
  - Правила переходов задачи (`scope="task"`): уведомляем при смене `last_status`→текущий, если текущий ∈ {`running`,`done`,`failed`,`awaiting_user`}. Первый проход (нет записи в `tg_notify_state`) — записываем baseline молча. `last_status` продвигаем только после успешной отправки всем chat_id.
  - Стек (`scope="stack"`): статус для диффа = `completed`, если у стека есть элементы и все их задачи `done`; иначе текущий `status` стека (`running`/`idle`). Уведомляем при смене на {`running`,`idle`,`completed`} (кроме baseline).

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_notifier.py`:

```python
import pytest
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.tasks import TaskRepo
from agentmon.telegram.notifier import TelegramNotifier


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


class _Sender:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text):
        self.sent.append((chat_id, text))


def _add_project(db):
    return db.returning_id("projects", ["name", "path"], ["p", "/tmp/p"])


@pytest.mark.asyncio
async def test_baseline_silent_then_transition():
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])

    await n.tick()                       # baseline — молчим
    assert s.sent == []

    tr.set_status(tid, "done")
    await n.tick()                       # переход running→done — уведомляем
    assert len(s.sent) == 1
    assert s.sent[0][0] == "111"
    assert "done" in s.sent[0][1].lower() or "заверш" in s.sent[0][1].lower()


@pytest.mark.asyncio
async def test_no_duplicate_on_same_status():
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline
    await n.tick()                       # статус не менялся
    assert s.sent == []
```

Примечание: проверить сигнатуру `TaskRepo.add` в `app/src/agentmon/store/tasks.py:11` и при расхождении привести вызовы в тесте в соответствие (обязательные поля `project_id`, `name`; прочие — как в репозитории).

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_notifier.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.notifier`)

- [ ] **Step 3: Реализовать notifier.py**

Создать `app/src/agentmon/telegram/notifier.py`:

```python
"""Поллер-диффер статусов задач/стеков → уведомления в Telegram."""
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.telegram_store import NotifyStateRepo

logger = logging.getLogger(__name__)

TASK_EVENTS = {"running", "done", "failed", "awaiting_user"}
STACK_EVENTS = {"running", "idle", "completed"}

_TASK_LABEL = {
    "running": "▶️ Задача «{name}» запущена",
    "done": "✅ Задача «{name}» завершена",
    "failed": "❌ Задача «{name}» провалена",
    "awaiting_user": "⏸ Задача «{name}» ждёт пользователя (гейт)",
}
_STACK_LABEL = {
    "running": "▶️ Стек «{name}» запущен",
    "idle": "⏹ Стек «{name}» остановлен",
    "completed": "✅ Стек «{name}» выполнен",
}


class TelegramNotifier:
    def __init__(self, db, send, chat_ids):
        self._db = db
        self._send = send
        self._chat_ids = chat_ids
        self._state = NotifyStateRepo(db)
        self._tasks = TaskRepo(db)
        self._stacks = StackRepo(db)

    async def tick(self) -> None:
        await self._diff_tasks()
        await self._diff_stacks()

    async def _diff_tasks(self) -> None:
        for task in self._tasks.list():
            await self._handle("task", task["id"], task["status"],
                               TASK_EVENTS, _TASK_LABEL, {"name": task["name"]})

    async def _diff_stacks(self) -> None:
        for stack in self._stacks.list():
            status = self._stack_status(stack)
            await self._handle("stack", stack["id"], status,
                               STACK_EVENTS, _STACK_LABEL, {"name": stack["name"]})

    def _stack_status(self, stack) -> str:
        items = self._stacks.items(stack["id"])
        if items:
            done = all(self._tasks.get(i["task_id"]) and
                       self._tasks.get(i["task_id"])["status"] == "done" for i in items)
            if done:
                return "completed"
        return stack["status"]

    async def _handle(self, scope, ref_id, status, events, labels, fmt) -> None:
        prev = self._state.get(scope, ref_id)
        if prev is None:                         # baseline — молчим
            self._state.set(scope, ref_id, status)
            return
        if status == prev or status not in events:
            if status != prev:
                self._state.set(scope, ref_id, status)
            return
        text = labels[status].format(**fmt)
        if await self._emit(text):
            self._state.set(scope, ref_id, status)

    async def _emit(self, text: str) -> bool:
        ok = True
        for chat_id in self._chat_ids:
            try:
                await self._send(chat_id, text)
            except Exception:
                logger.exception("не удалось отправить уведомление в чат %s", chat_id)
                ok = False
        return ok
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_notifier.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/telegram/notifier.py app/tests/telegram/test_notifier.py
git commit -m "Telegram: нотификатор-диффер статусов задач и стеков"
```

---

### Task 7: Хендлеры команд и callback-кнопок

**Files:**
- Create: `app/src/agentmon/telegram/handlers.py`
- Test: `app/tests/telegram/test_handlers.py`

**Interfaces:**
- Consumes: `TaskRepo`, `StackRepo`, `ProjectRepo`, `reports` (Task 4), `feedback.save_feedback` (Task 5); локальный REST через переданный async-callable `api_post(path) -> dict`.
- Produces:
  - `class Handlers`:
    - `__init__(self, db, send, answer, api_post, chat_ids, base_path_of)` где:
      - `send(chat_id, text, reply_markup=None)` — awaitable отправка;
      - `answer(callback_query_id, text=None)` — awaitable ответ на callback;
      - `api_post(path: str) -> dict` — awaitable POST на локальный REST (`/api/env/stacks/{id}/stop` и т.п.);
      - `base_path_of(project_id: int) -> str | None` — путь проекта (из `ProjectRepo`).
    - `async handle_update(self, update: dict) -> None` — разбирает `message` (команды) или `callback_query` (кнопки), проверяет авторизацию, диспетчеризует.
    - `_pending_feedback: dict[str, int]` — чат → task_id, ожидающий текста замечания (состояние диалога «Замечание»).
  - Форматы `callback_data`: `stk:start:<id>`, `stk:stop:<id>`, `tsk:report:<id>`, `rep:<task_id>:<stage>`, `gate:ok:<task_id>:<stage>`, `gate:note:<task_id>:<stage>`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_handlers.py`:

```python
import pytest
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.stacks import StackRepo
from agentmon.telegram.handlers import Handlers


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


class _Caps:
    def __init__(self):
        self.sent, self.answered, self.posted = [], [], []

    async def send(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))

    async def answer(self, cq_id, text=None):
        self.answered.append((cq_id, text))

    async def api_post(self, path, json=None):
        self.posted.append(path)
        return {"ok": True}


def _handlers(db, caps, chat_ids=("111",)):
    return Handlers(db, caps.send, caps.answer, caps.api_post, list(chat_ids),
                    base_path_of=lambda pid: "/tmp/p")


@pytest.mark.asyncio
async def test_unauthorized_ignored():
    db = _db()
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"message": {"chat": {"id": 999}, "text": "/stacks"}})
    assert caps.sent == []                 # чужой чат — молчим


@pytest.mark.asyncio
async def test_stacks_command_lists():
    db = _db()
    StackRepo(db).add(name="001")
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"message": {"chat": {"id": 111}, "text": "/stacks"}})
    assert caps.sent and "001" in caps.sent[0][1]


@pytest.mark.asyncio
async def test_stack_stop_calls_rest():
    db = _db()
    sid = StackRepo(db).add(name="001")
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"callback_query": {
        "id": "cq1", "message": {"chat": {"id": 111}},
        "data": f"stk:stop:{sid}"}})
    assert f"/api/env/stacks/{sid}/stop" in caps.posted
    assert caps.answered                   # ответили на callback


@pytest.mark.asyncio
async def test_gate_note_flow_saves_and_approves(tmp_path):
    db = _db()
    pid = db.returning_id("projects", ["name", "path"], ["p", str(tmp_path)])
    from agentmon.store.tasks import TaskRepo
    import json
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.update(tid, identifier="001",
              stages_json=json.dumps([{"name": "analyze", "artifact": "ANALYZE.md",
                                       "enabled": True, "gate": True}]))
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    caps = _Caps()
    h = Handlers(db, caps.send, caps.answer, caps.api_post, ["111"],
                 base_path_of=lambda p: str(tmp_path))

    # нажали «Замечание» — бот ждёт текст
    await h.handle_update({"callback_query": {
        "id": "cq2", "message": {"chat": {"id": 111}}, "data": f"gate:note:{tid}:analyze"}})
    # прислали текст замечания
    await h.handle_update({"message": {"chat": {"id": 111}, "text": "учти Y"}})

    from agentmon.store.telegram_store import FeedbackRepo
    assert FeedbackRepo(db).list_for_task(tid)[0]["text"] == "учти Y"
    assert f"/api/env/tasks/{tid}/approve" in " ".join(caps.posted)
```

Примечание: для `approve` локальный REST ждёт тело `{"stage": <name>}`; в бою `api_post` должен уметь передавать JSON-тело. Расширить сигнатуру до `api_post(path, json=None)` и в тесте проверять путь (тело можно не проверять). Привести реализацию и фейк к единой сигнатуре.

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_handlers.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.handlers`)

- [ ] **Step 3: Реализовать handlers.py**

Создать `app/src/agentmon/telegram/handlers.py`:

```python
"""Разбор апдейтов Telegram: команды и callback-кнопки."""
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.projects import ProjectRepo
from agentmon.telegram import reports as rep
from agentmon.telegram.client import inline_keyboard
from agentmon.telegram.feedback import save_feedback

logger = logging.getLogger(__name__)


class Handlers:
    def __init__(self, db, send, answer, api_post, chat_ids, base_path_of):
        self._db = db
        self._send = send
        self._answer = answer
        self._api_post = api_post            # async (path, json=None) -> dict
        self._chat_ids = set(str(c) for c in chat_ids)
        self._base_path_of = base_path_of
        self._tasks = TaskRepo(db)
        self._stacks = StackRepo(db)
        self._projects = ProjectRepo(db)
        self._pending_feedback = {}          # chat_id(str) -> (task_id, stage)

    def _authorized(self, chat_id) -> bool:
        return str(chat_id) in self._chat_ids

    async def handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            await self._on_callback(update["callback_query"])
        elif "message" in update:
            await self._on_message(update["message"])

    # --- сообщения/команды ---

    async def _on_message(self, msg: dict) -> None:
        chat_id = str(msg.get("chat", {}).get("id"))
        if not self._authorized(chat_id):
            return
        text = (msg.get("text") or "").strip()

        if chat_id in self._pending_feedback:          # ждём текст замечания
            task_id, stage = self._pending_feedback.pop(chat_id)
            await self._accept_feedback(chat_id, task_id, stage, text)
            return

        if text.startswith("/start"):
            await self._send(chat_id, "AgentMon на связи. Команды: /projects /tasks /stacks")
        elif text.startswith("/projects"):
            await self._list_projects(chat_id)
        elif text.startswith("/tasks"):
            await self._list_tasks(chat_id)
        elif text.startswith("/stacks"):
            await self._list_stacks(chat_id)

    async def _list_projects(self, chat_id) -> None:
        lines = [f"#{p['id']} {p['name']} — {p['path']}" for p in self._projects.list()]
        await self._send(chat_id, "\n".join(lines) or "Проектов нет")

    async def _list_tasks(self, chat_id) -> None:
        for t in self._tasks.list():
            kb = inline_keyboard([[("📄 Отчёты", f"tsk:report:{t['id']}")]])
            await self._send(chat_id,
                             f"#{t['id']} {t['name']} — {t['status']} / {t.get('stage') or '—'}",
                             reply_markup=kb)

    async def _list_stacks(self, chat_id) -> None:
        for s in self._stacks.list():
            buttons = [("▶️ Запустить/Продолжить", f"stk:start:{s['id']}"),
                       ("⏹ Остановить", f"stk:stop:{s['id']}")]
            await self._send(chat_id, f"Стек «{s['name']}» — {s['status']}",
                             reply_markup=inline_keyboard([buttons]))

    # --- callback-кнопки ---

    async def _on_callback(self, cq: dict) -> None:
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id"))
        cq_id = cq.get("id")
        if not self._authorized(chat_id):
            return
        data = cq.get("data") or ""
        try:
            await self._route_callback(chat_id, data)
        finally:
            await self._answer(cq_id)

    async def _route_callback(self, chat_id, data: str) -> None:
        parts = data.split(":")
        kind = parts[0]
        if kind == "stk":
            _, action, sid = parts
            if action == "start":
                await self._api_post(f"/api/env/stacks/{sid}/start")
                await self._send(chat_id, f"Стек {sid}: запуск/продолжение")
            elif action == "stop":
                await self._api_post(f"/api/env/stacks/{sid}/stop")
                await self._send(chat_id, f"Стек {sid}: остановлен")
        elif kind == "tsk" and parts[1] == "report":
            await self._report_menu(chat_id, int(parts[2]))
        elif kind == "rep":
            await self._show_report(chat_id, int(parts[1]), parts[2])
        elif kind == "gate":
            action, task_id, stage = parts[1], int(parts[2]), parts[3]
            if action == "ok":
                await self._api_post(f"/api/env/tasks/{task_id}/approve", json={"stage": stage})
                await self._send(chat_id, "Гейт одобрен")
            elif action == "note":
                self._pending_feedback[chat_id] = (task_id, stage)
                await self._send(chat_id, "Пришлите текст замечания одним сообщением")

    async def _report_menu(self, chat_id, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            await self._send(chat_id, "Задача не найдена")
            return
        rows = [[(s["name"], f"rep:{task_id}:{s['name']}")] for s in rep.enabled_stages(task)]
        await self._send(chat_id, f"Отчёты задачи #{task_id}:",
                         reply_markup=inline_keyboard(rows or [[("нет этапов", "noop")]]))

    async def _show_report(self, chat_id, task_id: int, stage: str) -> None:
        task = self._tasks.get(task_id)
        path = self._base_path_of(task["project_id"]) if task else None
        text = rep.read_report(path, task, stage) if (task and path) else None
        if not text:
            await self._send(chat_id, "Артефакт этапа пуст или отсутствует")
            return
        for part in rep.chunk(text):
            await self._send(chat_id, part)

    async def _accept_feedback(self, chat_id, task_id: int, stage: str, text: str) -> None:
        task = self._tasks.get(task_id)
        path = self._base_path_of(task["project_id"]) if task else None
        if not (task and path):
            await self._send(chat_id, "Задача не найдена")
            return
        save_feedback(self._db, path, task, chat_id, text)
        await self._api_post(f"/api/env/tasks/{task_id}/approve", json={"stage": stage})
        await self._send(chat_id, "Замечание сохранено, гейт одобрен")
```

Примечание: сверить `ProjectRepo.list()`/`get()` в `app/src/agentmon/store/projects.py` и `TaskRepo.add(...)` в `tasks.py:11`; привести вызовы в соответствие при расхождении имён полей.

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/telegram/test_handlers.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/telegram/handlers.py app/tests/telegram/test_handlers.py
git commit -m "Telegram: хендлеры команд, отчётов, управления стеком и гейта"
```

---

### Task 8: Long-poll цикл бота

**Files:**
- Create: `app/src/agentmon/telegram/bot.py`
- Test: `app/tests/telegram/test_bot.py`

**Interfaces:**
- Consumes: `BotClient` (Task 3), `Handlers` (Task 7).
- Produces:
  - `class TelegramBot`:
    - `__init__(self, client, handlers)`.
    - `async poll_once(self) -> None` — один цикл `getUpdates` с текущим `offset`; каждому апдейту вызывает `handlers.handle_update`; продвигает `offset = max(update_id)+1`.
    - `async run(self, stop_event) -> None` — цикл `poll_once` до `stop_event`; на исключениях — лог и короткая пауза (бэкофф), не падает.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_bot.py`:

```python
import pytest
from agentmon.telegram.bot import TelegramBot


class _Client:
    def __init__(self, batches):
        self._batches = list(batches)
        self.offsets = []

    async def get_updates(self, offset=None, timeout=25):
        self.offsets.append(offset)
        return self._batches.pop(0) if self._batches else []


class _Handlers:
    def __init__(self):
        self.seen = []

    async def handle_update(self, update):
        self.seen.append(update)


@pytest.mark.asyncio
async def test_poll_once_advances_offset():
    client = _Client([[{"update_id": 5, "message": {}}, {"update_id": 6, "message": {}}]])
    handlers = _Handlers()
    bot = TelegramBot(client, handlers)
    await bot.poll_once()
    assert len(handlers.seen) == 2
    await bot.poll_once()                       # второй вызов — offset = 7
    assert client.offsets[1] == 7
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_bot.py -q`
Expected: FAIL (`ModuleNotFoundError: agentmon.telegram.bot`)

- [ ] **Step 3: Реализовать bot.py**

Создать `app/src/agentmon/telegram/bot.py`:

```python
"""Long-poll цикл Telegram-бота."""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, client, handlers):
        self._client = client
        self._handlers = handlers
        self._offset = None

    async def poll_once(self) -> None:
        updates = await self._client.get_updates(offset=self._offset, timeout=25)
        for update in updates:
            try:
                await self._handlers.handle_update(update)
            except Exception:
                logger.exception("ошибка обработки апдейта %s", update.get("update_id"))
            self._offset = update["update_id"] + 1

    async def run(self, stop_event) -> None:
        last_error = None
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                signature = (type(exc), str(exc))
                if signature != last_error:
                    logger.exception("цикл бота упал")
                    last_error = signature
                await asyncio.sleep(3.0)         # бэкофф на сетевых сбоях
            else:
                last_error = None
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_bot.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/telegram/bot.py app/tests/telegram/test_bot.py
git commit -m "Telegram: long-poll цикл бота с устойчивым бэкоффом"
```

---

### Task 9: Сборка и интеграция в рантайм

**Files:**
- Create: `app/src/agentmon/telegram/runtime.py`
- Modify: `app/src/agentmon/__main__.py`
- Test: `app/tests/telegram/test_runtime.py`

**Interfaces:**
- Consumes: всё из Tasks 1–8, `config`.
- Produces:
  - `build_bot(db, store, registry) -> tuple[BotClient, TelegramBot, TelegramNotifier] | None` — собирает компоненты, если `config.TG_TOKEN` задан; иначе `None`. Внутри создаёт `api_post` (httpx POST на `config.local_base_url()+path`) и `base_path_of` через `ProjectRepo`.
  - `notifier_send(client)` — возвращает `async (chat_id, text)` обёртку над `client.send_message`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/telegram/test_runtime.py`:

```python
import importlib
import agentmon.config as config
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.telegram import runtime


def test_build_bot_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTMON_TG_TOKEN", raising=False)
    importlib.reload(config)
    importlib.reload(runtime)
    db = connect(":memory:")
    init_schema(db)
    assert runtime.build_bot(db, db, registry=None) is None


def test_build_bot_present_with_token(monkeypatch):
    monkeypatch.setenv("AGENTMON_TG_TOKEN", "T")
    monkeypatch.setenv("AGENTMON_TG_CHAT_IDS", "111")
    importlib.reload(config)
    importlib.reload(runtime)
    db = connect(":memory:")
    init_schema(db)
    built = runtime.build_bot(db, db, registry=None)
    assert built is not None
    client, bot, notifier = built
    assert notifier is not None


def teardown_module(module):
    import os
    os.environ.pop("AGENTMON_TG_TOKEN", None)
    os.environ.pop("AGENTMON_TG_CHAT_IDS", None)
    importlib.reload(config)
    importlib.reload(runtime)
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/telegram/test_runtime.py -q`
Expected: FAIL (`AttributeError: module 'agentmon.telegram.runtime' has no attribute 'build_bot'`)

- [ ] **Step 3: Реализовать runtime.py**

Создать `app/src/agentmon/telegram/runtime.py`:

```python
"""Сборка Telegram-компонентов и обёртки REST/отправки."""
import httpx

from agentmon import config
from agentmon.store.projects import ProjectRepo
from agentmon.telegram.client import BotClient
from agentmon.telegram.bot import TelegramBot
from agentmon.telegram.handlers import Handlers
from agentmon.telegram.notifier import TelegramNotifier


def notifier_send(client):
    async def _send(chat_id, text):
        await client.send_message(chat_id, text)
    return _send


def _api_poster():
    base = config.local_base_url()

    async def _post(path, json=None):
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(base + path, json=json or {})
            resp.raise_for_status()
            return resp.json()
    return _post


def build_bot(db, store, registry=None):
    if not config.TG_TOKEN:
        return None
    client = BotClient(config.TG_TOKEN, config.TG_API_BASE)
    projects = ProjectRepo(db)

    async def _send(chat_id, text, reply_markup=None):
        await client.send_message(chat_id, text, reply_markup=reply_markup)

    async def _answer(cq_id, text=None):
        await client.answer_callback(cq_id, text=text)

    def _base_path_of(project_id):
        p = projects.get(project_id)
        return p["path"] if p else None

    handlers = Handlers(db, _send, _answer, _api_poster(), config.TG_CHAT_IDS, _base_path_of)
    bot = TelegramBot(client, handlers)
    notifier = TelegramNotifier(db, notifier_send(client), config.TG_CHAT_IDS)
    return client, bot, notifier
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/telegram/test_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Встроить в `__main__.py`**

В `app/src/agentmon/__main__.py`: после создания `stack_dispatcher` собрать бота и запустить его цикл + встроить `notifier.tick()` в `dispatch_loop`.

Добавить импорт рядом с прочими:
```python
    from agentmon.telegram.runtime import build_bot
```

После строки `stack_dispatcher = StackDispatcher(app_store, monitor)` добавить:
```python
    tg = build_bot(app_store, app_store, registry)
    tg_client = tg[0] if tg else None
    tg_bot = tg[1] if tg else None
    tg_notifier = tg[2] if tg else None
    tg_stop = asyncio.Event()
```

Внутри `dispatch_loop`, после блока `stack_dispatcher.tick`, добавить тик нотификатора (под своим try, по образцу существующих):
```python
            if tg_notifier is not None:
                try:
                    await tg_notifier.tick()
                except Exception:
                    logger.exception("тик Telegram-нотификатора не удался")
```

В `lifespan` рядом с запуском `dispatch_loop()` поднять цикл бота и корректно погасить при остановке:
```python
    @contextlib.asynccontextmanager
    async def lifespan(application):
        task = asyncio.create_task(dispatch_loop())
        bot_task = asyncio.create_task(tg_bot.run(tg_stop)) if tg_bot else None
        try:
            yield
        finally:
            task.cancel()
            tg_stop.set()
            if bot_task:
                bot_task.cancel()
            if tg_client:
                await tg_client.aclose()
```
(Привести к фактической структуре `lifespan` — сохранить имеющуюся отмену `task` и добавить гашение бота.)

- [ ] **Step 6: Прогнать smoke-тест приложения (бот выключен без токена)**

Run: `cd app && python -m pytest tests/test_app_smoke.py tests/telegram/ -q`
Expected: PASS (без `AGENTMON_TG_TOKEN` бот не стартует, приложение поднимается как раньше)

- [ ] **Step 7: Коммит**

```bash
git add app/src/agentmon/telegram/runtime.py app/src/agentmon/__main__.py app/tests/telegram/test_runtime.py
git commit -m "Telegram: сборка компонентов и интеграция в рантайм (опционально)"
```

---

### Task 10: Правило template для учёта замечаний агентом

**Files:**
- Create: `template/.claude/rules/user-feedback.md`
- Modify: `template/.claude/skills/task-orchestration/SKILL.md` (упоминание правила)
- Test: `app/tests/env/test_content_files.py` (проверка наличия правила в развёртывании)

**Interfaces:**
- Consumes: механизм развёртывания `.claude` (`content.py`, `rglob`).
- Produces: правило, которое субагенты/оркестратор читают перед каждым этапом.

- [ ] **Step 1: Написать/дополнить тест развёртывания**

Проверить `app/tests/env/test_content_files.py` на паттерн перечисления правил. Добавить тест (или кейс), что `user-feedback.md` присутствует среди разворачиваемых файлов `.claude/rules`. Пример (привести к фактическим хелперам файла):

```python
def test_user_feedback_rule_present():
    from agentmon.env.content import CONTENT_DIR
    assert (CONTENT_DIR / "rules" / "user-feedback.md").exists()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_content_files.py -q -k user_feedback`
Expected: FAIL (файла нет)

- [ ] **Step 3: Создать правило**

Создать `template/.claude/rules/user-feedback.md`:

```markdown
---
name: user-feedback
description: Учитывай замечания пользователя из USER_FEEDBACK.md перед каждым этапом задачи.
---

# Замечания пользователя

Если в каталоге задачи `tasks/task#<id>/` есть файл `USER_FEEDBACK.md` — это
замечания пользователя, оставленные через Telegram. Перед выполнением каждого
этапа:

1. Прочитай `USER_FEEDBACK.md` целиком.
2. Отработай открытые замечания в текущем и последующих этапах (аналитика,
   план, тесты, реализация, ревью) — они имеют приоритет над догадками.
3. В артефакте этапа кратко отметь, какие замечания учтены.

Файл ведёт приложение (дозапись). Сам его не удаляй и не переписывай.
```

- [ ] **Step 4: Упомянуть правило в оркестрации**

В `template/.claude/skills/task-orchestration/SKILL.md` добавить строку в разделе про артефакты/жизненный цикл: «Перед каждым этапом учитывай `USER_FEEDBACK.md` (правило `user-feedback`) — замечания пользователя из Telegram.»

- [ ] **Step 5: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/env/test_content_files.py -q`
Expected: PASS

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/rules/user-feedback.md template/.claude/skills/task-orchestration/SKILL.md app/tests/env/test_content_files.py
git commit -m "template: правило user-feedback — учёт замечаний из Telegram"
```

---

### Task 11: Документация и финальный прогон

**Files:**
- Modify: `README.md` (переменные окружения + раздел функционала)
- Modify: `docs/running-web-ui.md` (env Telegram)

**Interfaces:**
- Consumes: ничего. Documentation-only + сквозной прогон.

- [ ] **Step 1: Документировать переменные окружения**

В `README.md` в таблицу «Переменные окружения» добавить строки:

```markdown
| `AGENTMON_TG_TOKEN` | токен Telegram-бота (пусто → интеграция выключена) | — |
| `AGENTMON_TG_CHAT_IDS` | разрешённые chat_id через запятую | — |
```

В раздел «Реализованный функционал» добавить краткий пункт про Telegram-интеграцию (уведомления, управление стеком, отчёты и замечания; long-polling; allowlist).

- [ ] **Step 2: Дополнить docs/running-web-ui.md**

Добавить короткий раздел «Telegram-интеграция (опционально)»: как получить токен у @BotFather, узнать свой `chat_id`, прописать `AGENTMON_TG_TOKEN`/`AGENTMON_TG_CHAT_IDS` в `.ai1c.env`, что доступно (команды `/projects /tasks /stacks`, кнопки на гейте).

- [ ] **Step 3: Полный прогон тестов**

Run: `cd app && python -m pytest -q`
Expected: PASS (все тесты, включая новый пакет `tests/telegram/`)

- [ ] **Step 4: Коммит**

```bash
git add README.md docs/running-web-ui.md
git commit -m "docs: Telegram-интеграция — переменные окружения и инструкция"
```

---

## Примечания по исполнению

- Задачи 3–9 зависят линейно (клиент → reports/feedback → notifier → handlers → bot → runtime). Задачи 4 и 5 независимы между собой и могут идти параллельно после Task 3. Task 10 независима от 1–9 (template-сторона), Task 11 — последняя.
- Перед реализацией каждой задачи субагент сверяет фактические сигнатуры соседних репозиториев (`TaskRepo.add`, `ProjectRepo.get/list`, `Db.execute_rowcount`) и приводит код в соответствие — имена полей важнее примерного кода плана.
- Интеграция в `__main__.py` (Task 9) — единственная правка горячего пути; делать строго по образцу существующих `try`-блоков `dispatch_loop`, не меняя поведения при отсутствии токена.
