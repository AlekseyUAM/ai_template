import sqlite3, sys
from pathlib import Path
from agentmon import run_wrapper
from agentmon.run_store import RunStore


def test_missing_binary_still_writes_exit(tmp_path):
    ef = tmp_path / "e"
    rc = run_wrapper.run(str(ef), ["definitely_no_such_binary_xyz_42"])
    assert ef.read_text().strip() != ""        # файл записан
    assert rc != 0


def test_runstore_with_raw_connection(tmp_path):
    conn = sqlite3.connect(":memory:")          # без row_factory
    store = RunStore(conn, clock=lambda: 1.0)
    rid = store.add(1, 123)
    assert store.get(rid)["pid"] == 123
    assert [r["id"] for r in store.running()] == [rid]
