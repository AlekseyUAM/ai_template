import pytest
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.run_store import RunStore
from test_monitor import (FakeBackend, FakeBackends, FakeDetachedRunner,
                          FakeFiles, assistant)


def make_client(tmp_path, backend=None, now=1000.0, runner=None):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    backends = FakeBackends(backend)
    store = RunStore(db)
    runner = runner if runner is not None else FakeDetachedRunner()
    mon = Monitor(reg, backends, store=store, runner=runner,
                  generating_window=10.0, now_fn=lambda: now)
    app = create_app(registry=reg, queue=q, monitor=mon)
    client = TestClient(app)
    client.detached_runner = runner      # доступ к управляемому раннеру в тестах
    return client, reg, q, mon, backends


def test_projects_crud(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    assert client.get("/api/projects").json()["projects"] == []

    r = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                           "backend": "local"})
    assert r.status_code == 200
    pid = r.json()["project"]["id"]
    assert r.json()["project"]["alive"] is False

    r = client.put(f"/api/projects/{pid}", json={"name": "renamed"})
    assert r.json()["project"]["name"] == "renamed"

    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get("/api/projects").json()["projects"] == []


def test_create_ssh_project_keeps_conn(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    conn = {"host": "srv", "port": 2222, "user": "root", "key_path": None}
    r = client.post("/api/projects", json={"name": "r", "path": "/srv/r",
                                           "backend": "ssh", "conn": conn})
    body = r.json()["project"]
    assert body["conn"] == conn
    assert body["host"] == "srv"


def test_duplicate_project_is_bad_request(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    payload = {"name": "a", "path": "/proj/a", "backend": "local"}
    client.post("/api/projects", json=payload)
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 400
    assert "уже есть" in r.json()["detail"]


def test_ssh_without_host_is_bad_request(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    r = client.post("/api/projects", json={"name": "a", "path": "/x",
                                           "backend": "ssh", "conn": {}})
    assert r.status_code == 400


def test_unknown_project_is_404(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    assert client.post("/api/projects/999/start").status_code == 404
    assert client.delete("/api/projects/999").status_code == 404


def test_start_runs_next_queued_task(tmp_path):
    """Ручной /start запускает следующую задачу из очереди проекта."""
    client, _, q, mon, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    tid = client.post("/api/queue", json={"project_id": pid, "text": "сделай"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/start")
    assert r.status_code == 200
    assert r.json()["agent_id"]
    # Задача помечена running и прогон записан.
    tasks = client.get("/api/queue", params={"project_id": pid}).json()["tasks"]
    assert tasks[0]["status"] == "running"
    assert mon.task_status(tid) == "running"
    assert client.detached_runner.calls[0][0] == "launch"


def test_start_with_empty_queue_is_bad_request(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    r = client.post(f"/api/projects/{pid}/start")
    assert r.status_code == 400
    assert "пуста" in r.json()["detail"]


def test_stop_reaches_monitor(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    client.post(f"/api/projects/{pid}/start")
    r = client.post(f"/api/projects/{pid}/stop", json={"mode": "kill"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert any(c[0] == "terminate" for c in client.detached_runner.calls)


def test_start_failure_returns_502_with_message(tmp_path):
    runner = FakeDetachedRunner(fail_on_launch="нет связи")
    client, _, _, _, _ = make_client(tmp_path, runner=runner)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    r = client.post(f"/api/projects/{pid}/start")
    assert r.status_code == 502
    assert "нет связи" in r.json()["detail"]


def test_check_reports_ok_and_failure(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    assert client.post(f"/api/projects/{pid}/check").json() == {"ok": True, "error": None}

    backend = FakeBackend(check_error="хост недоступен")
    second = tmp_path / "two"
    second.mkdir()
    client2, _, _, _, _ = make_client(second, backend)
    pid2 = client2.post("/api/projects", json={"name": "b", "path": "/srv/b",
                                               "backend": "ssh",
                                               "conn": {"host": "srv"}}).json()["project"]["id"]
    body = client2.post(f"/api/projects/{pid2}/check").json()
    assert body["ok"] is False
    assert "хост недоступен" in body["error"]


def test_sessions_only_live(tmp_path):
    files = FakeFiles()
    files.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, assistant("/proj/a", 10, 5, "hi"))
    client, _, _, _, _ = make_client(tmp_path, FakeBackend(files=files))
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    assert client.get("/api/sessions").json()["sessions"] == []
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    client.post(f"/api/projects/{pid}/start")
    sessions = client.get("/api/sessions").json()["sessions"]
    assert [s["project_path"] for s in sessions] == ["/proj/a"]
    assert sessions[0]["input_tokens"] == 10


def test_queue_crud(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    tid = client.post("/api/queue", json={"project_id": pid, "text": "t1"}).json()["id"]
    tasks = client.get("/api/queue", params={"project_id": pid}).json()["tasks"]
    assert [t["text"] for t in tasks] == ["t1"]
    client.delete(f"/api/queue/{tid}")
    assert client.get("/api/queue", params={"project_id": pid}).json()["tasks"] == []


def test_queue_for_unknown_project_is_404(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    r = client.post("/api/queue", json={"project_id": 999, "text": "x"})
    assert r.status_code == 404


def test_project_row_carries_last_error(tmp_path):
    runner = FakeDetachedRunner(fail_on_launch="нет связи")
    client, _, _, _, _ = make_client(tmp_path, runner=runner)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    client.post(f"/api/projects/{pid}/start")
    row = client.get("/api/projects").json()["projects"][0]
    assert "нет связи" in row["error"]


def test_ws_pushes_sessions(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    with client.websocket_connect("/ws/sessions") as ws:
        msg = ws.receive_json()
    assert msg == {"sessions": []}


# --- Правка проекта не должна плодить второго агента (Finding 5) ---


def test_changing_path_stops_the_old_agent(tmp_path):
    """Смена ключа проекта: старый агент по новому ключу недостижим — его гасим."""
    client, reg, _, mon, _ = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    client.post(f"/api/projects/{pid}/start")
    runner = client.detached_runner
    assert len(runner.alive) == 1

    client.put(f"/api/projects/{pid}", json={"path": "/proj/b"})
    assert any(c[0] == "terminate" for c in runner.calls)
    assert runner.alive == set()
    assert client.get("/api/projects").json()["projects"][0]["alive"] is False


def test_renaming_a_project_leaves_its_agent_alone(tmp_path):
    """Имя не входит ни в ключ проекта, ни в ключ подключения."""
    client, reg, _, _, backends = make_client(tmp_path)
    pid = client.post("/api/projects", json={"name": "a", "path": "/proj/a",
                                             "backend": "local"}).json()["project"]["id"]
    client.post("/api/queue", json={"project_id": pid, "text": "сделай"})
    client.post(f"/api/projects/{pid}/start")
    runner = client.detached_runner

    client.put(f"/api/projects/{pid}", json={"name": "переименован"})
    assert not any(c[0] == "terminate" for c in runner.calls)
    assert len(runner.alive) == 1
    assert backends.invalidated == []


class BackendsByHost(FakeBackends):
    """Ключ подключения зависит от conn, как в настоящем BackendRegistry."""

    def key_for(self, project):
        if project.backend == "local":
            return "local"
        return f"ssh|{(project.conn or {}).get('host')}"

    def get(self, project):
        return self.backend


def test_changing_host_invalidates_the_old_connection(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    backends = BackendsByHost()
    mon = Monitor(reg, backends, generating_window=10.0, now_fn=lambda: 1000.0)
    client = TestClient(create_app(registry=reg, queue=TaskQueue(db), monitor=mon))

    pid = client.post("/api/projects", json={
        "name": "a", "path": "/srv/x", "backend": "ssh",
        "conn": {"host": "h1", "user": "root"}}).json()["project"]["id"]

    client.put(f"/api/projects/{pid}", json={"conn": {"host": "h2", "user": "root"}})
    assert backends.invalidated == ["ssh|h1"]


# --- Общий бэкенд нельзя рушить из-за правки одного проекта (регрессия) ---


class SharedBackends(FakeBackends):
    """Кеш бэкендов по ключу подключения — как настоящий BackendRegistry.

    Один бэкенд на все локальные проекты и один на каждый хост; invalidate
    по-настоящему закрывает бэкенд, а закрытие гасит всех его агентов.
    Двойник, который только записывал бы ключ, разницы между «выбросили
    соседям бэкенд» и «не тронули» не показал бы вовсе.
    """

    def __init__(self):
        super().__init__()
        self.made: dict[str, FakeBackend] = {}

    def key_for(self, project):
        if project.backend == "local":
            return "local"
        conn = project.conn or {}
        return f"ssh|{conn.get('user')}@{conn.get('host')}"

    def get(self, project):
        key = self.key_for(project)
        backend = self.made.get(key)
        if backend is None:
            backend = FakeBackend(key=key)
            self.made[key] = backend
        return backend

    def invalidate(self, key):
        self.invalidated.append(key)
        backend = self.made.pop(key, None)
        if backend is not None:
            backend.close()

    def items(self):
        return list(self.made.items())

    def close_all(self):
        for key in list(self.made):
            self.invalidate(key)


def make_shared_client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    backends = SharedBackends()
    runner = FakeDetachedRunner()
    mon = Monitor(reg, backends, store=RunStore(db), runner=runner,
                  generating_window=10.0, now_fn=lambda: 1000.0)
    client = TestClient(create_app(registry=reg, queue=q, monitor=mon))
    client.detached_runner = runner
    return client, reg, q, mon, backends


def _start_task(client, pid, text="go"):
    client.post("/api/queue", json={"project_id": pid, "text": text})
    return client.post(f"/api/projects/{pid}/start")


def test_editing_one_project_does_not_kill_a_neighbour_on_the_same_backend(tmp_path):
    """Правка одного проекта не должна гасить агента соседа на том же бэкенде.

    В detached-модели агенты бэкенду не принадлежат; закрытие/инвалидация
    бэкенда их не трогает — живость читается из store по PID. Проверяем, что
    при смене подключения у A его агент убит, а агент B остаётся жив, и общий
    бэкенд не инвалидирован (им ещё пользуется B)."""
    client, reg, _, mon, backends = make_shared_client(tmp_path)
    a = client.post("/api/projects", json={"name": "a", "path": "/srv/a",
                                           "backend": "local"}).json()["project"]["id"]
    b = client.post("/api/projects", json={"name": "b", "path": "/srv/b",
                                           "backend": "local"}).json()["project"]["id"]
    _start_task(client, a)
    _start_task(client, b)
    client.get("/api/sessions")                 # материализует общий бэкенд local
    pa, pb = reg.get(a), reg.get(b)
    assert mon.is_alive(pa) and mon.is_alive(pb)

    client.put(f"/api/projects/{a}", json={
        "backend": "ssh", "conn": {"host": "h1", "user": "root"}})

    assert backends.invalidated == []          # бэкендом пользуется ещё B
    assert backends.made["local"].closed is False
    assert mon.is_alive(reg.get(a)) is False    # убит только агент A
    body = {p["id"]: p for p in client.get("/api/projects").json()["projects"]}
    assert body[b]["alive"] is True
    assert body[b]["error"] is None


def test_last_project_leaving_a_backend_still_invalidates_it(tmp_path):
    """Когда на подключении никого не осталось, соединение держать незачем."""
    client, reg, _, _, backends = make_shared_client(tmp_path)
    pid = client.post("/api/projects", json={
        "name": "a", "path": "/srv/a", "backend": "ssh",
        "conn": {"host": "h1", "user": "root"}}).json()["project"]["id"]
    _start_task(client, pid)
    client.get("/api/sessions")                 # материализует бэкенд ssh|root@h1
    old = backends.made["ssh|root@h1"]

    client.put(f"/api/projects/{pid}", json={"conn": {"host": "h2", "user": "root"}})

    assert backends.invalidated == ["ssh|root@h1"]
    assert old.closed is True


# --- Ошибка не переживает проект (Finding 11) ---


def test_deleting_and_re_adding_a_project_clears_its_error(tmp_path):
    client, reg, _, mon, backends = make_client(tmp_path)
    payload = {"name": "a", "path": "/proj/a", "backend": "local"}
    pid = client.post("/api/projects", json=payload).json()["project"]["id"]

    # Удаление проекта и его повторное добавление: ошибка прошлого проекта не
    # должна переехать на новый (forget вызывается при удалении).
    client.delete(f"/api/projects/{pid}")
    body = client.post("/api/projects", json=payload).json()["project"]
    assert body["error"] is None
    assert client.get("/api/projects").json()["projects"][0]["error"] is None


# --- Недоступный хост виден в списке проектов (Finding 8) ---


def test_projects_list_carries_the_backend_error(tmp_path):
    backend = FakeBackend(key="ssh|root@srv:22", broken=True)
    client, reg, _, mon, backends = make_client(tmp_path, backend)
    client.post("/api/projects", json={"name": "a", "path": "/srv/a",
                                       "backend": "ssh",
                                       "conn": {"host": "srv", "user": "root"}})
    mon.refresh()
    body = client.get("/api/projects").json()["projects"][0]
    assert body["alive"] is False
    assert "srv" in body["error"]


def test_version_endpoint_reports_fresh_process(tmp_path):
    client, _, _, _, _ = make_client(tmp_path)
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert body["stale"] is False
    assert body["loaded"] == body["disk"]
    assert body["uptime_seconds"] >= 0


def test_version_endpoint_reports_stale_code(tmp_path, monkeypatch):
    from agentmon import version

    monkeypatch.setattr(version, "LOADED_FINGERPRINT", "отпечаток-старого-кода")
    client, _, _, _, _ = make_client(tmp_path)
    body = client.get("/api/version").json()
    assert body["stale"] is True
