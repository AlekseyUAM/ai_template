"""Атомарная запись и межпроцессная блокировка task.json.

task.json пишут два независимых процесса: инструмент оркестратора
(template/.claude/tools/task_status.py) и приложение (approve из UI/Telegram).
Обычный write_text — это truncate+write: читатель может увидеть обрезанный
JSON, а два read-modify-write затирают правки друг друга. Здесь:
- lock-файл `<task.json>.lock` (O_CREAT|O_EXCL) с ожиданием и снятием
  застарелого lock'а;
- запись во временный файл рядом + os.replace (атомарна в пределах ФС).
"""
import contextlib
import json
import os
import time
from pathlib import Path

LOCK_TIMEOUT = 5.0
STALE_LOCK_SECONDS = 30.0


@contextlib.contextmanager
def locked(path):
    """Держать межпроцессный lock для task.json (или любого файла)."""
    target = Path(path)
    lock = target.with_name(target.name + ".lock")
    deadline = time.monotonic() + LOCK_TIMEOUT
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
                if age > STALE_LOCK_SECONDS:
                    lock.unlink()          # писатель умер, не сняв lock
                    continue
            except OSError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"task.json занят: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock.unlink()
        except OSError:
            pass


def atomic_write_text(path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        # Windows: os.replace fails while a reader has the target open.
        for attempt in range(100):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(0.01)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def atomic_write_text_prov(prov, path: str, text: str) -> None:
    """Атомарная запись на машине проекта через provisioner (tmp + mv).

    Межпроцессный lock здесь не держится: для нелокальных бэкендов веб-правка
    происходит на гейте, когда оркестратор ждёт пользователя. Атомарного
    replace достаточно, чтобы читатель не увидел обрезанный JSON.
    """
    tmp = f"{path}.tmp"
    prov.write_text(tmp, text)
    result = prov.run(["mv", "-f", tmp, path])
    if getattr(result, "returncode", 1) != 0:
        raise OSError(
            f"не удалось заменить {path}: "
            f"{(getattr(result, 'stderr', '') or '').strip()}")


def update_json(path, mutator, *, prov=None):
    """Прочитать JSON под lock'ом, дать mutator(data), атомарно записать.

    mutator возвращает False — запись не нужна (например, этап не найден).
    Возвращает результат mutator. ``prov`` — provisioner нелокального
    проекта: тогда файл читается/пишется на машине проекта (без lock).
    """
    if prov is not None:
        target = str(path)
        if not prov.exists(target):
            return False
        try:
            data = json.loads(prov.read_text(target))
        except (ValueError, OSError):
            return False
        result = mutator(data)
        if result is not False:
            atomic_write_text_prov(
                prov, target,
                json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return result
    target = Path(path)
    with locked(target):
        data = json.loads(target.read_text(encoding="utf-8"))
        result = mutator(data)
        if result is not False:
            atomic_write_text(
                target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return result
