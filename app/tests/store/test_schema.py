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
