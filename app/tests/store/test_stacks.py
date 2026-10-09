"""Тесты репозитория стеков (StackRepo)."""
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.stacks import StackRepo
from agentmon.store.tasks import TaskRepo


def _repos(tmp_path):
    """Вспомогательная фабрика: возвращает (StackRepo, TaskRepo) на общей БД."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    return StackRepo(db), TaskRepo(db)


def test_stack_crud(tmp_path):
    sr, _ = _repos(tmp_path)
    sid = sr.add(name="спринт-1")
    row = sr.get(sid)
    assert row is not None
    assert row["name"] == "спринт-1"
    assert row["status"] == "idle"
    assert [r["id"] for r in sr.list()] == [sid]
    sr.set_status(sid, "active")
    assert sr.get(sid)["status"] == "active"
    sr.delete(sid)
    assert sr.get(sid) is None


def test_stack_add_item_appends(tmp_path):
    """add_item без position добавляет в конец (позиция = текущий максимум + 1)."""
    sr, tr = _repos(tmp_path)
    sid = sr.add(name="стек")
    t1 = tr.add(project_id=1, name="задача-1")
    t2 = tr.add(project_id=1, name="задача-2")
    t3 = tr.add(project_id=1, name="задача-3")
    sr.add_item(sid, t1)
    sr.add_item(sid, t2)
    sr.add_item(sid, t3)
    ids = [row["task_id"] for row in sr.items(sid)]
    assert ids == [t1, t2, t3]


def test_stack_items_ordered_by_position(tmp_path):
    """items возвращает элементы, упорядоченные по position."""
    sr, tr = _repos(tmp_path)
    sid = sr.add(name="стек")
    t1 = tr.add(project_id=1, name="задача-1")
    t2 = tr.add(project_id=1, name="задача-2")
    # явно задаём нестандартный порядок позиций
    sr.add_item(sid, t2, position=0)
    sr.add_item(sid, t1, position=10)
    ids = [row["task_id"] for row in sr.items(sid)]
    assert ids == [t2, t1]


def test_stack_reorder(tmp_path):
    """reorder переставляет элементы согласно переданному списку task_id."""
    sr, tr = _repos(tmp_path)
    sid = sr.add(name="стек")
    t1 = tr.add(project_id=1, name="задача-1")
    t2 = tr.add(project_id=1, name="задача-2")
    t3 = tr.add(project_id=1, name="задача-3")
    sr.add_item(sid, t1)
    sr.add_item(sid, t2)
    sr.add_item(sid, t3)
    # меняем порядок на обратный
    sr.reorder(sid, [t3, t2, t1])
    ids = [row["task_id"] for row in sr.items(sid)]
    assert ids == [t3, t2, t1]


def test_stack_remove_item(tmp_path):
    """remove_item удаляет элемент стека по item_id."""
    sr, tr = _repos(tmp_path)
    sid = sr.add(name="стек")
    t1 = tr.add(project_id=1, name="задача-1")
    t2 = tr.add(project_id=1, name="задача-2")
    item1 = sr.add_item(sid, t1)
    sr.add_item(sid, t2)
    sr.remove_item(item1)
    ids = [row["task_id"] for row in sr.items(sid)]
    assert ids == [t2]


def test_stack_delete_removes_items(tmp_path):
    """delete() удаляет стек вместе со всеми его элементами из stack_items."""
    sr, tr = _repos(tmp_path)
    sid = sr.add(name="стек-удаление")
    t1 = tr.add(project_id=1, name="задача-A")
    t2 = tr.add(project_id=1, name="задача-B")
    sr.add_item(sid, t1)
    sr.add_item(sid, t2)
    assert len(sr.items(sid)) == 2
    sr.delete(sid)
    # стек удалён
    assert sr.get(sid) is None
    # элементы тоже удалены — items() вернёт пустой список (stack_id больше нет строк)
    assert sr.items(sid) == []
