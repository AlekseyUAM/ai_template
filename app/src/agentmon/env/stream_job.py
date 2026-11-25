"""Фоновое выполнение генератора с журналом в файле.

Зачем: создание проекта (сборка образа + установка окружения) идёт минутами.
Держать такую работу в HTTP-стриме нельзя — обрыв соединения клиента
(Firefox: «Error in input stream») останавливает вычитку генератора:
docker build повисает на полном pipe, откат стаба не выполняется.
Здесь работа идёт в отдельном потоке и пишет журнал в файл, а HTTP-стрим
лишь «хвостит» файл и может быть оборван/переподключён без последствий.
"""
import asyncio
import threading
from codecs import getincrementaldecoder
from pathlib import Path
from typing import Callable, Iterable


class StreamJob:
    """Фоновая задача с журналом в файле.

    ``produce`` — генератор строк; его исчерпание означает завершение задачи.
    Необработанная ошибка генератора пишется в журнал и помечает задачу failed.
    """

    def __init__(self, log_path):
        self.log_path = Path(log_path)
        self.done = threading.Event()
        self.failed = False
        self._thread: threading.Thread | None = None

    def start(self, produce: Callable[[], Iterable[str]]) -> "StreamJob":
        """Запустить produce в демон-потоке, журнал — с чистого файла."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        self._thread = threading.Thread(
            target=self._run, args=(produce,), daemon=True,
            name=f"stream-job-{self.log_path.stem}")
        self._thread.start()
        return self

    def _run(self, produce):
        try:
            for chunk in produce():
                self.append(chunk)
        except Exception as exc:                           # noqa: BLE001
            # Последняя линия обороны: produce обычно сам печатает ошибку.
            self.failed = True
            self.append(f"\n✗ Ошибка: {exc}\n")
        except BaseException:                              # GeneratorExit и др.
            # Аварийное прерывание задания (не обрыв стрима — стрим задачу
            # не владеет). В журнале должна остаться хотя бы отметка.
            self.failed = True
            self.append("\n✗ Задание прервано\n")
        finally:
            self.done.set()

    def append(self, text: str) -> None:
        """Дописать порцию журнала (сразу видна читателям файла)."""
        if not text:
            return
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(text)

    def _read_from(self, pos: int) -> bytes:
        with self.log_path.open("rb") as f:
            f.seek(pos)
            return f.read()

    async def iter_log(self, poll: float = 0.2):
        """Async-генератор журнала с начала файла до завершения задачи.

        Инкрементальный UTF-8 декодер — чтобы не рвать многобайтные символы
        на границах чтения. Async — чтобы при обрыве стрима Starlette отменял
        именно этот генератор, а не занимал поток пула на время сна.
        """
        decoder = getincrementaldecoder("utf-8")(errors="replace")
        pos = 0
        while True:
            chunk = self._read_from(pos)
            if chunk:
                pos += len(chunk)
                text = decoder.decode(chunk)
                if text:
                    yield text
                continue
            if self.done.is_set():
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail
                return
            await asyncio.sleep(poll)
