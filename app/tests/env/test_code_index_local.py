from pathlib import Path
from agentmon.env import code_index_local as L


def test_deploy_local_writes_daemon_toml_and_autostarts(tmp_path):
    ci = tmp_path / "ci"; ci.mkdir()
    captured = {"installs": []}

    def fake_download(code_index_dir, *, log=None, **k):
        if log:
            log("скачал")
        return Path(code_index_dir) / "bsl-indexer"

    def fake_install(name, argv, *, env, state_dir):
        captured["installs"].append((name, tuple(argv), dict(env)))
        return [f"установлен {name}"]

    log = list(L.deploy_local(
        mid=7, code_index_dir=str(ci), catalog_dir="/code/cfg",
        project_name="proj", port=8005,
        download=fake_download, install=fake_install))

    text = "\n".join(log)
    # daemon.toml записан с alias=имя проекта и path=каталог кодовой базы
    daemon = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "proj"' in daemon
    assert 'path = "/code/cfg"' in daemon
    # два автозапуска: daemon run и serve
    names = [i[0] for i in captured["installs"]]
    assert names == ["ai1c-code-index-daemon-7", "ai1c-code-index-mcp-7"]
    daemon_i, serve_i = captured["installs"]
    assert daemon_i[1][-2:] == ("daemon", "run")
    assert daemon_i[2]["CODE_INDEX_HOME"] == str(ci)
    assert serve_i[1][-1] == "serve"
    assert serve_i[2]["MCP_HTTP_PORT"] == "8005"
    assert serve_i[2]["MCP_HTTP_HOST"] == "127.0.0.1"
    assert "proj" in text and "8005" in text
