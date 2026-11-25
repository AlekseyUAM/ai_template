import pytest

from agentmon.env import code_index_project
from agentmon.env.code_index_project import (
    CodeIndexError, CodeIndexRequest, pick_port, resolve_card, validate_request)
from env.fakes_code_index import FakeProvisioner


class _Repo:
    def __init__(self):
        self.rows = []
        self.links = {}

    def list(self):
        return list(self.rows)

    def add(self, **fields):
        mid = len(self.rows) + 1
        row = {"id": mid, **fields}
        self.rows.append(row)
        return mid

    def for_project(self, pid):
        ids = self.links.get(pid, [])
        return [r for r in self.rows if r["id"] in ids]

    def set_for_project(self, pid, ids):
        self.links[pid] = list(ids)


def test_validate_local_absolute_and_outside():
    req = validate_request("local", "/work/demo",
                           CodeIndexRequest("/work/demo/src/cf",
                                            "/work/demo-code-index"))
    assert req.code_index_dir.endswith("demo-code-index")
    with pytest.raises(CodeIndexError, match="абсолютным"):
        validate_request("local", "/work/demo",
                         CodeIndexRequest("src/cf", "/work/demo-code-index"))
    with pytest.raises(CodeIndexError, match="внутри"):
        validate_request("local", "/work/demo",
                         CodeIndexRequest("/work/demo/src/cf", "/work/demo/ci"))


def test_validate_docker_paths():
    req = validate_request("docker", "/workspace",
                           CodeIndexRequest("/workspace/src/cf", "/code-index"))
    assert req.code_index_dir == "/code-index"
    with pytest.raises(CodeIndexError, match="внутри"):
        validate_request("docker", "/workspace",
                         CodeIndexRequest("/workspace/src/cf", "/workspace/ci"))
    with pytest.raises(CodeIndexError, match="только для local"):
        validate_request("ssh", "/workspace",
                         CodeIndexRequest("/workspace/src/cf", "/code-index"))


def test_pick_port_reads_service_json():
    assert pick_port(lambda: 8010, host_check=False) == 8010


def test_pick_port_first_free():
    busy = {"http://127.0.0.1:8005", "http://127.0.0.1:8006"}
    port = pick_port(lambda: None, tcp_ok=lambda url: url in busy)
    assert port == 8007


def test_pick_port_no_host_check():
    assert pick_port(lambda: None, host_check=False) == 8005


def test_pick_port_exhausted():
    with pytest.raises(CodeIndexError, match="свободный порт"):
        pick_port(lambda: None, tcp_ok=lambda url: True)


def test_resolve_card_creates_and_reuses():
    repo = _Repo()
    req = CodeIndexRequest("/work/demo/src/cf", "/work/demo-code-index")
    mid, selection, created = resolve_card(
        repo, project_id=7, project_name="demo", backend="local",
        request=req, port=8005)
    assert created and mid == 1 and selection.id == "code-index"
    assert selection.catalog_dir == req.catalog_dir
    assert "code_index" in selection.connection
    mid2, _, created2 = resolve_card(
        repo, project_id=8, project_name="demo", backend="local",
        request=req, port=8005)
    assert mid2 == mid and created2 is False
    mid3, sel3, created3 = resolve_card(
        repo, project_id=9, project_name="other", backend="local",
        request=req, port=8005)
    assert created3 and mid3 != mid
    assert repo.rows[-1]["name"] == "other: code_index"


def test_resolve_card_docker_standard_key():
    repo = _Repo()
    req = CodeIndexRequest("/workspace/src/cf", "/code-index")
    _, selection, _ = resolve_card(
        repo, project_id=1, project_name="demo", backend="docker",
        request=req, port=8005)
    assert selection.id == "code-index-docker"
    assert repo.rows[0]["standard_key"] == "code-index-docker"
    assert repo.rows[0]["kind"] == "docker"


def test_container_service_port_reads_json():
    prov = FakeProvisioner()
    prov.writes["/code-index/service.json"] = '{"port": 8011}'
    assert code_index_project.container_service_port(prov, "/code-index") == 8011
    prov.writes["/code-index/service.json"] = "bad"
    assert code_index_project.container_service_port(prov, "/code-index") is None


def test_wait_ready_local_success():
    code_index_project.wait_ready_local(
        "/ci", port=8005,
        status=lambda ci: {"paths": [{"path": "/cf", "status": "ready"}]},
        tcp_ok=lambda url: True, sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_local_error():
    with pytest.raises(CodeIndexError, match="ошибка индексации"):
        code_index_project.wait_ready_local(
            "/ci", port=8005,
            status=lambda ci: {"paths": [{"path": "/cf", "status": "error",
                                          "error": "bad"}]},
            tcp_ok=lambda url: True, sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_local_timeout():
    times = iter([0.0, 0.0, 10_000.0])
    with pytest.raises(CodeIndexError, match="не проиндексировал"):
        code_index_project.wait_ready_local(
            "/ci", port=8005, wait_minutes=1,
            status=lambda ci: {"paths": []}, tcp_ok=lambda url: True,
            sleep=lambda _s: None, clock=lambda: next(times, 10_000.0))
