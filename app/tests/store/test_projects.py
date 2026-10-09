from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo


def repo(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    return ProjectRepo(db)


def test_project_crud(tmp_path):
    r = repo(tmp_path)
    pid = r.add(name="demo", path="/p/demo", email="i@e.ru", env_version="1.0.0")
    assert r.get(pid)["name"] == "demo"
    assert r.by_name("demo")["id"] == pid
    r.update(pid, email="x@e.ru")
    assert r.get(pid)["email"] == "x@e.ru"
    assert [p["id"] for p in r.list()] == [pid]
    r.delete(pid)
    assert r.get(pid) is None


def test_project_add_defaults(tmp_path):
    """Проверяем, что необязательные поля получают дефолтные значения."""
    r = repo(tmp_path)
    pid = r.add(name="minimal", path="/p/minimal")
    row = r.get(pid)
    assert row["identifier"] == ""
    assert row["email"] == ""
    assert row["db_kind"] == "file"
    assert row["env_version"] == ""
    assert row["created_at"] is None  # now=None → не ставим время


def test_project_list_multiple(tmp_path):
    """list() возвращает все записи."""
    r = repo(tmp_path)
    ids = [r.add(name=f"p{i}", path=f"/p/{i}") for i in range(3)]
    listed = [p["id"] for p in r.list()]
    assert set(listed) == set(ids)


def test_project_update_multiple_fields(tmp_path):
    """update() с несколькими полями меняет все сразу."""
    r = repo(tmp_path)
    pid = r.add(name="multi", path="/p/multi")
    r.update(pid, email="a@b.com", platform_version="3.2.1")
    row = r.get(pid)
    assert row["email"] == "a@b.com"
    assert row["platform_version"] == "3.2.1"


def test_project_by_name_missing(tmp_path):
    """by_name() возвращает None для несуществующего имени."""
    r = repo(tmp_path)
    assert r.by_name("nope") is None


def test_project_get_missing(tmp_path):
    """get() возвращает None для несуществующего id."""
    r = repo(tmp_path)
    assert r.get(9999) is None
