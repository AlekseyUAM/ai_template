"""Тесты формата дат task.json: локальная ISO-строка ↔ epoch-секунды."""
import re
from datetime import datetime, timedelta, timezone

from agentmon.env.timefmt import parse_ts, to_local_iso


def test_to_local_iso_none():
    assert to_local_iso(None) is None


def test_to_local_iso_has_offset_and_roundtrips():
    ts = 1794504190.2363446
    text = to_local_iso(ts)

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", text)

    expected_offset = datetime.fromtimestamp(ts).astimezone().utcoffset()
    parsed = datetime.fromisoformat(text)
    assert parsed.utcoffset() == expected_offset
    # Секундная точность: микросекунды отбрасываются.
    assert parse_ts(text) == \
        datetime.fromtimestamp(ts).replace(microsecond=0).timestamp()


def test_parse_ts_numbers():
    assert parse_ts(5) == 5.0
    assert parse_ts(5.5) == 5.5
    assert parse_ts("5.5") == 5.5


def test_parse_ts_iso_with_offsets_and_z():
    expected = datetime(2026, 11, 13, 11, 37, 18,
                        tzinfo=timezone(timedelta(hours=3))).timestamp()
    assert parse_ts("2026-11-13T11:37:18+03:00") == expected
    assert parse_ts("2026-11-13T08:37:18Z") == expected
    assert parse_ts("2026-11-13T08:37:18+00:00") == expected
    assert parse_ts("2026-11-13T08:37:18+0000") == expected


def test_parse_ts_garbage_is_none():
    assert parse_ts("не дата") is None
    assert parse_ts("") is None
    assert parse_ts("   ") is None
    assert parse_ts(None) is None
    assert parse_ts(True) is None
    assert parse_ts({}) is None
