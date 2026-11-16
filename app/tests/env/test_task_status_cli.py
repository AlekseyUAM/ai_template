import importlib.util
import json
from datetime import datetime
from pathlib import Path
import pytest
from agentmon.env import task_schema as ts

CLI = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools" / "task_status.py"


def _load():
    spec = importlib.util.spec_from_file_location("task_status", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso_dt(value: str) -> datetime:
    """Разбор ISO-даты из task.json для сравнений в тестах."""
    return datetime.fromisoformat(value)


def _task(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=ts.STAGE_NAMES)
    return ts.task_dir(tmp_path, s.id)


def test_cli_sets_status_and_files(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done", "--files", "Module.bsl", "Form.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "done"
    assert dev["changed_files"] == ["Module.bsl", "Form.bsl"]


def test_cli_unknown_stage_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    with pytest.raises(SystemExit):
        mod.main([str(d), "nope", "done"])


def _one_stage_task(tmp_path):
    """Задача с единственным включённым этапом develop и верхнеуровневым status."""
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    data["status"] = "planned"
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return d


def test_cli_rolls_up_overall_status_to_done(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done", "--files", "Module.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "done"


def test_cli_rolls_up_overall_status_running(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "running"


def test_cli_rolls_up_overall_status_failed(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "failed"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "failed"


def test_cli_sets_started_and_finished_at(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    running = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(running["started_at"], str)
    assert _iso_dt(running["started_at"]).tzinfo is not None
    assert running.get("finished_at") is None

    mod.main([str(d), "develop", "done"])
    done = json.loads((d / "task.json").read_text(encoding="utf-8"))
    # started_at не перезаписывается, finished_at проставляется и не раньше старта
    assert done["started_at"] == running["started_at"]
    assert isinstance(done["finished_at"], str)
    assert _iso_dt(done["finished_at"]) >= _iso_dt(done["started_at"])


def test_cli_clears_finished_at_when_reopened(tmp_path):
    """Цикл review→develop: задача снова не терминальна — finished_at снимается."""
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    assert json.loads((d / "task.json").read_text(encoding="utf-8"))["finished_at"]
    mod.main([str(d), "develop", "pending"])
    reopened = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert reopened["status"] == "planned"
    assert reopened["finished_at"] is None


def test_stage_has_timing_and_iteration_defaults(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(x for x in data["stages"] if x["name"] == "develop")
    assert dev["started_at"] is None
    assert dev["finished_at"] is None
    assert dev["iteration"] == 1


def test_stage_roundtrip_with_new_fields(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    reloaded = ts.load_task(d)          # from_dict(Stage(**s)) не должен падать
    assert reloaded.stages[0].iteration == 1


def test_cli_stamps_stage_timing(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(dev["started_at"], str)
    assert dev["finished_at"] is None
    assert dev["iteration"] == 1
    mod.main([str(d), "develop", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(dev["finished_at"], str)
    assert _iso_dt(dev["finished_at"]) >= _iso_dt(dev["started_at"])


def test_cli_rerun_increments_iteration(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "running"])   # повторный прогон в цикле
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["iteration"] == 2
    assert dev["finished_at"] is None          # сброшен до нового завершения


def _stage(data, name):
    return next(s for s in data["stages"] if s["name"] == name)


def test_cli_runs_first_running_done(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")), "develop")
    assert len(dev["runs"]) == 1
    assert dev["runs"][0]["iteration"] == 1
    assert dev["runs"][0]["finished_at"] is None
    assert _iso_dt(dev["runs"][0]["started_at"]).tzinfo is not None

    mod.main([str(d), "develop", "done"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")), "develop")
    assert len(dev["runs"]) == 1
    assert _iso_dt(dev["runs"][0]["finished_at"]) >= _iso_dt(dev["runs"][0]["started_at"])


def test_cli_runs_repeat_running_done(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")), "develop")
    assert [r["iteration"] for r in dev["runs"]] == [1, 2]
    assert all(r["finished_at"] is not None for r in dev["runs"])
    assert dev["iteration"] == 2


def test_cli_running_twice_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    with pytest.raises(SystemExit, match="restart"):
        mod.main([str(d), "develop", "running"])


def test_cli_done_without_running_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    with pytest.raises(SystemExit, match="running"):
        mod.main([str(d), "develop", "done"])


def test_cli_restart_closes_open_run_and_increments(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["status"] == "running"
    assert dev["iteration"] == 2
    assert len(dev["runs"]) == 2
    assert dev["runs"][0]["finished_at"] is not None
    assert dev["runs"][1]["iteration"] == 2
    assert dev["runs"][1]["finished_at"] is None


def test_cli_restart_from_done_starts_new_iteration(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["status"] == "running"
    assert dev["iteration"] == 2
    assert all(r["finished_at"] is not None for r in dev["runs"][:-1])
    assert dev["runs"][-1]["finished_at"] is None


def test_cli_restart_first_run_is_iteration_one(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "restart"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["iteration"] == 1
    assert dev["runs"][0]["iteration"] == 1
    assert dev["runs"][0]["finished_at"] is None


def _testing_done_task(tmp_path, review_done=False):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=ts.STAGE_NAMES)
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    _stage(data, "testing")["status"] = "done"
    _stage(data, "develop")["status"] = "done"
    if review_done:
        _stage(data, "review")["status"] = "done"
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return d


def test_cli_archives_testing_verdict_on_develop_pending(tmp_path):
    mod = _load()
    d = _testing_done_task(tmp_path)
    (d / "TESTING.md").write_text("# Вердикт\n", encoding="utf-8")
    mod.main([str(d), "develop", "pending"])
    assert not (d / "TESTING.md").exists()
    assert (d / "TESTING.1.md").read_text(encoding="utf-8") == "# Вердикт\n"
    assert _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                  "develop")["status"] == "pending"


def test_cli_keeps_testing_verdict_when_testing_not_done(tmp_path):
    """Падение загрузки: testing не done — вердикта нет, TESTING.md не трогаем."""
    mod = _load()
    d = _testing_done_task(tmp_path)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    _stage(data, "testing")["status"] = "pending"
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    (d / "TESTING.md").write_text("# Вердикт\n", encoding="utf-8")
    mod.main([str(d), "develop", "pending"])
    assert (d / "TESTING.md").exists()
    assert not (d / "TESTING.1.md").exists()


def test_cli_archive_conflict_leaves_everything_untouched(tmp_path):
    mod = _load()
    d = _testing_done_task(tmp_path)
    (d / "TESTING.md").write_text("новый\n", encoding="utf-8")
    (d / "TESTING.1.md").write_text("старый\n", encoding="utf-8")
    before = (d / "task.json").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="TESTING.1.md"):
        mod.main([str(d), "develop", "pending"])
    assert (d / "TESTING.md").read_text(encoding="utf-8") == "новый\n"
    assert (d / "TESTING.1.md").read_text(encoding="utf-8") == "старый\n"
    assert (d / "task.json").read_text(encoding="utf-8") == before


def test_cli_archive_conflict_does_not_rename_other_verdict(tmp_path):
    """Конфликт по TESTING.1.md не должен оставить полуархив (REVIEW переименован)."""
    mod = _load()
    d = _testing_done_task(tmp_path, review_done=True)
    (d / "TESTING.md").write_text("новый\n", encoding="utf-8")
    (d / "TESTING.1.md").write_text("старый\n", encoding="utf-8")
    (d / "REVIEW.md").write_text("# Итоговый вердикт\n", encoding="utf-8")
    before = (d / "task.json").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main([str(d), "develop", "pending"])
    assert (d / "REVIEW.md").exists()
    assert not (d / "REVIEW.1.md").exists()
    assert (d / "task.json").read_text(encoding="utf-8") == before


def test_cli_archives_review_verdict_on_develop_pending(tmp_path):
    mod = _load()
    d = _testing_done_task(tmp_path, review_done=True)
    (d / "REVIEW.md").write_text("# Итоговый вердикт\n", encoding="utf-8")
    mod.main([str(d), "develop", "pending"])
    assert not (d / "REVIEW.md").exists()
    assert (d / "REVIEW.1.md").exists()


def test_cli_db_update_start_and_done(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "db-update", "start"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(data["db_update"]["started_at"], str)
    assert data["db_update"]["finished_at"] is None
    mod.main([str(d), "db-update", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(data["db_update"]["finished_at"], str)
    assert _iso_dt(data["db_update"]["finished_at"]) >= \
        _iso_dt(data["db_update"]["started_at"])


def _task_with_update_db(tmp_path):
    """Задача с update_db=true — загрузка в ИБ обязательна для develop done."""
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    data["update_db"] = True
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return d


def test_cli_develop_done_blocked_without_db_update(tmp_path):
    """Падение/отсутствие загрузки не должно давать статус «готово»."""
    mod = _load()
    d = _task_with_update_db(tmp_path)
    mod.main([str(d), "develop", "running"])
    with pytest.raises(SystemExit) as exc:
        mod.main([str(d), "develop", "done", "--files", "Module.bsl"])
    assert "db-update" in str(exc.value)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "running"          # этап не закрыт
    assert data["status"] == "running"         # задача не стала done


def test_cli_develop_done_allowed_after_db_update_done(tmp_path):
    mod = _load()
    d = _task_with_update_db(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "db-update", "start"])
    mod.main([str(d), "db-update", "done"])
    mod.main([str(d), "develop", "done", "--files", "Module.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "done"
    assert data["status"] == "done"


def test_cli_db_update_reset_when_develop_reopened(tmp_path):
    """Новый прогон develop требует новой загрузки, а не старой отметки."""
    mod = _load()
    d = _task_with_update_db(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "db-update", "start"])
    mod.main([str(d), "db-update", "done"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "pending"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["db_update"]["finished_at"] is None
    mod.main([str(d), "develop", "running"])
    with pytest.raises(SystemExit):
        mod.main([str(d), "develop", "done"])


def _gated_task(tmp_path, analyze_status):
    s = ts.create_task(tmp_path, title="g", goal="", plan="", constraints="",
                       enabled_stages=ts.STAGE_NAMES)
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    for st in data["stages"]:
        if st["name"] == "analyze":
            st["gate"] = True
            st["approved"] = False
            st["status"] = analyze_status
        elif st["name"] == "plan":
            st["status"] = "pending"
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False),
                                 encoding="utf-8")
    return d


def test_pending_gate_does_not_block_next_stage(tmp_path):
    mod = _load()
    d = _gated_task(tmp_path, "pending")
    mod.update(str(d), "develop", "running")        # не должно бросить
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "running"


def test_done_unapproved_gate_blocks_next_stage(tmp_path):
    mod = _load()
    d = _gated_task(tmp_path, "done")
    with pytest.raises(SystemExit, match="гейт"):
        mod.update(str(d), "develop", "running")


def test_overall_status_awaiting_user(tmp_path):
    mod = _load()
    d = _gated_task(tmp_path, "done")
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert mod._overall_status(data["stages"]) == "awaiting_user"


def test_cli_normalizes_old_epoch_dates_to_iso(tmp_path):
    """Числовые даты старого файла при записи конвертируются в ISO."""
    mod = _load()
    d = _one_stage_task(tmp_path)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    data["created_at"] = 1000.0
    data["started_at"] = 800.0
    data["db_update"] = {"started_at": 700.0, "finished_at": None}
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    dev["started_at"] = 900.0
    (d / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    mod.main([str(d), "develop", "running"])

    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert isinstance(data["created_at"], str)
    assert _iso_dt(data["created_at"]).timestamp() == 1000.0
    assert isinstance(data["started_at"], str)
    assert _iso_dt(data["started_at"]).timestamp() == 800.0
    assert isinstance(data["db_update"]["started_at"], str)
    assert _iso_dt(data["db_update"]["started_at"]).timestamp() == 700.0
    # Этап уже был в running — started_at перезаписан текущим запуском (ISO).
    assert isinstance(dev["started_at"], str)


def test_cli_normalizes_old_epoch_dates_in_runs(tmp_path):
    """Числовые отметки в runs[] тоже конвертируются в ISO при записи."""
    mod = _load()
    d = _one_stage_task(tmp_path)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    dev["runs"] = [{"iteration": 1, "started_at": 900.0, "finished_at": 960}]
    (d / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    mod.main([str(d), "develop", "running"])

    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    old, new = dev["runs"][0], dev["runs"][1]
    assert _iso_dt(old["started_at"]).timestamp() == 900.0
    assert _iso_dt(old["finished_at"]).timestamp() == 960.0
    assert isinstance(new["started_at"], str)


def test_cli_pending_closes_open_run(tmp_path):
    """Аброшенный прогон (pending без done/failed) закрывается, iteration не растёт."""
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "pending"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["runs"][0]["finished_at"] is not None
    assert _iso_dt(dev["runs"][0]["finished_at"]) >= \
        _iso_dt(dev["runs"][0]["started_at"])
    assert dev["status"] == "pending"
    assert dev["iteration"] == 1
    # Новый прогон — отдельная запись, прежняя остаётся закрытой.
    mod.main([str(d), "develop", "running"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert len(dev["runs"]) == 2
    assert dev["runs"][0]["finished_at"] is not None
    assert dev["runs"][1]["finished_at"] is None


def test_cli_pending_then_running_increments_iteration(tmp_path):
    """После возврата в pending следующий running — новая итерация."""
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "pending"])
    mod.main([str(d), "develop", "running"])
    dev = _stage(json.loads((d / "task.json").read_text(encoding="utf-8")),
                 "develop")
    assert dev["iteration"] == 2
    assert [run["iteration"] for run in dev["runs"]] == [1, 2]
