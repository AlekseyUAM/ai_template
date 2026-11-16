#!/usr/bin/env python
"""
run-tests.py
Кроссплатформенный запуск юнит-тестов 1С: стартует базу в режиме предприятия
через `1c-batch run-enterprise -C "ВыполнитьЗапускЮнитТестов=<абс. путь к конфигу>"`.

Перед запуском предприятия модули компилируются пакетным конфигуратором
(`1c-batch check-modules`): ошибка компиляции в предприятии выводится модальным
окном, из-за которого сеанс висит вечно, а оркестратор ждёт его завершения в фоне
и не узнаёт об ошибке. Конфигуратор же пишет ошибки в лог и завершается кодом, без
модальных окон. Проверяются сначала модули расширения с тестами, затем модули
основной конфигурации: ошибка компиляции в основной конфигурации (модуль,
загруженный на этапе разработки вне расширения) тоже всплыла бы модальным окном.
Сама проверка модулей ограничена 600 c на процесс — зависшая проверка убивается по
дереву и считается ошибкой среды, а не компиляции. Сам прогон предприятия
запускается с таймаутом — чтобы зависший сеанс не держал задачу бесконечно. Если
сеанс завершился по таймауту, скрипт дополнительно проверяет модули основной
конфигурации: причиной зависания мог стать модуль, изменённый после предпроверки.

Использование:
    python .claude/tools/run-tests.py [КОНФИГ] [--extension ИМЯ]
                                      [--timeout СЕК] [--no-check]
                                      [--no-check-main] [--no-cache]
                                      [--test СЦЕНАРИИ]

КОНФИГ         путь к JSON-файлу конфигурации тестов (по умолчанию configs/test.json),
              передаётся в конфигурацию как абсолютный путь.
Результат      после прогона копируется в result.<n>.json рядом с result.json —
              история прогонов не теряется при повторных смоуках и --test.
--extension   имя расширения с тестами для компиляции (по умолчанию ЮнитТесты).
--timeout     таймаут сеанса предприятия в секундах (по умолчанию 600).
              Для отладочного прогона (--test) задавайте короткий таймаут явно,
              например `--timeout 60` — значение определяет вызывающий.
--no-check    пропустить предварительную компиляцию модулей (расширения и
              основной конфигурации).
--no-check-main пропустить только проверку модулей основной конфигурации;
              расширение с тестами проверяется.
--no-cache    не использовать кэш успешной проверки модулей (по хэшу исходников).
--test        имена сценариев через запятую для отладочного прогона
              (например, `--test СебестоимостьФИФО,ПроверкаСклада`);
              остальные сценарии модуля не выполняются.

Коды возврата:
    0    штатное завершение
    1    ошибка запуска
    2    ошибка компиляции модулей расширения или основной конфигурации
         (в т.ч. до запуска предприятия; после таймаута — ошибка найдена
         в основной конфигурации)
    3    среда/лицензия/таймаут проверки модулей (проверка не уложилась
         в 600 c, дерево процессов убито) — это НЕ ошибка компиляции;
         так же при диагностике после таймаута сеанса: среда/лицензия или
         таймаут самой диагностической проверки
    4    прогон состоялся, но есть проваленные тесты (result.json свежий)
    5    result.json не найден, невалиден или список тестов пуст
    124  таймаут сеанса предприятия без ошибки компиляции и без проблемы
         среды в диагностике
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

# Имя параметра запуска, который конфигурация обрабатывает в /C
LAUNCH_PARAM = "ВыполнитьЗапускЮнитТестов"
DEFAULT_CONFIG = "configs/test.json"
DEFAULT_EXTENSION = "ЮнитТесты"
DEFAULT_TIMEOUT = 600
# Жёсткий таймаут проверки модулей: зависшая проверка не должна держать задачу.
CHECK_MODULES_TIMEOUT = 600

# Коды возврата
RC_OK = 0
RC_LAUNCH_ERROR = 1
RC_COMPILE_ERROR = 2
RC_ENV_ERROR = 3
RC_TIMEOUT = 124
RC_TESTS_FAILED = 4
RC_NO_RESULT = 5
# Внутренний код check_modules: проверка не уложилась в CHECK_MODULES_TIMEOUT.
# Наружу отдаётся как RC_ENV_ERROR; отдельный код нужен, чтобы диагностика
# таймаута отличала таймаут самой проверки от ошибки среды (лицензия и т.п.).
RC_CHECK_TIMEOUT = -1

RESULT_DONE_KEY = "Выполнено"
RESULT_ERROR_KEY = "ОписаниеОшибки"
RESULT_TESTS_KEY = "РезультатТестов"

# Маркеры ошибки компиляции в выводе конфигуратора (/CheckModules). Нужны на случай,
# если конфигуратор отчитался успехом, но написал ошибку в лог; при обычной ошибке
# он и так возвращает ненулевой код.
COMPILE_ERROR_MARKERS = (
    "ОшибкаКомпиляцииВстроенногоЯзыка",
    "Ошибка компиляции модуля",
    "Процедура или функция с указанным именем уже определена",
)

# Маркеры того, что проблема не в коде, а в среде: нет бинарника платформы,
# не подхватилась лицензия, нет доступа к базе/файлам. Такой rc нельзя отдавать
# агенту как «ошибка компиляции» — он пойдёт править рабочий код.
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
    """Перевести stdout/stderr скрипта в UTF-8.

    При перенаправлении вывода в файл (оркестратор пишет лог прогона) Python на
    Windows берёт ANSI-кодировку локали (cp1251), в которой нет эмодзи из print().
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _child_env() -> dict:
    """Окружение для дочернего 1c-batch: вывод конфигуратора в UTF-8.

    Без этого на Windows вывод (и лог) конфигуратора приходит в cp1251 и
    нечитаем при захвате через capture_output.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def get_project_root() -> Path:
    """Корень проекта (на два уровня выше .claude/tools)."""
    return Path(__file__).resolve().parent.parent.parent


def batch_cmd() -> list[str]:
    """Префикс команды: локальная (проектная) копия 1c-batch через wrapper."""
    wrapper = get_project_root() / ".claude/skills/1c-batch/scripts/1c-batch.py"
    return [sys.executable, str(wrapper)]


def _check_source_dir(project_root: Path, extension: str | None) -> Path:
    """Каталог, который проверяет check-modules: src/cf или src/cfe/<ext>."""
    if extension:
        return project_root / "src" / "cfe" / extension
    return project_root / "src" / "cf"


def _tree_hash(root: Path) -> str | None:
    """Хэш исходников проверки; None — каталога нет (кэш не используем)."""
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
    """Проверка модулей пакетным конфигуратором (/CheckModules).

    Если extension задано, проверяются модули только этого расширения
    (`-Extension ИМЯ`), иначе — модули основной конфигурации.

    Возвращает RC_OK при успехе и RC_COMPILE_ERROR при ошибке компиляции
    (ненулевой код конфигуратора или маркер ошибки в выводе). Конфигуратор пишет
    ошибки в лог и завершается — без модальных окон, которые вешают предприятие.
    Проблемы среды (лицензия, база) — RC_ENV_ERROR.

    Вся проверка ограничена CHECK_MODULES_TIMEOUT секундами: по истечении таймаута
    дерево процессов проверки убивается (как у run_enterprise) и возвращается
    RC_ENV_ERROR — это проблема среды, а не компиляции. Код именно таймаута
    получают через _check_modules_raw (нужен diagnose_timeout).
    """
    source = _check_source_dir(project_root, extension)
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
    """check_modules без перевода таймаута: возвращает RC_CHECK_TIMEOUT."""
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
        # Своя группа процессов — чтобы убивать только своё дерево.
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
        # Вывод до зависания — единственная зацепка, что за проблема среды.
        # После SIGKILL communicate может отдать None вместо строк.
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
        # Ошибка компиляции важнее env-маркеров: конфигуратор мог написать и то,
        # и другое, но чинить надо код.
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
    """Принудительно завершить дерево процессов запущенного сеанса — и обёртку
    1c-batch, и порождённый ею 1cv8.

    Трогаем только своё дерево: чужие сеансы 1С (другие базы, конфигуратор
    пользователя) не затрагиваются. На Windows — taskkill /T по PID обёртки,
    на POSIX — SIGKILL по группе процессов (сеанс создан через start_new_session).
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
    """Запусти предприятие с параметром /C для прогона тестов, с таймаутом.

    Предприятие запускается через Popen в отдельной группе процессов; по истечении
    таймаута дерево процессов убивается, возвращается RC_TIMEOUT.
    """
    cmd = batch_cmd() + ["run-enterprise", "--wait", "-C", c_value]

    print(f'Команда: 1c-batch run-enterprise -C "{c_value}"')
    print(f"   Таймаут сеанса: {timeout} c")
    print()

    popen_kwargs: dict = {"cwd": project_root, "env": _child_env()}
    if os.name == "nt":
        # Своя группа процессов — чтобы убивать только своё дерево.
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
    """Проверить модули основной конфигурации после таймаута сеанса.

    Сеанс мог зависнуть на модальном окне ошибки компиляции модуля, который
    загружен в базу на этапе разработки и не входит в расширение с тестами
    (модули расширения проверяет предварительная компиляция). Если ошибка
    найдена, возвращает RC_COMPILE_ERROR — это причина таймаута. Если сама
    проверка не уложилась в таймаут или не запустилась из-за среды/лицензии —
    RC_ENV_ERROR: это проблема среды, а не зависший код. Иначе оставляет
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
        # Не выдаём проблему диагностики (таймаут проверки или среда/лицензия)
        # за таймаут сеанса: причину ищут в среде, код править не надо.
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
    """Создать временный конфиг с отбором сценариев для отладочного прогона.

    Временный конфиг пишется в каталог logs проекта (он не попадает в git) и
    отличается от исходного только полем "Сценарии" — имена через запятую.
    Возвращает путь к конфигу для запуска; None — если исходный конфиг не
    удалось прочитать.
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
    """Путь к result.json из конфига тестов (поле ИмяФайлаЛог)."""
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
    """Удалить прошлый результат: после прогона файл может быть только свежим."""
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
    """Сохранить копию result.json как result.<n>.json — история прогонов."""
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


