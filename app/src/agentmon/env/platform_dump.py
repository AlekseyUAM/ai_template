import subprocess
import sys
import time
from pathlib import Path

from .project_checks import platform_binary, infer_db_kind, _designer_db_arg, auth_args

# Признаки ошибки аутентификации — такие НЕ ретраим (чтобы не залочить учётку).
_AUTH_MARKERS = ("парол", "идентификац", "аутентификац")


def _is_auth_error(log: str) -> bool:
    low = (log or "").lower()
    return any(m in low for m in _AUTH_MARKERS)

_TARGET = {"cf": ("src", "cf"), "cfe": ("src", "cfe")}


def build_dump_command(config, kind: str, *, user: str = "", password: str = "") -> list[str]:
    """Команда выгрузки конфигурации/расширений через нативный `1cv8 DESIGNER`.

    cf: `/DumpConfigToFiles <dir>`; cfe: то же с `-AllExtensions`. Кроссплатформенно
    (1cv8.exe на Windows, иначе 1cv8). Без зависимости от внешнего модуля.
    """
    if kind not in _TARGET:
        raise ValueError(f"неизвестный вид выгрузки: {kind!r}")
    target = str(Path(config.project_dir).joinpath(*_TARGET[kind]))
    binary = platform_binary(config.platform_dir) or str(
        Path(config.platform_dir) /
        ("1cv8.exe" if sys.platform.startswith("win") else "1cv8"))
    db_kind = getattr(config, "db_kind", "") or infer_db_kind(config.db_connection)
    flag, value = _designer_db_arg(db_kind, config.db_connection)
    cmd = [
        binary, "DESIGNER", flag, value,
        *auth_args(user, password), "/DisableStartupDialogs",
        "/DumpConfigToFiles", target,
    ]
    if kind == "cfe":
        cmd.append("-AllExtensions")
    return cmd


def dump(config, kind: str, *, user: str = "", password: str = "",
         run=subprocess.run, sleep=time.sleep, clock=time.monotonic,
         max_wait: float = 900.0, interval: float = 30.0) -> None:
    """Выгружает cf/cfe. При занятости конфигуратора повторяет попытки.

    1С не сразу освобождает конфигуратор после предыдущей выгрузки, поэтому при
    ошибке (кроме ошибок аутентификации) повторяем запуск каждые `interval` секунд
    до `max_wait` секунд. Ошибку аутентификации НЕ ретраим, чтобы не заблокировать
    учётную запись.
    """
    cmd = build_dump_command(config, kind, user=user, password=password)
    deadline = clock() + max_wait
    while True:
        # Таймаут запуска ограничиваем остатком времени до дедлайна, чтобы
        # зависший 1cv8 не висел дольше max_wait. Зависание трактуем как
        # неуспешную (ретраибельную) попытку — так же, как ненулевой код.
        remaining = deadline - clock()
        try:
            result = run(cmd, capture_output=True, text=True,
                         timeout=max(1.0, remaining))
            returncode = result.returncode
            log = ((getattr(result, "stdout", "") or "")
                   + (getattr(result, "stderr", "") or ""))
        except subprocess.TimeoutExpired:
            returncode = -1
            log = f"выгрузка {kind}: конфигуратор не ответил (таймаут запуска)"
        if returncode == 0:
            return
        if _is_auth_error(log):
            raise RuntimeError(log.strip() or f"выгрузка {kind}: ошибка аутентификации")
        if clock() >= deadline:
            raise RuntimeError(
                log.strip() or f"выгрузка {kind}: конфигуратор занят (таймаут {int(max_wait)}с)")
        sleep(interval)
