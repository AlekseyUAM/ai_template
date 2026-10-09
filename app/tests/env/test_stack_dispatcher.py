"""Тесты стек-раннера StackDispatcher.

Покрывает:
- первый тик запускает первую задачу стека (monitor.start вызван с prompt+task_id);
- project-lock: пока первая задача alive, вторая НЕ запускается;
- после завершения первой задачи — вторая стартует;
- задача вида kind='test' → monitor.start вызван с cmd, содержащим 'time.sleep'.
"""
import sys
from types import SimpleNamespace

from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.env.stack_dispatcher import StackDispatcher


# ─── фейковый монитор ─────────────────────────────────────────────────────────

class FakeMonitor:
    """Двойник Monitor для изоляции StackDispatcher от реального процесса."""

    def __init__(self):
        # список вызовов start: [(project_id, cmd_or_prompt, task_id), ...]
        self.started: list[tuple] = []
        # множество project_id, у которых есть «живой» прогон
        self._alive: set = set()
        # map task_id → статус прогона (None = не стартовал)
        self._task_status: dict = {}
        # map task_id → project_id (чтобы снять alive при таймауте)
        self._task_project: dict = {}
        # task_id, которые при проверке должны считаться превысившими таймаут
        self._timed_out: set = set()
        # аргументы enforce_timeout: [(task_id, max_minutes), ...]
        self.timeout_calls: list[tuple] = []

    def start(self, project, prompt="", task_id=None, cmd=None):
        """Фиксируем вызов; помечаем проект живым и задачу как running."""
        payload = cmd if cmd is not None else prompt
        self.started.append((project.id, payload, task_id))
        self._alive.add(project.id)
        self._task_status[task_id] = "running"
        self._task_project[task_id] = project.id

    def is_alive(self, project) -> bool:
        return project.id in self._alive

    def task_status(self, task_id) -> str | None:
        return self._task_status.get(task_id)

    def enforce_timeout(self, task_id, max_minutes) -> bool:
        """Двойник: если задачу пометили force_timeout — снимаем прогон."""
        self.timeout_calls.append((task_id, max_minutes))
        if task_id in self._timed_out:
            self._task_status[task_id] = "failed"
            self._alive.discard(self._task_project.get(task_id))
            return True
        return False

    # вспомогательные методы для управления состоянием из тестов

    def set_task_status(self, task_id, status: str):
        self._task_status[task_id] = status

    def clear_alive(self, project_id):
        self._alive.discard(project_id)

    def force_timeout(self, task_id):
        self._timed_out.add(task_id)


# ─── фабрика стора ────────────────────────────────────────────────────────────

