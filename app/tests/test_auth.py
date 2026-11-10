import pytest

from agentmon import config
from test_api import make_client


def test_no_token_keeps_loopback_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN", None)
    client, *_ = make_client(tmp_path)
    assert client.get("/api/projects").status_code == 200


def test_token_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TOKEN", "s3cret")
    client, *_ = make_client(tmp_path)

    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"X-Agentmon-Token": "nope"}).status_code == 401

    assert client.get("/api/projects",
                      headers={"X-Agentmon-Token": "s3cret"}).status_code == 200
    assert client.get("/api/projects",
                      headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/projects?token=s3cret").status_code == 200


def test_origin_must_match_host(tmp_path):
    client, *_ = make_client(tmp_path)
    assert client.get("/api/projects", headers={"Origin": "http://testserver"}).status_code == 200
    assert client.get("/api/projects", headers={"Origin": "http://evil.example"}).status_code == 403
    assert client.get("/api/projects", headers={"Origin": "null"}).status_code == 403


def test_foreign_host_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOST", "127.0.0.1")
    monkeypatch.setattr(config, "TOKEN", None)
    monkeypatch.setattr(config, "ALLOWED_HOSTS", [])
    client, *_ = make_client(tmp_path)
    assert client.get("/api/projects", headers={"Host": "evil.example"}).status_code == 400


def test_allowed_host_list(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOST", "127.0.0.1")
    monkeypatch.setattr(config, "TOKEN", None)
    monkeypatch.setattr(config, "ALLOWED_HOSTS", ["agentmon.local"])
    client, *_ = make_client(tmp_path)
    assert client.get("/api/projects", headers={"Host": "agentmon.local"}).status_code == 200


def test_wide_bind_requires_token():
    with pytest.raises(SystemExit):
        config.ensure_secure_bind(host="0.0.0.0", token=None)
    config.ensure_secure_bind(host="0.0.0.0", token="x")   # не бросает
    config.ensure_secure_bind(host="127.0.0.1", token=None)  # не бросает
