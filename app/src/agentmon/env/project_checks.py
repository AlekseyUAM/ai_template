"""
Проверки проекта: имена, требования, версия окружения.
"""

import keyword
import os
import sys
from pathlib import Path


def validate_name(name: str) -> tuple[bool, str | None]:
    """
    Проверяет, является ли имя валидным идентификатором Python и не ключевым словом.

    :param name: Имя для проверки
    :return: Кортеж (валидно ли, ошибка или None)
    """
    # Проверка, что имя является идентификатором
    if not name.isidentifier():
        return (False, "Имя должно быть валидным идентификатором Python")

    # Проверка, что имя не является ключевым словом
    if keyword.iskeyword(name):
        return (False, "Имя не может быть ключевым словом Python")

    return (True, None)


def is_empty_dir(prov, path) -> bool:
    return prov.is_empty_dir(path)


def requirements(prov) -> list[dict]:
    required_tools = ["git", "claude", "node"]
    result = []
    for tool in required_tools:
        path = prov.which(tool)
        result.append({"name": tool, "ok": path is not None,
                       "detail": path if path else "не найден"})
    # git bash нужен только если цель — Windows; в удалённых Linux-сценариях нет.
    # Для local сохраняем прежнюю проверку по sys.platform монитора.
    if sys.platform.startswith("win"):
        path = prov.which("bash")
        result.append({"name": "git bash", "ok": path is not None,
                       "detail": path if path else "не найден (установите Git for Windows)"})
    return result


def current_env_version() -> str:
    """
    Читает версию окружения из файла template/VERSION в корне репо.

    :return: Содержимое файла VERSION
    """
    # Путь к файлу VERSION в корне репо
    # __file__ находится в app/src/agentmon/env/project_checks.py
    # родители: [4] = корень репо
    version_file = Path(__file__).resolve().parents[4] / "template" / ".claude" / "VERSION"

    if version_file.exists():
        return version_file.read_text()

    return ""


def infer_db_kind(connection: str) -> str:
    """Определяет тип базы (file/server) по строке подключения."""
    c = (connection or "").lower()
    if "srvr=" in c or "ref=" in c:
        return "server"
    return "file"


def platform_binary(prov, platform_dir) -> str | None:
    """Путь к исполняемому 1cv8 на ЦЕЛИ. Цель — Linux: имя `1cv8`.

    Если platform_dir указывает прямо на файл — вернём его.
    Иначе ищем `1cv8` и `1cv8.exe` в каталоге и в bin/.
    """
    if not platform_dir:
        return None
    if prov.is_file(platform_dir):
        return platform_dir
    for cand in (f"{platform_dir}/1cv8", f"{platform_dir}/bin/1cv8",
                 f"{platform_dir}/1cv8.exe", f"{platform_dir}/bin/1cv8.exe"):
        if prov.exists(cand):
            return cand
    return None


def auth_args(user: str, password: str) -> list[str]:
    """Аргументы аутентификации 1cv8.

    /N — только если задан пользователь (иначе 1cv8 отвергает пустой /N "").
    /P — только если задан непустой пароль (пустой /P "" тоже ломает запуск);
    у пользователя с пустым паролем передаём только /N.
    """
    args: list[str] = []
    if user:
        args += ["/N", user]
    if password:
        args += ["/P", password]
    return args


def _designer_db_arg(db_kind: str, connection: str) -> tuple[str, str]:
    """Строит аргумент DESIGNER для подключения: (/S, server\\base) или (/F, path)."""
    conn = connection or ""
    if db_kind == "server":
        srvr = ref = ""
        for part in conn.replace(";", "\n").splitlines():
            key, _, val = part.partition("=")
            key = key.strip().lower(); val = val.strip().strip('"')
            if key == "srvr":
                srvr = val
            elif key == "ref":
                ref = val
        if srvr or ref:
            return ("/S", f"{srvr}\\{ref}")
        # уже в виде server\base или server/base
        return ("/S", conn.replace("/", "\\"))
    # файловая: снять префикс File= при наличии
    path = conn
    if "=" in conn and conn.split("=", 1)[0].strip().lower() == "file":
        path = conn.split("=", 1)[1].strip().strip('"')
    return ("/F", path)


def build_check_db_command(binary, db_connection="", user="", password="",
                           *, db_kind="", out_log="") -> list[str]:
    """Собирает команду проверки доступа к базе через `1cv8 DESIGNER`.

    Сервер: `1cv8 DESIGNER /S "server\\base" ...`; файл: `1cv8 DESIGNER /F "path" ...`.
    Пробой служит `/DumpDBCfgList -AllExtensions` (требует рабочего соединения).
    """
    if not db_kind:
        db_kind = infer_db_kind(db_connection)
    flag, value = _designer_db_arg(db_kind, db_connection)
    return [
        binary, "DESIGNER", flag, value,
        *auth_args(user, password),
        "/DisableStartupDialogs", "/Out", out_log,
        "/DumpDBCfgList", "-AllExtensions",
    ]


def check_db(prov, *, platform_dir: str, db_connection: str, db_kind: str = "",
             user: str = "", password: str = "") -> dict:
    """Проверяет доступ к базе через `1cv8 DESIGNER ... /DumpDBCfgList` на ЦЕЛИ.

    Запуск — через prov.run (на удалённом хосте там же, где платформа и сеть до
    сервера 1С). Лог ошибки собираем из stdout/stderr команды.
    """
    if not platform_dir:
        return {"ok": False, "log": "Укажите путь к платформе 1С."}
    binary = platform_binary(prov, platform_dir)
    if binary is None:
        return {"ok": False,
                "log": f"Не найден исполняемый 1cv8 по пути платформы: {platform_dir}"}
    if not db_kind:
        db_kind = infer_db_kind(db_connection)
    out_log = f"{prov.tempdir()}/ai1c-check-db-{os.getpid()}.log"
    cmd = build_check_db_command(binary, db_connection, user, password,
                                 db_kind=db_kind, out_log=out_log)
    res = prov.run(cmd)
    ok = res.returncode == 0
    if ok:
        return {"ok": True, "log": "Доступ есть"}
    tail = ((res.stdout or "") + (res.stderr or "")).strip()
    try:
        file_log = prov.read_text(out_log).strip()
    except Exception:
        file_log = ""
    log = "\n".join(p for p in (file_log, tail) if p) or f"Код возврата {res.returncode}"
    return {"ok": False, "log": log}
