import asyncio
import contextlib
import logging

import uvicorn
from starlette.concurrency import run_in_threadpool

from . import config
from .api import create_app
from .backends.factory import BackendRegistry
from .dispatcher import Dispatcher
from .monitor import Monitor
from .queue import TaskQueue
from .registry import ProjectRegistry, open_db
from .run_store import RunStore
from .store.db import connect
from .store.schema import init_schema
from .env.stack_dispatcher import StackDispatcher
from .telegram.runtime import build_bot

logger = logging.getLogger(__name__)


def build(db_path=None):
    db = open_db(db_path or config.DB_PATH)
    registry = ProjectRegistry(db)
    queue = TaskQueue(db)
    store = RunStore(db)
    backends = BackendRegistry(config.CLAUDE_CMD)
    monitor = Monitor(registry, backends, store=store)

    # Detached-агенты переживают перезапуск монитора: их прогоны лежат в БД,
    # а процессы монитору не принадлежат. Поэтому running-задачи НЕ возвращаем
    # вслепую — вместо этого сводим прогоны с реальными PID (reconcile): те, что
    # завершились, пока монитор был выключен, осядут done/failed, а диспетчер
    # разберётся с ними по task_status на ближайшем тике.
    monitor.reconcile()

    dispatcher = Dispatcher(registry=registry, queue=queue, monitor=monitor)

    app_store = connect(config.DSN)
    init_schema(app_store)
    stack_dispatcher = StackDispatcher(app_store, monitor)
    tg = build_bot(app_store, app_store, registry)
    tg_client = tg[0] if tg else None
    tg_bot = tg[1] if tg else None
    tg_notifier = tg[2] if tg else None
    tg_stop = asyncio.Event()

    async def dispatch_loop():
        # Последний отказ: полный traceback пишем один раз на каждый новый
        # вид ошибки, дальше — одну строку. Иначе устойчивый отказ раз в
        # DISPATCH_INTERVAL даёт десятки тысяч трейсбеков в сутки и хоронит
        # под собой всё остальное ровно тогда, когда в лог идут смотреть.
        last_error = None
        repeats = 0
        stack_last_error = None
        stack_repeats = 0
        notifier_last_error = None
        notifier_repeats = 0
        while True:
            try:
                # tick блокирующий: refresh идёт на бэкенды, а первый контакт
                # по SSH — это connect с таймаутом 10 секунд и обход SFTP.
                # На событийном цикле это подвесило бы все HTTP-ручки и
                # WebSocket'ы на всё время недоступности хоста.
                await run_in_threadpool(dispatcher.tick)
                last_error = None
                repeats = 0
            except Exception as exc:
                signature = (type(exc), str(exc))
                if signature != last_error:
                    logger.exception("тик диспетчера не удался")
                    last_error, repeats = signature, 1
                else:
                    repeats += 1
                    logger.warning("тик диспетчера не удался снова (%d-й раз): %s",
                                   repeats, exc)
            try:
                await run_in_threadpool(stack_dispatcher.tick)
                stack_last_error = None
                stack_repeats = 0
            except Exception as exc:
                signature = (type(exc), str(exc))
                if signature != stack_last_error:
                    logger.exception("тик стек-раннера не удался")
                    stack_last_error, stack_repeats = signature, 1
                else:
                    stack_repeats += 1
                    logger.warning("тик стек-раннера не удался снова (%d-й раз): %s",
                                   stack_repeats, exc)
            if tg_notifier is not None:
                try:
                    await tg_notifier.tick()
                    notifier_last_error = None
                    notifier_repeats = 0
                except Exception as exc:
                    signature = (type(exc), str(exc))
                    if signature != notifier_last_error:
                        logger.exception("тик Telegram-нотификатора не удался")
                        notifier_last_error, notifier_repeats = signature, 1
                    else:
                        notifier_repeats += 1
                        logger.warning("тик Telegram-нотификатора не удался снова (%d-й раз): %s",
                                       notifier_repeats, exc)
            await asyncio.sleep(config.DISPATCH_INTERVAL)

    @contextlib.asynccontextmanager
    async def lifespan(application):
        task = asyncio.create_task(dispatch_loop())
        bot_task = asyncio.create_task(tg_bot.run(tg_stop)) if tg_bot else None
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            tg_stop.set()
            if bot_task:
                bot_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await bot_task
            if tg_client:
                await tg_client.aclose()
            monitor.shutdown()

    return create_app(registry=registry, queue=queue, monitor=monitor,
                      lifespan=lifespan, store=app_store)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(build(), host=config.HOST, port=config.PORT)
