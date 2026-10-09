from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def make(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db), queue=TaskQueue(db),
                                 monitor=mon, store=store))


def test_standard_presets(tmp_path):
    data = make(tmp_path).get("/api/mcp/standard").json()["standard"]
    ids = {s["id"] for s in data}
    assert {"1c-md", "code-index", "1c-naparnic"} <= ids


def test_crud_custom_mcp(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={"name": "my", "kind": "custom",
                                 "connection_json": '{"url":"http://x"}'})
    assert r.status_code == 200
    mid = r.json()["mcp"]["id"]
    assert any(m["name"] == "my" for m in c.get("/api/mcp").json()["mcp"])
    assert c.delete(f"/api/mcp/{mid}").status_code == 200


def test_launch_extension_rejected(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={"name": "1c-md", "kind": "extension",
                                   "standard_key": "1c-md"}).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={})
    assert r.status_code == 400


def test_types_endpoint_lists_seven_with_custom_first(tmp_path):
    data = make(tmp_path).get("/api/mcp/types").json()["types"]
    assert data[0]["key"] == "custom"
    keys = {t["key"] for t in data}
    assert keys == {"custom", "1c-md", "1c-md-queries", "bsl-ls",
                    "1c-platform", "1c-naparnic", "code-index"}


def test_create_persists_new_fields(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "mcp_name": "code_index", "url": "localhost", "port": 8004,
        "catalog_dir": "/src/cfg",
        "connection_json": '"code_index": {"type":"http"}',
    })
    assert r.status_code == 200
    row = r.json()["mcp"]
    assert row["mcp_name"] == "code_index"
    assert row["url"] == "localhost"
    assert row["catalog_dir"] == "/src/cfg"


def test_create_persists_db_name(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={
        "name": "md", "kind": "extension", "standard_key": "1c-md",
        "url": "host1", "db_name": "my_base",
    })
    assert r.status_code == 200
    assert r.json()["mcp"]["db_name"] == "my_base"


def test_create_persists_platform_path(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={
        "name": "plat", "kind": "docker", "standard_key": "1c-platform",
        "port": 8002, "platform_path": "/opt/1cv8/x86_64/8.3.27",
    })
    assert r.status_code == 200
    assert r.json()["mcp"]["platform_path"] == "/opt/1cv8/x86_64/8.3.27"


def test_update_new_fields(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={"name": "u", "kind": "docker",
                                   "standard_key": "bsl-ls"}).json()["mcp"]["id"]
    r = c.put(f"/api/mcp/{mid}", json={"url": "example", "mcp_name": "bsl_ls"})
    assert r.status_code == 200
    assert r.json()["mcp"]["url"] == "example"


def test_launch_code_index_uses_recipe(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    calls = {}
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: True)
    def fake_launch(**kw):
        calls.update(kw)
        return {"ok": True, "container": kw["name"], "log": "started"}
    monkeypatch.setattr(mcp_docker, "launch", fake_launch)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog),
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8004})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert calls["image"] == "bsl-indexer:local"
    assert calls["env"]["MCP_HTTP_PORT"] == "8004"
    assert any("/repos/src" in v for v in calls["volumes"])


def test_launch_builds_image_when_missing(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    built = {}
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: False)
    def fake_build(tag, dockerfile, context, **k):
        built["tag"] = tag
        return {"ok": True, "log": "built"}
    monkeypatch.setattr(mcp_docker, "build", fake_build)
    monkeypatch.setattr(mcp_docker, "launch",
                        lambda **kw: {"ok": True, "container": kw["name"], "log": "run"})

    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "bsl", "kind": "docker", "standard_key": "bsl-ls", "port": 8001,
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8001})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert built["tag"] == "ai1c/mcp-bsl-ls:local"


def test_delete_docker_mcp_keeps_container(tmp_path, monkeypatch):
    # удаление карточки docker-вида не должно трогать контейнер
    from agentmon.env import mcp_docker
    called = {"n": 0}
    monkeypatch.setattr(mcp_docker, "stop",
                        lambda name, **k: called.update(n=called["n"] + 1) or {"ok": True})
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "bsl", "kind": "docker", "standard_key": "bsl-ls",
        "mcp_name": "bsl_ls", "port": 8001,
    }).json()["mcp"]["id"]
    assert c.delete(f"/api/mcp/{mid}").status_code == 200
    assert called["n"] == 0


def test_delete_custom_mcp_does_not_stop(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    called = {"n": 0}
    monkeypatch.setattr(mcp_docker, "stop",
                        lambda name, **k: called.update(n=called["n"] + 1) or {"ok": True})
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={"name": "my", "kind": "custom",
                                   "connection_json": '{"url":"http://x"}'}).json()["mcp"]["id"]
    assert c.delete(f"/api/mcp/{mid}").status_code == 200
    assert called["n"] == 0  # у произвольного вида контейнера нет


def test_launch_stream_streams_run_log(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    monkeypatch.setattr(mcp_docker, "image_exists", lambda t, **k: True)

    def fake_iter(cmd, **k):
        if cmd[:3] == ["docker", "rm", "-f"]:
            yield mcp_docker.rc_line(0)
            return
        yield "docker: starting"
        yield "container-id-123"
        yield mcp_docker.rc_line(0)
    monkeypatch.setattr(mcp_docker, "iter_output", fake_iter)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog),
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch/stream", json={"port": 8004})
    assert r.status_code == 200
    body = r.text
    assert "Запуск контейнера" in body
    assert "container-id-123" in body
    assert "Контейнер запущен" in body


def test_launch_stream_builds_then_runs(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    monkeypatch.setattr(mcp_docker, "image_exists", lambda t, **k: False)

    def fake_iter(cmd, **k):
        if cmd[:2] == ["docker", "build"]:
            yield "Step 1/3"
            yield "downloaded jar"
            yield mcp_docker.rc_line(0)
            return
        if cmd[:3] == ["docker", "rm", "-f"]:
            yield mcp_docker.rc_line(0)
            return
        yield "cid"
        yield mcp_docker.rc_line(0)
    monkeypatch.setattr(mcp_docker, "iter_output", fake_iter)

    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "bsl", "kind": "docker", "standard_key": "bsl-ls", "port": 8001,
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch/stream", json={"port": 8001})
    body = r.text
    assert "Сборка образа" in body and "downloaded jar" in body
    assert "Образ собран" in body and "Контейнер запущен" in body


def test_launch_prebuilt_only_missing_image_reports(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: False)
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "nap", "kind": "docker", "standard_key": "1c-naparnic", "port": 8003,
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8003})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False and "не найден" in data["log"]


def test_download_cfe_for_queries_type(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "md-q", "kind": "extension", "standard_key": "1c-md-queries",
    }).json()["mcp"]["id"]
    r = c.get(f"/api/mcp/{mid}/download")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "1c-mcp-tools-1.0.6.cfe" in cd
