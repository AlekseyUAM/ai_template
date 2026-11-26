import pytest

from agentmon.env import code_index_docker
from env.fakes_code_index import FakeProvisioner


def _download(tmp, log=None, platform_name=None):
    assert platform_name == "linux"
    from pathlib import Path
    path = Path(tmp) / "bsl-indexer"
    path.write_bytes(b"bin")
    return path


def test_deploy_installs_binary_and_starts_processes():
    prov = FakeProvisioner()
    lines = list(code_index_docker.deploy(
        prov, code_index_dir="/code-index", catalog_dir="/workspace/src/cf",
        alias="demo", port=8005, download=_download))
    assert any("бинарь установлен" in line for line in lines)
    assert prov.copies and prov.copies[0][1] == "/code-index/bsl-indexer"
    assert ["chmod", "+x", "/code-index/bsl-indexer"] in [
        r["argv"] for r in prov.runs]
    toml = prov.writes["/code-index/daemon.toml"]
    assert 'alias = "demo"' in toml and 'path = "/workspace/src/cf"' in toml
    service = prov.writes["/code-index/service.json"]
    assert '"port": 8005' in service
    assert len(prov.detached) == 2
    assert prov.detached[0]["env"]["CODE_INDEX_HOME"] == "/code-index"
    assert prov.detached[1]["env"]["MCP_HTTP_PORT"] == "8005"


def test_deploy_keeps_existing_paths():
    prov = FakeProvisioner()
    prov.writes["/code-index/bsl-indexer"] = "bin"
    prov.writes["/code-index/daemon.toml"] = (
        '[daemon]\nhttp_host = "127.0.0.1"\n\n'
        '[[paths]]\npath = "/other/src/cf"\nalias = "other"\nlanguage = "bsl"\n')
    list(code_index_docker.deploy(
        prov, code_index_dir="/code-index", catalog_dir="/workspace/src/cf",
        alias="demo", port=8005, download=_download))
    toml = prov.writes["/code-index/daemon.toml"]
    assert 'alias = "other"' in toml and 'alias = "demo"' in toml
    assert not prov.copies


def test_wait_ready_success():
    calls = {"n": 0}

    def status():
        calls["n"] += 1
        return {"paths": [{"path": "/workspace/src/cf", "status": "ready"}]}

    code_index_docker.wait_ready(
        FakeProvisioner(), code_index_dir="/code-index", port=8005,
        status=status, alive=lambda: True, log_tail=lambda name: "",
        sleep=lambda _s: None, clock=lambda: 0.0)
    assert calls["n"] == 1


def test_wait_ready_error_status_raises():
    def status():
        return {"paths": [{"path": "/workspace/src/cf", "status": "error",
                           "error": "boom"}]}

    with pytest.raises(Exception, match="boom"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            status=status, alive=lambda: True, log_tail=lambda name: "",
            sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_dead_process_raises_with_logs():
    with pytest.raises(Exception, match="завершился"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            status=lambda: None, alive=lambda: False,
            log_tail=lambda name: f"{name}-tail",
            sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_timeout():
    times = iter([0.0, 0.0, 1.0])
    with pytest.raises(Exception, match="не проиндексировал"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            wait_minutes=1, status=lambda: {"paths": []}, alive=lambda: True,
            log_tail=lambda name: "", sleep=lambda _s: None,
            clock=lambda: next(times, 10_000.0))


def test_wait_ready_daemon_startup_grace():
    """Демон не ответил, но serve жив (pgrep видит процесс): ждём старта
    и падаем по grace, а не висим до общего таймаута."""
    times = iter([0.0, 0.0, 200.0])
    with pytest.raises(Exception, match="не запустился"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            wait_minutes=1, status=lambda: None, alive=lambda: True,
            grace_seconds=10, log_tail=lambda name: "",
            sleep=lambda _s: None, clock=lambda: next(times, 10_000.0))


def test_wait_ready_dead_after_indexing_raises():
    """Демон был жив и перестал отвечать — падаем сразу, не ждём таймаут."""
    states = iter([{"paths": [{"path": "/workspace/src/cf",
                               "status": "indexing"}]}, None])
    times = iter([0.0, 0.0, 100.0])
    with pytest.raises(Exception, match="завершился"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            wait_minutes=1, status=lambda: next(states, None),
            alive=lambda: True, log_tail=lambda name: "",
            sleep=lambda _s: None, clock=lambda: next(times, 10_000.0))


def test_stop_pkills_bsl_indexer_and_clears_pid():
    """После остановки убираем daemon.pid/daemon.json: иначе зомби-PID
    заставит новый демон отказаться стартовать («уже запущен»)."""
    prov = FakeProvisioner()
    code_index_docker.stop(prov, "/code-index")
    joined = " ".join(prov.runs[-1]["argv"])
    assert "pkill" in joined and "[b]sl-indexer" in joined
    assert "rm -f /code-index/daemon.pid" in joined
    assert "/code-index/daemon.json" in joined
