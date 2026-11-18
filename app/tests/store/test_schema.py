from agentmon.store.db import connect
from agentmon.store.schema import init_schema

TABLES = {"projects", "mcp_servers", "project_mcp", "tasks",
          "stacks", "stack_items", "runs"}


def test_init_creates_tables_idempotent(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    init_schema(db)   # повторный вызов не падает
    rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    names = {r["name"] for r in rows}
    assert TABLES <= names


def test_init_migrates_python3_in_stdio_bridge(tmp_path, monkeypatch):
    """Старые карточки 1c_platform звали python3 — на Windows это заглушка."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    db.execute(
        "INSERT INTO mcp_servers (name, kind, standard_key, connection_json) "
        "VALUES (?, ?, ?, ?)",
        ["card", "docker", "1c-platform",
         '"1c_platform": {"type": "stdio", "command": "python3", '
         '"args": [".claude/mcp/sse_stdio_bridge.py", '
         '"http://localhost:8002/sse"]}'])
    monkeypatch.setattr("agentmon.store.schema.PYTHON_CMD", "python")

    init_schema(db)

    row = db.query("SELECT connection_json FROM mcp_servers WHERE name=?",
                   ["card"])[0]
    assert '"command": "python"' in row["connection_json"]
    assert '"command": "python3"' not in row["connection_json"]
