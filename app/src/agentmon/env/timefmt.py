"""Формат отметок времени в task.json: локальный ISO 8601 и разбор обратно.

task.json — человекочитаемый файл: даты пишутся строками вида
``2026-11-13T11:37:18+03:00`` (часовой пояс ОС пишущего процесса). БД и UI
продолжают работать с epoch-секундами, поэтому на границе файл→БД значения
разбираются обратно в число. Старые файлы с epoch-числами поддерживаются.
"""
from datetime import datetime


def to_local_iso(ts) -> str | None:
    """epoch-секунды → ISO 8601 в локальном поясе ОС. None → None."""
    if ts is None:
        return None
    return (datetime.fromtimestamp(float(ts))
            .astimezone()
            .isoformat(timespec="seconds"))


def parse_ts(value) -> float | None:
    """ISO-строка/число/числовая строка → epoch-секунды; мусор → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(
                text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return None
    return None