def _seed(tmp_path):
    """Создаёт БД, засевает проект, две задачи и running-стек с обеими задачами."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)

    pr = ProjectRepo(db)
    tr = TaskRepo(db)
    sr = StackRepo(db)

    proj_id = pr.add(name="proj-alpha", path=str(tmp_path / "proj"))
    t1_id = tr.add(project_id=proj_id, name="задача-1", kind="real")
    t2_id = tr.add(project_id=proj_id, name="задача-2", kind="real")
    stack_id = sr.add(name="стек-А")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, t1_id)   # position 0
    sr.add_item(stack_id, t2_id)   # position 1

    return db, proj_id, t1_id, t2_id, stack_id


# ─── тесты ────────────────────────────────────────────────────────────────────

def test_first_tick_starts_task1(tmp_path):
    """Первый тик: стартует первая задача стека; статус задачи → running."""
    db, proj_id, t1_id, t2_id, stack_id = _seed(tmp_path)
    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    disp.tick()

    # monitor.start вызван ровно один раз
    assert len(mon.started) == 1, f"ожидали 1 вызов start, получили {len(mon.started)}"
    pid, payload, tid = mon.started[0]
    assert pid == proj_id
    assert tid == t1_id
    # payload — строка-промпт (kind=real)
    assert isinstance(payload, str), "для real-задачи ожидается строка промпта"
    assert str(t1_id) in str(payload), "промпт должен содержать task_id"

    # статус задачи обновлён
    tr = TaskRepo(db)
    assert tr.get(t1_id)["status"] == "running"


def test_second_tick_project_locked(tmp_path):
    """Второй тик: project-lock — task2 НЕ запускается, пока task1 alive."""
    db, proj_id, t1_id, t2_id, stack_id = _seed(tmp_path)
    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    disp.tick()   # запускает task1
    disp.tick()   # project занят — task2 не стартует

    # start вызван только один раз суммарно
    assert len(mon.started) == 1, (
        f"project-lock нарушен: start вызван {len(mon.started)} раз(а)"
    )


def test_after_task1_done_starts_task2(tmp_path):
    """После завершения task1 и снятия alive — следующий тик запускает task2."""
    db, proj_id, t1_id, t2_id, stack_id = _seed(tmp_path)
    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    # тик 1: task1 стартует
    disp.tick()

    # имитируем завершение task1
    mon.set_task_status(t1_id, "done")
    mon.clear_alive(proj_id)

    # тик 2: task1 помечается done, task2 стартует
    disp.tick()

    tr = TaskRepo(db)
    assert tr.get(t1_id)["status"] == "done", "task1 должна быть помечена done"

    # start вызван для task2
    assert len(mon.started) == 2, (
        f"ожидали 2 вызова start (task1 + task2), получили {len(mon.started)}"
    )
    pid2, payload2, tid2 = mon.started[1]
    assert tid2 == t2_id


def test_tick_advances_past_done_tasks_no_recursion(tmp_path):
    """Тик со стеком из нескольких уже выполненных задач + одна planned:
    StackDispatcher запускает planned-задачу без RecursionError;
    monitor.start вызван ровно один раз для planned-задачи.
    """
    db = connect(str(tmp_path / "rec.db"))
    init_schema(db)

    pr = ProjectRepo(db)
    tr = TaskRepo(db)
    sr = StackRepo(db)

    proj_id = pr.add(name="proj-loop", path=str(tmp_path / "proj-loop"))

    # Несколько уже завершённых задач
    done_ids = []
    for i in range(5):
        tid = tr.add(project_id=proj_id, name=f"done-task-{i}", kind="real")
        tr.set_status(tid, "done")
        done_ids.append(tid)

    # Одна planned-задача в конце
    planned_id = tr.add(project_id=proj_id, name="planned-task", kind="real")

    stack_id = sr.add(name="стек-рекурсия")
    sr.set_status(stack_id, "running")
    for tid in done_ids:
        sr.add_item(stack_id, tid)
    sr.add_item(stack_id, planned_id)

    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    # Не должно быть RecursionError
    disp.tick()

    # monitor.start вызван ровно один раз — для planned-задачи
    assert len(mon.started) == 1, (
        f"ожидали 1 вызов start, получили {len(mon.started)}"
    )
    _, _, tid_started = mon.started[0]
    assert tid_started == planned_id, (
        f"ожидали запуск planned-задачи id={planned_id}, запустили id={tid_started}"
    )


def test_running_task_timeout_marks_failed_and_advances(tmp_path):
    """Задача, превысившая max_minutes, снимается по таймауту → failed,
    а стек переходит к следующей задаче."""
    db, proj_id, t1_id, t2_id, stack_id = _seed(tmp_path)
    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    disp.tick()                       # тик 1: стартует task1 (running)
    assert mon.task_status(t1_id) == "running"

    # task1 «висит» дольше лимита
    mon.force_timeout(t1_id)
    disp.tick()                       # тик 2: таймаут task1 → failed, старт task2

    tr = TaskRepo(db)
    assert tr.get(t1_id)["status"] == "failed", "task1 должна быть помечена failed по таймауту"
    # enforce_timeout вызван с max_minutes задачи (дефолт 60)
    assert (t1_id, 60) in mon.timeout_calls
    # после снятия task1 стартовала task2
    assert len(mon.started) == 2
    assert mon.started[1][2] == t2_id


def test_running_task_within_limit_not_killed(tmp_path):
    """Пока задача в пределах лимита — enforce_timeout не снимает её."""
    db, proj_id, t1_id, t2_id, stack_id = _seed(tmp_path)
    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    disp.tick()                       # старт task1
    disp.tick()                       # ещё running, таймаут не наступил

    tr = TaskRepo(db)
    assert tr.get(t1_id)["status"] == "running"
    # enforce_timeout всё же проверялся
    assert any(c[0] == t1_id for c in mon.timeout_calls)
    # task2 не стартовала (project-lock держит живой task1)
    assert len(mon.started) == 1


def test_test_kind_task_uses_cmd(tmp_path):
    """Задача kind='test' → monitor.start получает cmd-список с time.sleep."""
    db = connect(str(tmp_path / "t2.db"))
    init_schema(db)

    pr = ProjectRepo(db)
    tr = TaskRepo(db)
    sr = StackRepo(db)

    proj_id = pr.add(name="proj-test", path=str(tmp_path / "proj2"))
    t_id = tr.add(project_id=proj_id, name="тест-задача", kind="test")
    stack_id = sr.add(name="стек-тест")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, t_id)

    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    disp.tick()

    assert len(mon.started) == 1
    _, payload, tid = mon.started[0]
    assert tid == t_id
    # payload — список (cmd), а не строка
    assert isinstance(payload, list), f"для test-задачи ожидается cmd-список, получили {type(payload)}"
    # команда содержит time.sleep
    cmd_str = " ".join(str(x) for x in payload)
    assert "time.sleep" in cmd_str, f"cmd должен содержать time.sleep, получили: {payload}"
    # используется sys.executable
    assert payload[0] == sys.executable, f"первый элемент cmd должен быть {sys.executable}"


def test_test_kind_task_full_lifecycle(tmp_path):
    """Полный жизненный цикл тест-заглушки: planned→running→done, стек→idle.

    Тик 1: задача planned → запускается (monitor.start), статус → running.
    Тик 2: monitor.task_status возвращает 'done' → задача помечается done,
            стек становится idle (все задачи завершены).
    """
    db = connect(str(tmp_path / "lifecycle.db"))
    init_schema(db)

    pr = ProjectRepo(db)
    tr = TaskRepo(db)
    sr = StackRepo(db)

    proj_id = pr.add(name="proj-lifecycle", path=str(tmp_path / "proj-lifecycle"))
    t_id = tr.add(project_id=proj_id, name="тест-заглушка", kind="test")
    stack_id = sr.add(name="стек-lifecycle")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, t_id)

    mon = FakeMonitor()
    disp = StackDispatcher(db, mon)

    # --- Тик 1: задача planned → запускается, статус running ---
    disp.tick()

    assert tr.get(t_id)["status"] == "running", "после тик-1 задача должна быть running"
    assert len(mon.started) == 1, "monitor.start должен быть вызван один раз"
    _, payload, started_tid = mon.started[0]
    assert started_tid == t_id
    assert isinstance(payload, list), "для test-задачи ожидается cmd-список"
    # стек ещё running — задача не завершена
    assert sr.get(stack_id)["status"] == "running", "стек должен оставаться running после тик-1"

    # --- Имитируем завершение процесса ---
    mon.set_task_status(t_id, "done")
    mon.clear_alive(proj_id)

    # --- Тик 2: задача running → done, стек → idle ---
    disp.tick()

    assert tr.get(t_id)["status"] == "done", "после тик-2 задача должна быть done"
    assert sr.get(stack_id)["status"] == "idle", (
        f"после тик-2 стек должен быть idle, получен: {sr.get(stack_id)['status']}"
    )
