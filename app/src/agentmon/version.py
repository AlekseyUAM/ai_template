"""Отпечаток исходников пакета — чтобы заметить, что процесс работает на коде,
которого на диске уже нет.

Питоновские модули читаются один раз, при импорте. Если файлы потом изменить,
работающий процесс продолжит исполнять старое — и никакого внешнего признака
этого нет. Поэтому отпечаток считается дважды: один раз при импорте (он отражает
загруженный код) и по требованию с диска (он отражает код сейчас). Расхождение
означает ровно одно: нужен перезапуск.

В отпечаток входят только .py пакета. Файлы web/ сюда не относятся: они отдаются
с диска на каждый запрос и перезапуска не требуют, так что их учёт давал бы
ложные тревоги.
"""

import hashlib
import time
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def source_fingerprint(root=None) -> str:
    """Хеш всех .py каталога: путь и содержимое, в устойчивом порядке."""
    root = Path(root) if root is not None else PACKAGE_DIR
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            # Нечитаемый файл — тоже изменение состояния, а не повод падать.
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


# Считаются один раз, при импорте пакета: это снимок того, что реально загружено
# в текущий процесс.
LOADED_FINGERPRINT = source_fingerprint()
STARTED_AT = time.time()


def status(now_fn=time.time) -> dict:
    """Сравнить загруженный код с тем, что лежит на диске сейчас."""
    disk = source_fingerprint()
    return {
        "loaded": LOADED_FINGERPRINT,
        "disk": disk,
        "stale": disk != LOADED_FINGERPRINT,
        "started_at": STARTED_AT,
        "uptime_seconds": max(0.0, now_fn() - STARTED_AT),
    }
