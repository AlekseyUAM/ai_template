#!/usr/bin/env python
"""
run-tests.py
Cross-platform 1C unit test run: starts the base in enterprise mode
via `1c-batch run-enterprise -C "ВыполнитьЗапускЮнитТестов=<abs. path to config>"`.

Before starting the enterprise, the modules are compiled by the batch Configurator
(`1c-batch check-modules`): a compilation error in the enterprise is shown in a modal
window, which makes the session hang forever while the orchestrator waits for it in the background
and never learns about the error. The Configurator writes errors to the log and exits with a code, without
modal windows. The extension modules with tests are checked first, then the modules of the
main configuration: a compilation error in the main configuration (a module
loaded during development outside the extension) would also pop up as a modal window.
The module check itself is limited to 600 c per process - a hanging check is killed by
tree and counts as an environment error, not a compilation error. The enterprise run itself
is started with a timeout - so a hanging session does not hold the task forever. If
the session ended by timeout, the script additionally checks the main configuration
modules: the hang could be caused by a module changed after the pre-check.

Usage:
    python .claude/tools/run-tests.py [CONFIG] [--extension NAME]
                                      [--timeout SEC] [--no-check]
                                      [--no-check-main] [--no-cache]
                                      [--test SCENARIOS]

CONFIG         path to the test configuration JSON file (default configs/test.json),
              passed to the configuration as an absolute path.
Result         after the run is copied to result.<n>.json next to result.json -
              run history is not lost on repeated smoke runs and --test.
--extension   name of the extension with tests for compilation (default ЮнитТесты).
--timeout     enterprise session timeout in seconds (default 600).
              For a debug run (--test) set a short timeout explicitly,
              e.g. `--timeout 60` - the value is decided by the caller.
--no-check    skip preliminary module compilation (extension and
              main configuration).
--no-check-main skip only the main configuration module check;
              the extension with tests is checked.
--no-cache    do not use the successful module check cache (by source hash).
--test        comma-separated scenario names for a debug run
              (e.g. `--test СебестоимостьФИФО,ПроверкаСклада`);
              the rest of the module's scenarios are not executed.

Return codes:
    0    normal completion
    1    launch error
    2    compilation error in extension or main configuration modules
         (including before the enterprise start; after a timeout - the error is found
         in the main configuration)
    3    environment/license/module check timeout (the check did not fit
         in 600 c, the process tree was killed) - this is NOT a compilation error;
         likewise for diagnostics after a session timeout: environment/license or
         timeout of the diagnostic check itself
    4    the run happened but there are failed tests (result.json is fresh)
    5    result.json not found, invalid or the test list is empty
    124  enterprise session timeout without a compilation error and without an
         environment problem in diagnostics
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from module_changes import has_nonempty_changed_bsl  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Name of the launch parameter the configuration handles in /C
LAUNCH_PARAM = "ВыполнитьЗапускЮнитТестов"
DEFAULT_CONFIG = "configs/test.json"
DEFAULT_EXTENSION = "ЮнитТесты"
DEFAULT_TIMEOUT = 600
# Hard timeout of the module check: a hanging check must not hold the task.
CHECK_MODULES_TIMEOUT = 600

# Return codes
RC_OK = 0
RC_LAUNCH_ERROR = 1
RC_COMPILE_ERROR = 2
RC_ENV_ERROR = 3
RC_TIMEOUT = 124
RC_TESTS_FAILED = 4
RC_NO_RESULT = 5
# Internal check_modules code: the check did not fit in CHECK_MODULES_TIMEOUT.
# Returned to the outside as RC_ENV_ERROR; a separate code is needed so that timeout
# diagnostics can tell the check's own timeout from an environment error (license etc.).
RC_CHECK_TIMEOUT = -1

RESULT_DONE_KEY = "Выполнено"
RESULT_ERROR_KEY = "ОписаниеОшибки"
RESULT_TESTS_KEY = "РезультатТестов"
RESULT_JOURNAL_KEY = "ЖурналРегистрацииВсеОшибки"

# Compilation error markers in the Configurator output (/CheckModules). Needed in case
# the Configurator reports success but wrote an error to the log; on a normal error
# it returns a non-zero code anyway.
COMPILE_ERROR_MARKERS = (
    "ОшибкаКомпиляцииВстроенногоЯзыка",
    "Ошибка компиляции модуля",
    "Процедура или функция с указанным именем уже определена",
)

# Markers that the problem is not in the code but in the environment: no platform binary,
# license not picked up, no access to the base/files. Such rc must not be given
# to the agent as a "compilation error" - it would go and change working code.
ENV_ERROR_MARKERS = (
    "Traceback (most recent call last)",
    "No such file or directory",
    "not found",
    "cannot execute",
    "Permission denied",
    "лицензи",
    "License",
    "не найден",
    "не удалось запустить",
    "Не удалось подключиться",
    "ошибка подключения",
    "platform_path",
    "не задан путь к платформе",
)


def _force_utf8_output() -> None:
    """Switch the script's stdout/stderr to UTF-8.

    When output is redirected to a file (the orchestrator writes the run log), Python on
    Windows uses the ANSI locale encoding (cp1251), which lacks emoji from print().
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _child_env() -> dict:
    """Environment for the child 1c-batch: Configurator output in UTF-8.

    Without this, on Windows the Configurator output (and log) comes in cp1251 and is
    unreadable when captured via capture_output.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def get_project_root() -> Path:
    """Project root (two levels above .claude/tools)."""
    return Path(__file__).resolve().parent.parent.parent


def batch_cmd() -> list[str]:
    """Command prefix: local (project) copy of 1c-batch via wrapper."""
    wrapper = get_project_root() / ".claude/skills/1c-batch/scripts/1c-batch.py"
    return [sys.executable, str(wrapper)]


def _check_source_dir(project_root: Path, extension: str | None) -> Path:
    """Directory checked by check-modules: src/cf or src/cfe/<ext>."""
    if extension:
        return project_root / "src" / "cfe" / extension
    return project_root / "src" / "cf"


def _tree_hash(root: Path) -> str | None:
    """Hash of the check sources; None - no directory (cache is not used)."""
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "ConfigDumpInfo.xml":
            continue
        if path.suffix.lower() not in (".bsl", ".xml"):
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            return None
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_path(project_root: Path, extension: str | None) -> Path:
    key = "cf" if not extension else "cfe-" + re.sub(r"[^0-9A-Za-z_.-]+", "_", extension)
    return project_root / "logs" / ".check-modules-cache" / f"{key}.json"


def _cache_hit(project_root: Path, extension: str | None,
               source_hash: str | None) -> bool:
    if source_hash is None:
        return False
    path = _cache_path(project_root, extension)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(data, dict) and data.get("schema") == 1
            and data.get("hash") == source_hash and data.get("rc") == RC_OK)


def _cache_store(project_root: Path, extension: str | None,
                 source_hash: str | None) -> None:
    if source_hash is None:
        return
    path = _cache_path(project_root, extension)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({
            "schema": 1, "hash": source_hash, "rc": RC_OK,
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def check_modules(project_root: Path, extension: str | None = None,
                  title: str = "Предварительная компиляция модулей",
                  use_cache: bool = True) -> int:
    """Module check by the batch Configurator (/CheckModules).

    If extension is given, only the modules of that extension are checked
    (`-Extension NAME`), otherwise - the main configuration modules.

    Returns RC_OK on success and RC_COMPILE_ERROR on a compilation error
    (non-zero Configurator code or an error marker in the output). The Configurator writes
    errors to the log and exits - without modal windows that hang the enterprise.
    Environment problems (license, base) - RC_ENV_ERROR.

    The whole check is limited to CHECK_MODULES_TIMEOUT seconds: after the timeout
    the check process tree is killed (as in run_enterprise) and
    RC_ENV_ERROR is returned - this is an environment problem, not compilation. The exact
    timeout code is obtained via _check_modules_raw (needed by diagnose_timeout).
    """
    source = _check_source_dir(project_root, extension)
    if extension is None and has_nonempty_changed_bsl(project_root, "src/cf") is False:
        print(f"⏭️  {title}: нет непустых изменённых .bsl — пропускаю компиляцию.")
        print()
        return RC_OK
    source_hash = _tree_hash(source) if use_cache else None
    if _cache_hit(project_root, extension, source_hash):
        print(f"♻️  {title}: исходники не менялись с прошлой успешной проверки "
              f"— пропускаю компиляцию (кэш).")
        print()
        return RC_OK
    rc = _check_modules_raw(project_root, extension, title)
    if rc == RC_OK and use_cache:
        _cache_store(project_root, extension, source_hash)
    return RC_ENV_ERROR if rc == RC_CHECK_TIMEOUT else rc


def _check_modules_raw(project_root: Path, extension: str | None = None,
                       title: str = "Предварительная компиляция модулей") -> int:
    """check_modules without timeout translation: returns RC_CHECK_TIMEOUT."""
    cmd = batch_cmd() + ["check-modules", "--thin-client", "--server"]
    if extension:
        cmd += ["--extension", extension]

    print(f"🔎 {title} (1c-batch check-modules)")
    print(f"   Команда: {' '.join(cmd[len(batch_cmd()):])}")
    print()

    popen_kwargs: dict = {
        "cwd": project_root,
        "env": _child_env(),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        # Own process group - to kill only our own tree.
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.",
              file=sys.stderr)
        return RC_LAUNCH_ERROR

    try:
        stdout, stderr = proc.communicate(timeout=CHECK_MODULES_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        print()
        # Output before the hang is the only clue about the environment problem.
        # After SIGKILL communicate may return None instead of strings.
        partial = ((exc.output or "") + (exc.stderr or ""))
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        if partial.strip():
            print("--- вывод проверки до таймаута ---")
            print(partial.rstrip())
            print("---")
        print(f"⏱️  Проверка модулей не уложилась в {CHECK_MODULES_TIMEOUT} c — "
              "проблема среды, не компиляции.")
        print("   Завершаю дерево процессов проверки; ошибок компиляции здесь нет —")
        print("   проверьте platform_path, лицензию и доступ к базе.")
        _kill_tree(proc)
        return RC_CHECK_TIMEOUT

    returncode = proc.returncode
    output = (stdout or "") + (stderr or "")
    if output.strip():
        print(output.rstrip())
        print()

    compile_markers = [m for m in COMPILE_ERROR_MARKERS if m in output]
    env_markers = [m for m in ENV_ERROR_MARKERS if m in output]
    if returncode != 0 or compile_markers:
        # Compilation error is more important than env markers: the Configurator could write
        # both, but the code must be fixed.
        if not compile_markers and env_markers:
            print(f"❌ Не удалось запустить проверку модулей "
                  f"(код {returncode}): проблема среды/лицензии.")
            print("   Это НЕ ошибка компиляции: проверьте platform_path, "
                  "лицензию и доступ к базе.")
            return RC_ENV_ERROR
        print(f"❌ Ошибка компиляции модулей (код конфигуратора {returncode}).")
        print("   Прогон не состоится. Исправьте ошибки компиляции и повторите.")
        return RC_COMPILE_ERROR

    print("✅ Модули скомпилированы без ошибок.")
    print()
    return RC_OK


def _kill_tree(proc: subprocess.Popen) -> None:
    """Forcefully terminate the process tree of the started session - both the 1c-batch
    wrapper and the 1cv8 it spawned.

    We touch only our own tree: other 1C sessions (other bases, the user's
    Configurator) are not affected. On Windows - taskkill /T by the wrapper PID,
    on POSIX - SIGKILL by process group (the session is created via start_new_session).
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def run_enterprise(project_root: Path, c_value: str, timeout: int) -> int:
    """Run the enterprise with the /C parameter for the test run, with a timeout.

    The enterprise is started via Popen in a separate process group; after the
    timeout the process tree is killed, RC_TIMEOUT is returned.
    """
    cmd = batch_cmd() + ["run-enterprise", "--wait", "-C", c_value]

    print(f'Команда: 1c-batch run-enterprise -C "{c_value}"')
    print(f"   Таймаут сеанса: {timeout} c")
    print()

    popen_kwargs: dict = {"cwd": project_root, "env": _child_env()}
    if os.name == "nt":
        # Own process group - to kill only our own tree.
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.",
              file=sys.stderr)
        return RC_LAUNCH_ERROR

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print()
        print(f"⏱️  Таймаут {timeout} c — сеанс предприятия не завершился.")
        print("   Завершаю дерево процессов прогона (возможно, зависло модальное окно).")
        _kill_tree(proc)
        return RC_TIMEOUT

    print()
    if returncode == 0:
        print("✅ Прогон тестов завершён (сеанс 1С закрыт).")
    else:
        print("❌ Ошибка запуска предприятия")
    return returncode


