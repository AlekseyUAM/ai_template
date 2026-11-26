from pathlib import Path
import pytest
from agentmon.env import code_index_local as L


def _fake_download(code_index_dir, *, log=None, **k):
    if log:
        log("скачал")
    path = Path(code_index_dir) / "bsl-indexer"
    path.write_text("bin", encoding="utf-8")
    return path


def _install(calls):
    def install(name, argv, *, env, state_dir):
        calls.append(("install", name, tuple(argv), dict(env)))
        return [f"install {name}"]
    return install


def test_first_deploy_creates_service_and_starts(tmp_path):
    ci = tmp_path / "ci"
    calls = []
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(calls),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    assert (ci / "service.json").is_file()
    assert L.read_service_port(ci) == 8005
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "a"' in text and 'path = "/code/a"' in text
    names = [c[1] for c in calls if c[0] == "install"]
    assert names == [L.service_names(ci)[0], L.service_names(ci)[1]]
    assert "8005" in "\n".join(log)


def test_second_deploy_adds_base_without_reinstall(tmp_path):
    ci = tmp_path / "ci"
    installs, restarts, reloads = [], [], []
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: restarts.append(a) or [],
        stop=lambda *a, **k: []))
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: restarts.append(a) or [],
        stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "",
                                           "stderr": ""})()))
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert text.count("[[paths]]") == 2
    assert 'alias = "a"' in text and 'alias = "b"' in text
    assert text.count("[[cache_targets]]") == 1
    assert "http://127.0.0.1:8005" in text
    assert L.read_service_port(ci) == 8005
    assert len(installs) == 2          # только первое развёртывание
    assert restarts and restarts[0][0] == L.service_names(ci)[1]
    assert "8005" in "\n".join(log)


def _ok_run(*a, **k):
    return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()


def test_first_deploy_install_argv_and_env(tmp_path):
    ci = tmp_path / "ci"
    calls = []
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(calls),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    binary = ci / "bsl-indexer"
    daemon_name, serve_name = L.service_names(ci)
    daemon_i, serve_i = calls
    assert daemon_i[1] == daemon_name
    assert daemon_i[2][-2:] == ("daemon", "run")
    assert daemon_i[3]["CODE_INDEX_HOME"] == str(ci)
    assert serve_i[1] == serve_name
    argv = serve_i[2]
    assert argv[1] == "serve"
    assert argv[argv.index("--transport") + 1] == "http"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "8005"
    assert argv[argv.index("--config") + 1] == str(ci / "daemon.toml")
    assert serve_i[3]["MCP_HTTP_PORT"] == "8005"
    assert binary.is_file()


def test_service_names_depend_on_resolved_dir_not_mid(tmp_path):
    ci = tmp_path / "ci"
    names = L.service_names(ci)
    assert names == L.service_names(str(ci))
    assert names[0] == f"ai1c-code-index-daemon-{L.service_id(ci)}"
    assert names[1] == f"ai1c-code-index-mcp-{L.service_id(ci)}"
    assert L.service_names(tmp_path / "other") != names
    assert len(L.service_id(ci)) == 8


def test_service_port_roundtrip_and_invalid(tmp_path):
    ci = tmp_path / "ci"
    ci.mkdir()
    assert L.read_service_port(ci) is None
    L.write_service_port(ci, 8007)
    assert L.read_service_port(ci) == 8007
    (ci / L.SERVICE_FILE).write_text('{"port": "x"}', encoding="utf-8")
    assert L.read_service_port(ci) is None


def _events(events):
    def install(name, argv, *, env, state_dir):
        events.append(("install", name))
        return [f"install {name}"]

    def stop(name, *, state_dir=None, home=None, **k):
        events.append(("stop", name))
        return []
    return install, stop


def test_first_deploy_cleans_legacy_mid_services(tmp_path):
    ci = tmp_path / "ci"
    events = []
    install, stop = _events(events)
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, mid=7, download=_fake_download, install=install,
        restart=lambda *a, **k: [], stop=stop))
    assert events == [
        ("stop", "ai1c-code-index-daemon-7"),
        ("stop", "ai1c-code-index-mcp-7"),
        ("install", L.service_names(ci)[0]),
        ("install", L.service_names(ci)[1]),
    ]
    assert L.read_service_port(ci) == 8005


def test_first_deploy_rolls_back_daemon_when_serve_install_fails(tmp_path):
    ci = tmp_path / "ci"
    daemon_name, serve_name = L.service_names(ci)
    stopped = []

    def install(name, argv, *, env, state_dir):
        if name == daemon_name:
            return ["install daemon"]
        raise RuntimeError("install failed")

    def stop(name, *, state_dir=None, home=None, **k):
        stopped.append(name)
        return []

    with pytest.raises(RuntimeError, match="install failed"):
        list(L.deploy_local(
            code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
            port=8005, mid=7, download=_fake_download, install=install,
            restart=lambda *a, **k: [], stop=stop))
    # legacy first, then rollback of both new names (serve stop is idempotent)
    assert stopped == ["ai1c-code-index-daemon-7",
                       "ai1c-code-index-mcp-7",
                       serve_name, daemon_name]
    assert not (ci / L.SERVICE_FILE).exists()


