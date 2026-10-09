from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.mcp import McpRepo
from agentmon.store.projects import ProjectRepo


def test_mcp_crud_and_project_link(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    p = ProjectRepo(db)
    pid = p.add(name="demo", path="/p/demo")
    a = m.add(name="code-index", kind="standard", standard_key="code-index", port=8815)
    b = m.add(name="my", kind="custom", connection_json='{"url":"http://x"}')
    assert {x["name"] for x in m.list()} == {"code-index", "my"}
    m.set_for_project(pid, [a, b])
    assert {x["id"] for x in m.for_project(pid)} == {a, b}
    m.set_for_project(pid, [a])  # перезапись набора
    assert {x["id"] for x in m.for_project(pid)} == {a}


def test_mcp_get_and_by_name(tmp_path):
    """get() и by_name() возвращают правильную запись."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="srv", kind="custom", purpose="testing")
    row = m.get(mid)
    assert row["name"] == "srv"
    assert row["purpose"] == "testing"
    assert m.by_name("srv")["id"] == mid
    assert m.get(9999) is None
    assert m.by_name("ghost") is None


def test_mcp_update(tmp_path):
    """update() изменяет указанные поля."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="upd", kind="custom")
    m.update(mid, purpose="new purpose", port=9000)
    row = m.get(mid)
    assert row["purpose"] == "new purpose"
    assert row["port"] == 9000


def test_mcp_delete(tmp_path):
    """delete() удаляет запись; get() возвращает None."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="del_me", kind="custom")
    m.delete(mid)
    assert m.get(mid) is None


def test_mcp_add_defaults(tmp_path):
    """Необязательные поля получают дефолтные значения; created_at=None при now=None."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="defaults", kind="custom")
    row = m.get(mid)
    assert row["purpose"] == ""
    assert row["kind"] == "custom"
    assert row["standard_key"] is None
    assert row["connection_json"] is None
    assert row["port"] is None
    assert row["token_env"] is None
    assert row["created_at"] is None


def test_mcp_new_fields_mcp_name_url_catalog_dir(tmp_path):
    """add()/get() поддерживают поля mcp_name, url, catalog_dir."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="idx", kind="standard", standard_key="code-index",
                mcp_name="code_index", url="localhost",
                catalog_dir="/src/cfg", port=8004)
    row = m.get(mid)
    assert row["mcp_name"] == "code_index"
    assert row["url"] == "localhost"
    assert row["catalog_dir"] == "/src/cfg"


def test_mcp_db_name_field(tmp_path):
    """add()/get() и update() поддерживают поле db_name (метаданные 1С)."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="md", kind="extension", standard_key="1c-md",
                url="host1", db_name="my_base")
    row = m.get(mid)
    assert row["db_name"] == "my_base"
    m.update(mid, db_name="other_base")
    assert m.get(mid)["db_name"] == "other_base"


def test_mcp_platform_path_field(tmp_path):
    """add()/get() поддерживают поле platform_path."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="plat", kind="standard", standard_key="1c-platform",
                platform_path="/opt/1cv8/x86_64/8.3.27")
    assert m.get(mid)["platform_path"] == "/opt/1cv8/x86_64/8.3.27"


def test_mcp_new_fields_default_none(tmp_path):
    """Новые поля по умолчанию None."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    row = m.get(m.add(name="plain", kind="custom"))
    assert row["mcp_name"] is None
    assert row["url"] is None
    assert row["catalog_dir"] is None


def test_mcp_update_new_fields(tmp_path):
    """update() изменяет новые поля."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="u2", kind="standard")
    m.update(mid, mcp_name="bsl_ls", url="example", catalog_dir="/x")
    row = m.get(mid)
    assert row["mcp_name"] == "bsl_ls"
    assert row["url"] == "example"
    assert row["catalog_dir"] == "/x"


def test_mcp_set_for_project_empty(tmp_path):
    """set_for_project([]) очищает все связи проекта."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    p = ProjectRepo(db)
    pid = p.add(name="pr", path="/p/pr")
    mid = m.add(name="srvX", kind="custom")
    m.set_for_project(pid, [mid])
    assert len(m.for_project(pid)) == 1
    m.set_for_project(pid, [])
    assert m.for_project(pid) == []


def test_mcp_for_project_returns_full_rows(tmp_path):
    """for_project() возвращает полные строки из mcp_servers, не только id."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    p = ProjectRepo(db)
    pid = p.add(name="pr2", path="/p/pr2")
    mid = m.add(name="full_row", kind="standard", standard_key="sk", port=1234)
    m.set_for_project(pid, [mid])
    rows = m.for_project(pid)
    assert len(rows) == 1
    assert rows[0]["name"] == "full_row"
    assert rows[0]["port"] == 1234


def test_set_for_project_atomic_rollback(tmp_path):
    """Откат транзакции внутри transaction() восстанавливает прежний набор MCP."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    p = ProjectRepo(db)
    pid = p.add(name="d", path="/d")
    a = m.add(name="x", kind="custom")
    m.set_for_project(pid, [a])
    # эмулируем сбой посреди транзакции
    try:
        with db.transaction():
            db.execute("DELETE FROM project_mcp WHERE project_id=?", [pid])
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert {x["id"] for x in m.for_project(pid)} == {a}   # откат вернул прежний набор
