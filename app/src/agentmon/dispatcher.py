import logging
import time

logger = logging.getLogger(__name__)


class Dispatcher:
    """Подаёт задачи из очереди агентам, по одной на проект.

    Detached-модель: каждую задачу монитор запускает отдельным процессом
    (`claude -p "<текст задачи>"`). Завершение определяется авторитетно — по
    коду выхода прогона (`monitor.task_status`), а не эвристикой тишины.
    Параметры min_run_seconds/no_log_seconds оставлены для совместимости и не
    используются.
    """

    def __init__(self, registry, queue, monitor, min_run_seconds=5.0,
                 no_log_seconds=120.0, max_requeues=3, max_start_failures=3,
                 clock=time.time):
        self.registry = registry
        self.queue = queue
        self.monitor = monitor
        self.max_requeues = max_requeues
        self.max_start_failures = max_start_failures
        self.clock = clock
        self._requeues = {}        # task_id -> сколько раз возвращали в очередь
        self._start_failures = {}  # task_id -> сколько раз подряд не стартовал

    def tick(self) -> None:
        self.monitor.refresh()      # сверяет прогоны с реальными PID (reconcile)
        for project in self.registry.list():
            try:
                self._tick_project(project)
            except (OSError, RuntimeError, KeyError, ValueError) as exc:
                logger.warning("проект %s недоступен: %s", project.path, exc)
            except Exception:
                logger.exception("ошибка диспетчера на проекте %s", project.path)

    def _tick_project(self, project) -> None:
        running = self.queue.running_for(project.id)
        if running is not None:
            status = self.monitor.task_status(running.id)
            if status == "done":
                self.queue.mark_done(running.id)
                self._requeues.pop(running.id, None)
            elif status == "failed":
                # Прогон завершился неуспешно (ненулевой код или был убит).
                # Даём ограниченное число повторов — на случай обрыва, а не
                # детерминированной ошибки.
                count = self._requeues.get(running.id, 0)
                if count >= self.max_requeues:
                    self.queue.mark_failed(running.id)
                    logger.error("задача %d проекта %s провалена после %d попыток",
                                 running.id, project.path, count)
                    self._requeues.pop(running.id, None)
                else:
                    self.queue.requeue(running.id)
                    self._requeues[running.id] = count + 1
            # status in {"running", None} → прогон ещё идёт (или только что
            # создан) — ждём следующего тика.
            return

        nxt = self.queue.next(project.id)
        if nxt is None:
            return
        # Захватываем задачу ДО запуска агента: атомарный queued→running не даёт
        # второму диспетчеру забрать ту же задачу. Проигравший захват (False)
        # просто уходит — иначе два процесса агента на одну задачу.
        if not self.queue.mark_running(nxt.id, session_id=None):
            return
        try:
            self.monitor.start(project, nxt.text, task_id=nxt.id)
        except Exception as exc:
            # Агент не стартовал — возвращаем задачу в очередь, чтобы захват не
            # «съел» её навсегда, и учитываем неудачу старта.
            self.queue.requeue(nxt.id)
            self._note_start_failure(project, nxt, exc)
            raise
        self._start_failures.pop(nxt.id, None)

    def _note_start_failure(self, project, task, exc) -> None:
        failures = self._start_failures.get(task.id, 0) + 1
        if failures < self.max_start_failures:
            self._start_failures[task.id] = failures
            return
        self._start_failures.pop(task.id, None)
        self.queue.mark_failed(task.id)
        logger.error("задача %d проекта %s: агент не запустился %d раз подряд (%s), "
                     "помечена проваленной",
                     task.id, project.path, failures, exc)