def diagnose_timeout(project_root: Path) -> int:
    """Check the main configuration modules after a session timeout.

    The session could hang on a modal compilation error window for a module that
    was loaded into the base during development and is not part of the test extension
    (extension modules are checked by preliminary compilation). If the error is
    found, returns RC_COMPILE_ERROR - this is the cause of the timeout. If the check
    itself did not fit the timeout or did not start due to environment/license -
    RC_ENV_ERROR: this is an environment problem, not hanging code. Otherwise leaves
    RC_TIMEOUT.
    """
    print()
    print("🔎 Диагностика таймаута: проверяю модули основной конфигурации.")
    print("   Причина зависания может быть в модуле конфигурации, загруженном")
    print("   на этапе разработки (вне расширения с тестами).")
    print()

    rc = _check_modules_raw(project_root, None,
                            title="Проверка модулей основной конфигурации")

    if rc == RC_COMPILE_ERROR:
        print("❗ Причина таймаута найдена: ошибка компиляции основной конфигурации.")
        print("   Предприятие зависло на модальном окне ошибки компиляции.")
        print("   Исправьте ошибки компиляции и повторите прогон.")
        return RC_COMPILE_ERROR

    if rc in (RC_CHECK_TIMEOUT, RC_ENV_ERROR):
        # Do not pass off a diagnostic problem (check timeout or environment/license)
        # as a session timeout: the cause is sought in the environment, no code fix is needed.
        what = ("Диагностика не уложилась в таймаут проверки модулей"
                if rc == RC_CHECK_TIMEOUT
                else "Диагностику провести не удалось (ошибка среды/лицензии)")
        print(f"❗ {what}: проблема среды/лицензии, не код.")
        print("   Проверьте platform_path, лицензию и доступ к базе; код не править.")
        return RC_ENV_ERROR

    if rc == RC_OK:
        print("ℹ️  Ошибок компиляции в основной конфигурации нет —")
        print("   причина таймаута другая (см. лог сеанса выше).")

    return RC_TIMEOUT


