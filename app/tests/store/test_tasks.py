"""Тесты репозитория задач (TaskRepo)."""
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.tasks import TaskRepo


def _repo(tmp_path):
    """Вспомогательная фабрика: создаёт БД, схему и репозиторий задач."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    return TaskRepo(db)


def test_task_add_get(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="первая задача", goal="выполнить")
    row = r.get(tid)
    assert row is not None
    assert row["name"] == "первая задача"
    assert row["goal"] == "выполнить"
    assert row["status"] == "planned"
    assert row["project_id"] == 1


def test_task_mark_changes_default_and_explicit(tmp_path):
    r = _repo(tmp_path)
    # по умолчанию флаг выключен
    t_default = r.add(project_id=1, name="без маркеров")
    assert r.get(t_default)["mark_changes"] == 0
    # явное включение сохраняется как 1
    t_on = r.add(project_id=1, name="с маркерами", mark_changes=1)
    assert r.get(t_on)["mark_changes"] == 1


def test_task_list_all_and_by_project(tmp_path):
    r = _repo(tmp_path)
    t1 = r.add(project_id=1, name="задача-1")
    t2 = r.add(project_id=2, name="задача-2")
    t3 = r.add(project_id=1, name="задача-3")
    # список всех
    all_ids = [row["id"] for row in r.list()]
    assert set(all_ids) == {t1, t2, t3}
    # фильтр по проекту
    proj1_ids = [row["id"] for row in r.list(project_id=1)]
    assert set(proj1_ids) == {t1, t3}
    proj2_ids = [row["id"] for row in r.list(project_id=2)]
    assert set(proj2_ids) == {t2}


def test_task_update(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="задача")
    r.update(tid, goal="новая цель", plan="план")
    row = r.get(tid)
    assert row["goal"] == "новая цель"
    assert row["plan"] == "план"
    assert row["name"] == "задача"  # неизменённое поле сохраняется


def test_task_set_status(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="задача")
    r.set_status(tid, "running", stage="step-1")
    row = r.get(tid)
    assert row["status"] == "running"
    assert row["stage"] == "step-1"
    # без stage — stage не затрагивается
    r.set_status(tid, "done")
    row = r.get(tid)
    assert row["status"] == "done"
    assert row["stage"] == "step-1"


def test_task_delete(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="задача на удаление")
    r.delete(tid)
    assert r.get(tid) is None


def test_task_kind_test_persists(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="тест-задача", kind="test")
    row = r.get(tid)
    assert row is not None
    assert row["kind"] == "test"


def test_task_kind_default_is_real(tmp_path):
    r = _repo(tmp_path)
    tid = r.add(project_id=1, name="обычная задача")
    row = r.get(tid)
    assert row is not None
    assert row["kind"] == "real"
