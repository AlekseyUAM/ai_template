import json
from agentmon.telegram.reports import chunk, enabled_stages, read_report, TG_LIMIT


def test_chunk_splits_on_limit():
    parts = chunk("a\n" * 5000, limit=100)
    assert all(len(p) <= 100 for p in parts)
    assert "".join(parts).replace("\n", "") == "a" * 5000


def test_chunk_short_text_single():
    assert chunk("короткий") == ["короткий"]


def test_enabled_stages_filters():
    task = {"stages_json": json.dumps([
        {"name": "analyze", "artifact": "ANALYZE.md", "enabled": True},
        {"name": "plan", "artifact": "ARCHITECT.md", "enabled": False},
    ])}
    names = [s["name"] for s in enabled_stages(task)]
    assert names == ["analyze"]


def test_read_report(tmp_path):
    folder = tmp_path / "tasks" / "task#001"
    folder.mkdir(parents=True)
    (folder / "ANALYZE.md").write_text("# Анализ\nтекст", encoding="utf-8")
    task = {"id": 1, "identifier": "001", "stages_json": json.dumps([
        {"name": "analyze", "artifact": "ANALYZE.md", "enabled": True}])}
    assert "Анализ" in read_report(str(tmp_path), task, "analyze")
    assert read_report(str(tmp_path), task, "review") is None  # нет артефакта
