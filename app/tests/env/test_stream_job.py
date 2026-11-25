"""Тесты фонового задания с журналом в файле (stream_job.py)."""
import asyncio
import threading

from agentmon.env.stream_job import StreamJob


async def _collect(job):
    parts = []
    async for chunk in job.iter_log(poll=0.01):
        parts.append(chunk)
    return "".join(parts)


def _wait_done(job, timeout=5.0):
    assert job.done.wait(timeout), "задание не завершилось вовремя"


def test_job_writes_log_and_iter_log_returns_it(tmp_path):
    job = StreamJob(tmp_path / "logs" / "1-demo.log")

    def produce():
        yield "первая строка\n"
        yield "вторая строка\n"

    job.start(produce)
    _wait_done(job)

    assert asyncio.run(_collect(job)) == "первая строка\nвторая строка\n"
    assert job.log_path.read_text(encoding="utf-8").count("\n") == 2
    assert not job.failed


def test_abandoned_reader_does_not_stop_job(tmp_path):
    """Обрыв читателя (клиент закрыл вкладку) не прерывает фоновую работу."""
    job = StreamJob(tmp_path / "1-drop.log")
    gate = threading.Event()

    def produce():
        yield "start\n"
        gate.wait(5.0)
        yield "finish\n"

    job.start(produce)

    async def read_and_close():
        agen = job.iter_log(poll=0.01)
        first = await agen.__anext__()
        await agen.aclose()                         # клиент отвалился
        return first

    assert asyncio.run(read_and_close()) == "start\n"
    gate.set()
    _wait_done(job)
    assert job.log_path.read_text(encoding="utf-8") == "start\nfinish\n"


def test_job_records_unhandled_error(tmp_path):
    job = StreamJob(tmp_path / "err.log")

    def produce():
        yield "строка\n"
        raise RuntimeError("boom")

    job.start(produce)
    _wait_done(job)

    text = job.log_path.read_text(encoding="utf-8")
    assert "строка\n" in text
    assert "boom" in text
    assert job.failed


def test_iter_log_reads_from_beginning_after_completion(tmp_path):
    """Переподключение после завершения отдаёт журнал с начала."""
    job = StreamJob(tmp_path / "done.log")
    job.start(lambda: iter(["a\n", "b\n"]))
    _wait_done(job)

    assert asyncio.run(_collect(job)) == "a\nb\n"
    assert asyncio.run(_collect(job)) == "a\nb\n"   # повторно — тоже
