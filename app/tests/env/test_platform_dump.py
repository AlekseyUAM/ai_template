import pytest
from agentmon.backends import RunResult
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


class FakeProv:
    """Имитирует Provisioner для dump-тестов.

    results — список RunResult, которые возвращаются по очереди.
    Записывает все (cmd, kwargs) в self.calls.
    """

    def __init__(self, *results: RunResult):
        self._results = list(results)
        self.calls: list[tuple[list, dict]] = []

    def run(self, cmd, cwd=None, timeout=None) -> RunResult:
        self.calls.append((cmd, {"cwd": cwd, "timeout": timeout}))
        if self._results:
            return self._results.pop(0)
        # По умолчанию возвращаем rc=0, чтобы последние вызовы не роняли тест.
        return RunResult(0, "", "")

    # build_dump_command использует prov.which / prov.is_file / prov.exists
    def which(self, tool) -> str | None:
        return None

    def is_file(self, path) -> bool:
        return False

    def exists(self, path) -> bool:
        return False


# ---------------------------------------------------------------------------
# build_dump_command
# ---------------------------------------------------------------------------

def test_cf_command_targets_src_cf(tmp_path):
    args = platform_dump.build_dump_command(cfg(tmp_path), "cf")
    assert str(tmp_path / "src" / "cf") in args


def test_unknown_kind_is_error(tmp_path):
    with pytest.raises(ValueError):
        platform_dump.build_dump_command(cfg(tmp_path), "xml")


# ---------------------------------------------------------------------------
# dump — успешный первый запуск
# ---------------------------------------------------------------------------

def test_dump_rc0_first_try(tmp_path):
    """rc=0 с первой попытки → возвращаемся, один вызов prov.run."""
    prov = FakeProv(RunResult(0, "", ""))
    platform_dump.dump(cfg(tmp_path), "cf", prov=prov)
    assert len(prov.calls) == 1


# ---------------------------------------------------------------------------
# dump — ретрай при занятом конфигураторе
# ---------------------------------------------------------------------------

def test_dump_retries_until_configurator_free(tmp_path):
    """rc!=0 (занят) → ретрай; rc=0 на третьей попытке."""
    prov = FakeProv(
        RunResult(1, "", "конфигуратор уже открыт"),
        RunResult(1, "", "конфигуратор уже открыт"),
        RunResult(0, "", ""),
    )
    slept = []
    platform_dump.dump(cfg(tmp_path), "cfe", prov=prov,
                       sleep=lambda s: slept.append(s), interval=30, max_wait=900)
    assert len(prov.calls) == 3
    assert slept == [30, 30]


# ---------------------------------------------------------------------------
# dump — таймаут rc=124 ретраибелен
# ---------------------------------------------------------------------------

def test_dump_timeout_rc124_is_retryable(tmp_path):
    """rc=124 (таймаут prov.run) — не auth-ошибка → ретраим; после успеха выходим."""
    prov = FakeProv(
        RunResult(124, "", "<timeout>"),
        RunResult(0, "", ""),
    )
    slept = []
    platform_dump.dump(cfg(tmp_path), "cf", prov=prov,
                       sleep=lambda s: slept.append(s), interval=5, max_wait=900)
    assert len(prov.calls) == 2
    assert slept == [5]


def test_dump_timeout_then_deadline(tmp_path):
    """rc=124, затем дедлайн истёк — RuntimeError, без повторного sleep."""
    prov = FakeProv(
        RunResult(124, "", "<timeout>"),
    )
    slept = []
    # clock: start=0, remaining=5; после попытки clock>=deadline
    clock = iter([0.0, 0.0, 10.0, 10.0])
    with pytest.raises(RuntimeError):
        platform_dump.dump(cfg(tmp_path), "cf", prov=prov,
                           sleep=lambda s: slept.append(s),
                           clock=lambda: next(clock), max_wait=5.0)
    assert slept == []


# ---------------------------------------------------------------------------
# dump — ошибка аутентификации → немедленный RuntimeError
# ---------------------------------------------------------------------------

def test_dump_no_retry_on_auth_error(tmp_path):
    """Маркер аутентификации в stderr → RuntimeError без ретрая."""
    prov = FakeProv(
        RunResult(1, "", "Превышено число ошибок ввода имени и пароля"),
    )
    slept = []
    with pytest.raises(RuntimeError):
        platform_dump.dump(cfg(tmp_path), "cf", prov=prov,
                           sleep=lambda s: slept.append(s), max_wait=900)
    assert len(prov.calls) == 1
    assert slept == []


def test_dump_no_retry_on_auth_error_in_stdout(tmp_path):
    """Маркер аутентификации в stdout тоже блокирует ретрай."""
    prov = FakeProv(
        RunResult(1, "неверный пароль указан", ""),
    )
    slept = []
    with pytest.raises(RuntimeError):
        platform_dump.dump(cfg(tmp_path), "cf", prov=prov,
                           sleep=lambda s: slept.append(s), max_wait=900)
    assert len(prov.calls) == 1
    assert slept == []


# ---------------------------------------------------------------------------
# dump — дедлайн истёк после нескольких попыток
# ---------------------------------------------------------------------------

def test_dump_deadline_exceeded(tmp_path):
    """Дедлайн истёк после нескольких ретраев → RuntimeError."""
    # Всегда возвращаем занятость
    prov = FakeProv(
        RunResult(1, "", "занят"),
        RunResult(1, "", "занят"),
        RunResult(1, "", "занят"),
    )
    slept = []
    # max_wait=0 → дедлайн сразу, не ретраим
    with pytest.raises(RuntimeError, match="занят"):
        platform_dump.dump(cfg(tmp_path), "cfe", prov=prov,
                           sleep=lambda s: slept.append(s), max_wait=0)


# ---------------------------------------------------------------------------
# dump — prov.run получает корректный timeout
# ---------------------------------------------------------------------------

def test_dump_passes_bounded_timeout_to_prov_run(tmp_path):
    """prov.run вызывается с timeout=remaining (ограничен до дедлайна)."""
    prov = FakeProv(RunResult(0, "", ""))
    clock = iter([0.0, 0.0, 0.0])
    platform_dump.dump(cfg(tmp_path), "cf", prov=prov,
                       clock=lambda: next(clock), max_wait=120.0)
    assert len(prov.calls) == 1
    _, kw = prov.calls[0]
    assert kw["timeout"] == 120.0
