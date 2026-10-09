import subprocess

import pytest
from agentmon.env.config_schema import EnvConfig, AgentModel, SCHEMA_VERSION
from agentmon.env import platform_dump


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/base/demo", web_publication="",
        mcp=[], agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


class FakeRun:
    def __init__(self, returncode=0, stderr=""):
        self.calls = []
        self._rc, self._err = returncode, stderr

    def __call__(self, args, **kw):
        self.calls.append(args)
        class R:
            returncode = self._rc
            stderr = self._err
        return R()


def test_cf_command_targets_src_cf(tmp_path):
    args = platform_dump.build_dump_command(cfg(tmp_path), "cf")
    assert str(tmp_path / "src" / "cf") in args


def test_dump_calls_runner(tmp_path):
    fake = FakeRun()
    platform_dump.dump(cfg(tmp_path), "cf", run=fake)
    assert len(fake.calls) == 1


def test_dump_raises_on_nonzero(tmp_path):
    fake = FakeRun(returncode=1, stderr="конфигуратор занят")
    # max_wait=0 → без ожидания, падаем сразу
    with pytest.raises(RuntimeError, match="конфигуратор занят"):
        platform_dump.dump(cfg(tmp_path), "cfe", run=fake,
                           sleep=lambda _s: None, max_wait=0)


def test_dump_retries_until_configurator_free(tmp_path):
    """При занятом конфигураторе повторяем, пока не освободится (rc=0)."""
    class Flaky:
        def __init__(self):
            self.n = 0
        def __call__(self, args, **kw):
            self.n += 1
            n = self.n
            class R:
                returncode = 0 if n >= 3 else 1
                stdout = ""
                stderr = "" if n >= 3 else "конфигуратор уже открыт"
            return R()
    flaky = Flaky()
    slept = []
    platform_dump.dump(cfg(tmp_path), "cfe", run=flaky,
                       sleep=lambda s: slept.append(s), interval=30, max_wait=900)
    assert flaky.n == 3            # две неудачи, третья успешна
    assert slept == [30, 30]       # ждали по 30 сек между попытками


def test_dump_no_retry_on_auth_error(tmp_path):
    """Ошибку аутентификации не ретраим (чтобы не залочить учётку)."""
    fake = FakeRun(returncode=1, stderr="Превышено число ошибок ввода имени и пароля")
    slept = []
    with pytest.raises(RuntimeError):
        platform_dump.dump(cfg(tmp_path), "cf", run=fake,
                           sleep=lambda s: slept.append(s), max_wait=900)
    assert len(fake.calls) == 1   # одна попытка, без ретраев
    assert slept == []


def test_dump_passes_bounded_timeout_to_run(tmp_path):
    """run получает timeout, ограниченный остатком до дедлайна."""
    seen = {}
    def fake_run(args, **kw):
        seen["timeout"] = kw.get("timeout")
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()
    clock = iter([0.0, 0.0, 0.0])
    platform_dump.dump(cfg(tmp_path), "cf", run=fake_run,
                       clock=lambda: next(clock), max_wait=120.0)
    assert seen["timeout"] == 120.0


def test_dump_treats_timeout_as_retryable(tmp_path):
    """Зависший 1cv8 (TimeoutExpired) — неуспешная попытка, после которой
    ретраим; на следующем успехе выходим."""
    calls = {"n": 0}
    def fake_run(args, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kw.get("timeout"))
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()
    slept = []
    platform_dump.dump(cfg(tmp_path), "cf", run=fake_run,
                       sleep=lambda s: slept.append(s), interval=5, max_wait=900)
    assert calls["n"] == 2 and slept == [5]


def test_dump_timeout_respects_deadline(tmp_path):
    """Если после зависания дедлайн истёк — не спим, падаем с таймаутом."""
    def fake_run(args, **kw):
        raise subprocess.TimeoutExpired(cmd=args, timeout=kw.get("timeout"))
    slept = []
    # Дедлайн достигается ко второй проверке clock() внутри цикла.
    clock = iter([0.0, 0.0, 10.0, 10.0, 10.0])
    with pytest.raises(RuntimeError):
        platform_dump.dump(cfg(tmp_path), "cf", run=fake_run,
                           sleep=lambda s: slept.append(s),
                           clock=lambda: next(clock), max_wait=5.0)
    assert slept == []


def test_unknown_kind_is_error(tmp_path):
    with pytest.raises(ValueError):
        platform_dump.build_dump_command(cfg(tmp_path), "xml")