def test_second_deploy_reports_reload_error_but_continues(tmp_path):
    ci = tmp_path / "ci"
    installs = []
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: [],
        stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "",
                                           "stderr": "boom"})()))
    text = "\n".join(log)
    assert "daemon reload: boom" in text
    assert L.read_service_port(ci) == 8005
    assert len(installs) == 2


def test_second_deploy_restarts_daemon_when_reload_fails(tmp_path):
    """Демон мог быть остановлен: reload некому ответить — поднимаем юнит."""
    ci = tmp_path / "ci"
    ci.mkdir()
    L.write_service_port(ci, 8005)
    (ci / "bsl-indexer").write_text("bin", encoding="utf-8")
    restarts = []

    def restart(name, *, state_dir=None, home=None):
        restarts.append(name)
        return []

    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=8005, download=_fake_download, install=_install([]),
        restart=restart, stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "",
                                           "stderr": "boom"})()))
    daemon_name, serve_name = L.service_names(ci)
    assert "daemon reload: boom" in "\n".join(log)
    assert restarts == [daemon_name, serve_name]
    assert L.read_service_port(ci) == 8005


def test_port_mismatch_with_existing_service_raises(tmp_path):
    ci = tmp_path / "ci"
    ci.mkdir()
    L.write_service_port(ci, 8005)
    with pytest.raises(ValueError, match="8005"):
        list(L.deploy_local(
            code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
            port=9999, download=_fake_download, install=_install([]),
            restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    assert L.read_service_port(ci) == 8005


def test_first_deploy_forwards_home_to_legacy_stop(tmp_path):
    ci = tmp_path / "ci"
    captured = []

    def stop(name, *, state_dir=None, home=None, **k):
        captured.append(home)
        return []

    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, mid=7, home="/h", download=_fake_download,
        install=_install([]), restart=lambda *a, **k: [], stop=stop))
    assert captured == ["/h", "/h"]


def test_second_deploy_forwards_home_to_restart(tmp_path):
    ci = tmp_path / "ci"
    ci.mkdir()
    L.write_service_port(ci, 8005)
    restarts = []

    def restart(name, *, state_dir=None, home=None):
        restarts.append((name, state_dir, home))
        return []

    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=8005, home="/h", download=_fake_download, install=_install([]),
        restart=restart, stop=lambda *a, **k: [], run=_ok_run))
    assert restarts == [(L.service_names(ci)[1], str(ci), "/h")]


# --- порт, занятый старым сервисом после переноса каталога ---

def test_first_deploy_refuses_when_port_busy(tmp_path):
    ci = tmp_path / "ci"
    calls = []
    with pytest.raises(ValueError, match="8005"):
        list(L.deploy_local(
            code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
            port=8005, download=_fake_download, install=_install(calls),
            restart=lambda *a, **k: [], stop=lambda *a, **k: [],
            tcp_ok=lambda _url: True))
    assert calls == []                         # до любых install
    assert not (ci / L.SERVICE_FILE).exists()
    assert not (ci / "daemon.toml").exists()


def test_second_deploy_does_not_probe_port(tmp_path):
    ci = tmp_path / "ci"
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install([]),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    probed = []
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=8005, download=_fake_download, install=_install([]),
        restart=lambda *a, **k: [], stop=lambda *a, **k: [], run=_ok_run,
        tcp_ok=lambda url: probed.append(url) or True))
    assert probed == []                        # сервис уже наш — проба не нужна


# --- откат daemon.toml при неудачной первой установке ---

def test_first_install_failure_restores_existing_daemon_toml(tmp_path):
    ci = tmp_path / "ci"
    ci.mkdir()
    old = ('[daemon]\nhttp_host = "127.0.0.1"\nhttp_port = 0\n'
           'log_level = "info"\n\n[[paths]]\npath = "/code/old"\n'
           'alias = "old"\nlanguage = "bsl"\n')
    (ci / "daemon.toml").write_text(old, encoding="utf-8")
    daemon_name, _serve_name = L.service_names(ci)

    def install(name, argv, *, env, state_dir):
        if name == daemon_name:
            return ["install daemon"]
        raise RuntimeError("install failed")

    with pytest.raises(RuntimeError, match="install failed"):
        list(L.deploy_local(
            code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
            port=8005, download=_fake_download, install=install,
            restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert text == old
    assert text.count("[[paths]]") == 1 and 'alias = "a"' not in text
    assert not (ci / L.SERVICE_FILE).exists()


def test_first_install_failure_removes_created_daemon_toml(tmp_path):
    ci = tmp_path / "ci"

    def install(name, argv, *, env, state_dir):
        raise RuntimeError("install failed")

    with pytest.raises(RuntimeError, match="install failed"):
        list(L.deploy_local(
            code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
            port=8005, download=_fake_download, install=install,
            restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    assert not (ci / "daemon.toml").exists()
