import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentmon.env import code_index_bench as B
from agentmon.env import code_index_release as R


def test_clean_removes_dirs_and_legacy_container(tmp_path):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 0, "serve": 0}')
    catalog = tmp_path / "catalog"; (catalog / ".code-index").mkdir(parents=True)
    calls = []
    B.clean_code_index(ci, catalog, run=lambda cmd, **k: calls.append(cmd),
                       log=lambda _m: None)
    assert not ci.exists()
    assert not (catalog / ".code-index").exists()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


def test_start_writes_pid_and_toml(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    def fake_download(dest, *, log=None):
        Path(dest).mkdir(parents=True, exist_ok=True)
        bin_path.write_text("bin", encoding="utf-8")
        return bin_path
    pids = iter([111, 222])
    class Proc:
        def __init__(self):
            self.pid = next(pids)
    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    index = B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=fake_download, popen=lambda *a, **k: Proc(),
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""))
    assert index.daemon_pid == 111 and index.serve_pid == 222
    assert (ci / "benchmark-pids.json").is_file()
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "a"' in text and str(catalog.resolve()) in text


def test_stop_kills_own_pids(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    killed, calls = [], []
    checks = {"n": 0}

    def ours(pid, run):
        checks["n"] += 1
        return checks["n"] <= 2          # живы только до SIGTERM

    monkeypatch.setattr(B, "_is_our_process", ours)
    B.stop_code_index(ci, run=lambda cmd, **k: calls.append(cmd),
                      kill=lambda pid, sig: killed.append(pid),
                      sleep=lambda _s: None, clock=lambda: 0.0,
                      log=lambda _m: None)
    assert killed == [10, 11]
    assert not (ci / "benchmark-pids.json").exists()


# --- дополнительные кейсы ---

def test_stop_skips_foreign_pids_and_missing_dir(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    killed = []
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: False)
    for target in (ci, tmp_path / "missing"):
        B.stop_code_index(target, run=lambda cmd, **k: None,
                          kill=lambda pid, sig: killed.append(pid),
                          sleep=lambda _s: None, clock=lambda: 0.0,
                          log=lambda _m: None)
    assert killed == []
    assert not (ci / "benchmark-pids.json").exists()


def test_clean_tolerates_missing_code_index_dir(tmp_path):
    catalog = tmp_path / "catalog"; (catalog / ".code-index").mkdir(parents=True)
    calls = []
    B.clean_code_index(tmp_path / "missing", catalog,
                       run=lambda cmd, **k: calls.append(cmd),
                       log=lambda _m: None)
    assert not (catalog / ".code-index").exists()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


def test_start_cleans_first_and_spawns_detached(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "old.txt").write_text("old", encoding="utf-8")
    catalog = tmp_path / "catalog"; catalog.mkdir()
    spawned = []
    pids = iter([1, 2])

    def fake_download(dest, *, log=None):
        path = Path(dest) / "bsl-indexer"
        path.write_text("bin", encoding="utf-8")
        return path

    def fake_popen(args, **kwargs):
        spawned.append((args, kwargs))
        return SimpleNamespace(pid=next(pids))

    monkeypatch.setattr(B, "_spawn_kwargs",
                        lambda: {"start_new_session": True})
    index = B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=fake_download, popen=fake_popen,
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""),
        log=lambda _m: None)
    assert not (ci / "old.txt").exists()
    assert spawned[0][0][1:] == ["daemon", "run"]
    assert spawned[1][0][1:3] == ["serve", "--transport"]
    assert all(kw.get("start_new_session") is True for _a, kw in spawned)
    pids_file = json.loads((ci / "benchmark-pids.json").read_text("utf-8"))
    assert pids_file == {"daemon": 1, "serve": 2}
    assert index == B.NativeIndex(ci, ci / "bsl-indexer", 1, 2)


def _ready_run(status, calls):
    def run(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(returncode=0, stdout=status, stderr="")
    return run


def _counting_clock():
    calls = {"n": 0}

    def clock():
        calls["n"] += 1
        return float(calls["n"])       # 1.0, 2.0, … — растущее время

    return clock


def test_wait_ready_returns_when_index_ready(monkeypatch):
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/p", "status": "ready"}]})
    calls = []
    B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                            run=_ready_run(status, calls),
                            sleep=lambda _s: None, clock=_counting_clock(),
                            tcp_ok=lambda _u: True,
                            log=lambda _m: None)
    assert calls == [[str(index.binary), "daemon", "status", "--json"]]


def test_wait_ready_raises_on_dead_process(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: False)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    with pytest.raises(SetupError):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run("", []), sleep=lambda _s: None,
                                clock=_counting_clock(), tcp_ok=lambda _u: True,
                                log=lambda _m: None)


def test_wait_ready_raises_on_timeout(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/p", "status": "indexing"}]})
    with pytest.raises(SetupError):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run(status, []),
                                sleep=lambda _s: None, clock=_counting_clock(),
                                tcp_ok=lambda _u: True,
                                log=lambda _m: None)


def test_module_does_not_import_bench_setup_at_import_time():
    import subprocess
    import sys
    src = str(Path(__file__).resolve().parents[3] / "src")
    code = ("import agentmon.env.code_index_bench, sys; "
            "sys.exit(int('bench_setup' in sys.modules))")
    result = subprocess.run([sys.executable, "-c", code],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, "PYTHONPATH": src})
    assert result.returncode == 0, result.stderr


def test_existing_binary_finds_downloaded(tmp_path):
    assert R.existing_binary(tmp_path) is None
    nested = tmp_path / "v1" / "bin"
    nested.mkdir(parents=True)
    binary = nested / "bsl-indexer"
    binary.write_text("bin", encoding="utf-8")
    assert R.existing_binary(tmp_path) == binary