def make_effective_config(project_root: Path, config_path: Path,
                          scenarios: str | None) -> Path | None:
    """Create a temporary config with scenario selection for a debug run.

    The temporary config is written to the project logs directory (it does not go to git) and
    differs from the original only in the "Сценарии" field - comma-separated names.
    Returns the config path for launch; None - if the original config could not
    be read.
    """
    if not scenarios:
        return config_path

    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        print(f"❌ Не удалось прочитать конфиг для --test: {err}", file=sys.stderr)
        return None

    if not isinstance(data, dict):
        print("❌ Конфиг тестов должен быть JSON-объектом.", file=sys.stderr)
        return None

    data["Сценарии"] = scenarios

    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    effective = logs_dir / f"run-{config_path.stem}.json"
    effective.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"🎯 Отладочный прогон сценариев: {scenarios}")
    print(f"   Временный конфиг: {effective}")
    print("   Для локализации зависания задайте короткий --timeout (например, 60–120 c).")
    print()
    return effective


def _result_log_path(project_root: Path, config_path: Path) -> Path | None:
    """Path to result.json from the test config (field ИмяФайлаЛог)."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        print(f"⚠️  Не удалось прочитать конфиг для определения ИмяФайлаЛог: {err}")
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("ИмяФайлаЛог")
    if not isinstance(name, str) or not name.strip():
        return None
    path = Path(name)
    return path if path.is_absolute() else (project_root / path).resolve()


def _reset_result_log(path: Path | None) -> None:
    """Delete the previous result: after the run the file may only be fresh."""
    if path is None:
        print("⚠️  В конфиге не задан ИмяФайлаЛог — результат после прогона не прочитать.")
        return
    try:
        path.unlink()
        print(f"🧹 Удалён прошлый результат: {path}")
    except FileNotFoundError:
        pass
    except OSError as err:
        print(f"⚠️  Не удалось удалить прошлый результат {path}: {err}")
    print(f"📄 Результат будет записан в: {path}")


def _snapshot_result(path: Path | None) -> None:
    """Save a copy of result.json as result.<n>.json - run history."""
    if path is None or not path.is_file():
        return
    numbers = []
    for candidate in path.parent.glob("result.*.json"):
        match = re.fullmatch(r"result\.(\d+)\.json", candidate.name)
        if match:
            numbers.append(int(match.group(1)))
    target = path.with_name(f"result.{max(numbers, default=0) + 1}.json")
    try:
        shutil.copyfile(path, target)
    except OSError as err:
        print(f"⚠️  Не удалось сохранить снимок результата {target}: {err}")
        return
    print(f"🗂️  Снимок результата: {target}")


def _error_text(value) -> str:
    """Текст ошибки без None и окружающих пробелов."""
    return str(value or "").strip()


def _test_is_ok(test) -> bool:
    """Тест пройден: Результат=true и ОписаниеОшибки пустое.

    Непустое ОписаниеОшибки при Результат=true — противоречивый результат:
    сценарий сообщил об ошибке, но не сбросил Результат. Такой тест — провал.
    """
    return (isinstance(test, dict)
            and test.get("Результат") is True
            and not _error_text(test.get(RESULT_ERROR_KEY)))


def _print_journal_errors(data) -> None:
    """Напечатать первые строки ошибок журнала регистрации при провале."""
    journal = data.get(RESULT_JOURNAL_KEY) if isinstance(data, dict) else None
    if not isinstance(journal, list) or not journal:
        return
    lines = []
    for item in journal:
        if not isinstance(item, dict):
            continue
        text = _error_text(item.get("Комментарий"))
        if text:
            lines.append(text.splitlines()[0].strip())
    if not lines:
        return
    print("   Ошибки журнала регистрации:")
    for line in lines[:10]:
        print(f"      {line}")
    if len(lines) > 10:
        print(f"      … ещё {len(lines) - 10}, полный текст — в result.json")


def _read_and_print_result(path: Path | None) -> int:
    """Read result.json, print the summary and return 0/4/5."""
    if path is None:
        print("❌ В конфиге тестов не задан ИмяФайлаЛог — результат некуда прочитать.")
        return RC_NO_RESULT
    if not path.exists():
        print(f"❌ Файл результата не найден: {path}")
        print("   Прогон не дошёл до записи результата — проверьте лог сеанса выше.")
        return RC_NO_RESULT
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as err:
        print(f"❌ Не удалось прочитать результат {path}: {err}")
        return RC_NO_RESULT

    tests = data.get(RESULT_TESTS_KEY) if isinstance(data, dict) else None
    if not isinstance(tests, list) or not tests:
        print(f"❌ В результате нет тестов: {path}")
        return RC_NO_RESULT

    done = data.get(RESULT_DONE_KEY)
    error = data.get(RESULT_ERROR_KEY)
    passed = sum(1 for test in tests if _test_is_ok(test))
    failed = len(tests) - passed

    print()
    print(f"📊 Результат прогона: {path}")
    print(f"   Выполнено: {done}")
    print(f"   ОписаниеОшибки: {error}")
    print()
    for test in tests:
        if not isinstance(test, dict):
            continue
        is_ok = _test_is_ok(test)
        print(f"   {'✓' if is_ok else '✗'} {test.get('Имя', '<без имени>')}")
        if not is_ok and _error_text(test.get(RESULT_ERROR_KEY)):
            print(f"      {_error_text(test.get(RESULT_ERROR_KEY))}")
    if failed:
        _print_journal_errors(data)
    print()
    print(f"ИТОГ: {passed}/{len(tests)} пройдено")

    all_passed = done is True and not _error_text(error) and failed == 0
    return RC_OK if all_passed else RC_TESTS_FAILED


def run_tests(config_arg: str, extension: str, timeout: int, no_check: bool,
              scenarios: str | None = None, no_check_main: bool = False,
              no_cache: bool = False) -> int:
    """Compile the modules and run the enterprise for the test run."""
    project_root = get_project_root()

    # Absolute path to the test config
    config_path = Path(config_arg)
    if not config_path.is_absolute():
        config_path = (project_root / config_path).resolve()
    else:
        config_path = config_path.resolve()

    # File checks
    if not config_path.exists():
        print(f"❌ Файл конфигурации тестов не найден: {config_path}", file=sys.stderr)
        return RC_LAUNCH_ERROR
    if config_path.stat().st_size == 0:
        print(f"⚠️  Файл конфигурации тестов пуст: {config_path}")
        print("   Прогон может ничего не выполнить — проверьте содержимое.")

    effective_config = make_effective_config(project_root, config_path, scenarios)
    if effective_config is None:
        return RC_LAUNCH_ERROR

    result_path = _result_log_path(project_root, effective_config)
    _reset_result_log(result_path)

    print("🧪 Запуск юнит-тестов 1С")
    print(f"   Конфиг: {effective_config}")
    print()

    # Preliminary compilation - so the error does not pop up as a modal window in the enterprise.
    if not no_check:
        rc = check_modules(project_root, extension, use_cache=not no_cache)
        if rc != RC_OK:
            return rc
        if not no_check_main:
            rc = check_modules(project_root, None,
                               title="Проверка модулей основной конфигурации",
                               use_cache=not no_cache)
            if rc != RC_OK:
                return rc
        else:
            print("ℹ️  Проверка модулей основной конфигурации пропущена "
                  "(--no-check-main).")
            print()
    else:
        print("ℹ️  Предварительная компиляция пропущена (--no-check).")
        print()

    c_value = f"{LAUNCH_PARAM}={effective_config}"
    rc = run_enterprise(project_root, c_value, timeout)

    if rc == RC_TIMEOUT:
        return diagnose_timeout(project_root)
    if rc != RC_OK:
        return rc

    if scenarios:
        print("ℹ️  Отладочный прогон --test: это не доказательство смоука — "
              "полный набор запускайте отдельно.")

    rc = _read_and_print_result(result_path)
    _snapshot_result(result_path)
    return rc


def main() -> int:
    _force_utf8_output()

    parser = argparse.ArgumentParser(
        prog="run-tests.py",
        description="Запуск юнит-тестов 1С с предварительной компиляцией и таймаутом.",
    )
    parser.add_argument("config", nargs="?", default=DEFAULT_CONFIG,
                        help=f"путь к JSON-конфигу тестов (по умолчанию {DEFAULT_CONFIG})")
    parser.add_argument("--extension", default=DEFAULT_EXTENSION,
                        help=f"имя расширения с тестами (по умолчанию {DEFAULT_EXTENSION})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"таймаут сеанса предприятия в секундах (по умолчанию {DEFAULT_TIMEOUT})")
    parser.add_argument("--no-check", action="store_true",
                        help="пропустить предварительную компиляцию модулей "
                             "(расширения и основной конфигурации)")
    parser.add_argument("--no-check-main", action="store_true",
                        help="пропустить только проверку модулей основной конфигурации")
    parser.add_argument("--no-cache", action="store_true",
                        help="не использовать кэш успешной проверки модулей")
    parser.add_argument("--test", metavar="СЦЕНАРИИ",
                        help="имена сценариев через запятую для отладочного прогона; "
                             "остальные сценарии модуля не выполняются")
    args = parser.parse_args()

    return run_tests(args.config, args.extension, args.timeout, args.no_check,
                     args.test, no_check_main=args.no_check_main,
                     no_cache=args.no_cache)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Отменено пользователем")
        sys.exit(1)
