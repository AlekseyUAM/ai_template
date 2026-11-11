#!/usr/bin/env python
"""
run-tests.py
Кроссплатформенный запуск юнит-тестов 1С: стартует базу в режиме предприятия
через `1c-batch run-enterprise -C "ВыполнитьЗапускЮнитТестов=<абс. путь к конфигу>"`.

Перед запуском предприятия модули компилируются пакетным конфигуратором
(`1c-batch check-modules`): ошибка компиляции в предприятии выводится модальным
окном, из-за которого сеанс висит вечно, а оркестратор ждёт его завершения в фоне
и не узнаёт об ошибке. Конфигуратор же пишет ошибки в лог и завершается кодом, без
модальных окон. Сам прогон предприятия запускается с таймаутом — чтобы зависший
сеанс не держал задачу бесконечно. Если сеанс завершился по таймауту, скрипт
дополнительно проверяет модули основной конфигурации: зависание может быть вызвано
модальным окном ошибки компиляции модуля, загруженного на этапе разработки вне
расширения с тестами.

Использование:
    python .claude/tools/run-tests.py [КОНФИГ] [--extension ИМЯ]
                                      [--timeout СЕК] [--no-check]
                                      [--test СЦЕНАРИИ]

КОНФИГ         путь к JSON-файлу конфигурации тестов (по умолчанию configs/test.json),
              передаётся в конфигурацию как абсолютный путь.
--extension   имя расширения с тестами для компиляции (по умолчанию ЮнитТесты).
--timeout     таймаут сеанса предприятия в секундах (по умолчанию 600).
              Для отладочного прогона (--test) задавайте короткий таймаут явно,
              например `--timeout 60` — значение определяет вызывающий.
--no-check    пропустить предварительную компиляцию модулей.
--test        имена сценариев через запятую для отладочного прогона
              (например, `--test СебестоимостьФИФО,ПроверкаСклада`);
              остальные сценарии модуля не выполняются.

Коды возврата:
    0    штатное завершение
    1    ошибка запуска
    2    ошибка компиляции модулей (предприятие не запускалось или зависло
         на модальном окне ошибки компиляции основной конфигурации)
    3    ошибка среды/лицензии (платформа не запустилась, база недоступна)
    124  таймаут сеанса предприятия
"""

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

# Имя параметра запуска, который конфигурация обрабатывает в /C
LAUNCH_PARAM = "ВыполнитьЗапускЮнитТестов"
DEFAULT_CONFIG = "configs/test.json"
DEFAULT_EXTENSION = "ЮнитТесты"
DEFAULT_TIMEOUT = 600

# Коды возврата
RC_OK = 0
RC_LAUNCH_ERROR = 1
RC_COMPILE_ERROR = 2
RC_ENV_ERROR = 3
RC_TIMEOUT = 124

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


def check_modules(project_root: Path, extension: str | None = None,
                  title: str = "Предварительная компиляция модулей") -> int:
    """Проверка модулей пакетным конфигуратором (/CheckModules).

    Если extension задано, проверяются модули только этого расширения
    (`-Extension ИМЯ`), иначе — модули основной конфигурации.

    Возвращает RC_OK при успехе и RC_COMPILE_ERROR при ошибке компиляции
    (ненулевой код конфигуратора или маркер ошибки в выводе). Конфигуратор пишет
    ошибки в лог и завершается — без модальных окон, которые вешают предприятие.
    """
    cmd = batch_cmd() + ["check-modules", "--thin-client", "--server"]
    if extension:
        cmd += ["--extension", extension]

    print(f"🔎 {title} (1c-batch check-modules)")
    print(f"   Команда: {' '.join(cmd[len(batch_cmd()):])}")
    print()

    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            env=_child_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print("❌ Ошибка: не найден wrapper 1c-batch в .claude/skills/1c-batch/scripts.",
              file=sys.stderr)
        return RC_LAUNCH_ERROR

    output = (result.stdout or "") + (result.stderr or "")
    if output.strip():
        print(output.rstrip())
        print()

    compile_markers = [m for m in COMPILE_ERROR_MARKERS if m in output]
    env_markers = [m for m in ENV_ERROR_MARKERS if m in output]
    if result.returncode != 0 or compile_markers:
        # Ошибка компиляции важнее env-маркеров: конфигуратор мог написать и то,
        # и другое, но чинить надо код.
        if not compile_markers and env_markers:
            print(f"❌ Не удалось запустить проверку модулей "
                  f"(код {result.returncode}): проблема среды/лицензии.")
            print("   Это НЕ ошибка компиляции: проверьте platform_path, "
                  "лицензию и доступ к базе.")
            return RC_ENV_ERROR
        print(f"❌ Ошибка компиляции модулей (код конфигуратора {result.returncode}).")
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
        print("   Результаты смотри там, куда их пишет обработчик тестов в конфигурации.")
    else:
        print("❌ Ошибка запуска предприятия")
    return returncode


def diagnose_timeout(project_root: Path) -> int:
    """Проверить модули основной конфигурации после таймаута сеанса.

    Сеанс мог зависнуть на модальном окне ошибки компиляции модуля, который
    загружен в базу на этапе разработки и не входит в расширение с тестами
    (модули расширения проверяет предварительная компиляция). Если ошибка
    найдена, возвращает RC_COMPILE_ERROR — это причина таймаута. Иначе оставляет
    RC_TIMEOUT.
    """
    print()
    print("🔎 Диагностика таймаута: проверяю модули основной конфигурации.")
    print("   Причина зависания может быть в модуле конфигурации, загруженном")
    print("   на этапе разработки (вне расширения с тестами).")
    print()

    rc = check_modules(project_root, None,
                       title="Проверка модулей основной конфигурации")

    if rc == RC_COMPILE_ERROR:
        print("❗ Причина таймаута найдена: ошибка компиляции основной конфигурации.")
        print("   Предприятие зависло на модальном окне ошибки компиляции.")
        print("   Исправьте ошибки компиляции и повторите прогон.")
        return RC_COMPILE_ERROR

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


def run_tests(config_arg: str, extension: str, timeout: int, no_check: bool,
              scenarios: str | None = None) -> int:
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

    print("🧪 Запуск юнит-тестов 1С")
    print(f"   Конфиг: {effective_config}")
    print()

    # Предварительная компиляция — чтобы ошибка не всплыла модальным окном в предприятии.
    if not no_check:
        rc = check_modules(project_root, extension)
        if rc != RC_OK:
            return rc
    else:
        print("ℹ️  Предварительная компиляция пропущена (--no-check).")
        print()

    c_value = f"{LAUNCH_PARAM}={effective_config}"
    rc = run_enterprise(project_root, c_value, timeout)

    if rc == RC_TIMEOUT:
        return diagnose_timeout(project_root)

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
                        help="пропустить предварительную компиляцию модулей")
    parser.add_argument("--test", metavar="СЦЕНАРИИ",
                        help="имена сценариев через запятую для отладочного прогона; "
                             "остальные сценарии модуля не выполняются")
    args = parser.parse_args()

    return run_tests(args.config, args.extension, args.timeout, args.no_check,
                     args.test)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n⚠️  Отменено пользователем")
        sys.exit(1)