def _read_and_print_result(path: Path | None) -> int:
    """Прочитать result.json, напечатать сводку и вернуть 0/4/5."""
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
    passed = sum(
        1 for test in tests
        if isinstance(test, dict) and test.get("Результат") is True
    )
    failed = len(tests) - passed

    print()
    print(f"📊 Результат прогона: {path}")
    print(f"   Выполнено: {done}")
    print(f"   ОписаниеОшибки: {error}")
    print()
    for test in tests:
        if not isinstance(test, dict):
            continue
        is_ok = test.get("Результат") is True
        print(f"   {'✓' if is_ok else '✗'} {test.get('Имя', '<без имени>')}")
        if not is_ok and test.get("ОписаниеОшибки"):
            print(f"      {test['ОписаниеОшибки']}")
    print()
    print(f"ИТОГ: {passed}/{len(tests)} пройдено")

    all_passed = done is True and error is None and failed == 0
    return RC_OK if all_passed else RC_TESTS_FAILED


def run_tests(config_arg: str, extension: str, timeout: int, no_check: bool,
              scenarios: str | None = None, no_check_main: bool = False,
              no_cache: bool = False) -> int:
    """Скомпилируй модули и запусти предприятие для прогона тестов."""
    project_root = get_project_root()

    # Абсолютный путь к конфигу тестов
    config_path = Path(config_arg)
    if not config_path.is_absolute():
        config_path = (project_root / config_path).resolve()
    else:
        config_path = config_path.resolve()

    # Проверки файла
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

    # Предварительная компиляция — чтобы ошибка не всплыла модальным окном в предприятии.
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
