from pathlib import Path
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
        port=9999, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: restarts.append(a) or [],
        stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "",
                                           "stderr": ""})()))
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert text.count("[[paths]]") == 2
    assert 'alias = "a"' in text and 'alias = "b"' in text
    assert L.read_service_port(ci) == 8005
    assert len(installs) == 2          # только первое развёртывание
    assert restarts and restarts[0][0] == L.service_names(ci)[1]
    assert "8005" in "\n".join(log)


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


def test_first_deploy_cleans_legacy_mid_services(tmp_path):
    ci = tmp_path / "ci"
    stopped = []

    def stop(name, *, state_dir=None, **k):
        stopped.append(name)
        return []

    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, mid=7, download=_fake_download, install=_install([]),
        restart=lambda *a, **k: [], stop=stop))
    assert stopped == ["ai1c-code-index-daemon-7", "ai1c-code-index-mcp-7"]


def test_second_deploy_reports_reload_error_but_continues(tmp_path):
    ci = tmp_path / "ci"
    installs = []
    list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=9999, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: [],
        stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "",
                                           "stderr": "boom"})()))
    text = "\n".join(log)
    assert "daemon reload: boom" in text
    assert L.read_service_port(ci) == 8005
    assert len(installs) == 2
