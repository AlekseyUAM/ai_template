import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pytest собирает функции test_*, которые тестовый модуль импортировал из
# bench_metrics по имени (в т.ч. публичную test_cycle_metrics); исключаем.
_DROP = "benchmark/tests/test_bench_metrics.py::test_cycle_metrics"


def pytest_collection_finish(session):
    session.items[:] = [item for item in session.items if item.nodeid != _DROP]
