"""
Проверки проекта: имена, требования, версия окружения.
"""

import keyword
import shutil
import subprocess
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


def is_empty_dir(path: str) -> bool:
    """
    Проверяет, пригоден ли каталог для нового проекта.

    Каталог пригоден (пуст), если он не существует либо существует и пуст.
    Если по пути лежит файл или непустой каталог — возвращает False.

    :param path: Путь к каталогу проекта
    :return: True, если каталог пуст/не существует
    """
    if not path:
        return False
    p = Path(path)
    if not p.exists():
        return True
    if not p.is_dir():
        return False
    return not any(p.iterdir())


def requirements(run=subprocess.run) -> list[dict]:
    """
    Проверяет наличие требуемых инструментов: python3, git, claude, node.
    На Windows дополнительно проверяет наличие git bash (bash) — он нужен для
    bash-скриптов навыков.
    (docker не требуется при установке проекта — он нужен лишь для подъёма MCP.)

    node требуется нескольким навыкам (query-analyze, web-test и др.).

    :param run: Функция для запуска подпроцессов (по умолчанию subprocess.run)
    :return: Список словарей с ключами name, ok, detail
    """
    required_tools = ["python3", "git", "claude", "node"]
    result = []

    for tool in required_tools:
        path = shutil.which(tool)
        result.append({
            "name": tool,
            "ok": path is not None,
            "detail": path if path else "не найден"
        })

    # git bash нужен только на Windows (bash-скрипты навыков)
    if sys.platform.startswith("win"):
        path = shutil.which("bash")
        result.append({
            "name": "git bash",
            "ok": path is not None,
            "detail": path if path else "не найден (установите Git for Windows)"
        })

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


def platform_binary(platform_dir: str) -> str | None:
    """Путь к исполняемому 1cv8 (кроссплатформенно).

    Если platform_dir — файл, возвращает его. Иначе ищет `1cv8.exe` (Windows) или
    `1cv8` (прочие ОС) в самом каталоге и в подкаталоге `bin`. None, если не найден.
    """
    if not platform_dir:
        return None
    p = Path(platform_dir)
    if p.is_file():
        return str(p)
    names = ["1cv8.exe"] if sys.platform.startswith("win") else ["1cv8", "1cv8.exe"]
    for base in (p, p / "bin"):
        for name in names:
            cand = base / name
            if cand.exists():
                return str(cand)
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


def build_check_db_command(platform_dir, db_connection="", user="", password="",
                           *, db_kind="", out_log="") -> list[str]:
    """Собирает команду проверки доступа к базе через `1cv8 DESIGNER`.

    Сервер: `1cv8 DESIGNER /S "server\\base" ...`; файл: `1cv8 DESIGNER /F "path" ...`.
    Пробой служит `/DumpDBCfgList -AllExtensions` (требует рабочего соединения).
    """
    if not db_kind:
        db_kind = infer_db_kind(db_connection)
    binary = platform_binary(platform_dir) or str(
        Path(platform_dir) / ("1cv8.exe" if sys.platform.startswith("win") else "1cv8"))
    flag, value = _designer_db_arg(db_kind, db_connection)
    return [
        binary, "DESIGNER", flag, value,
        *auth_args(user, password),
        "/DisableStartupDialogs", "/Out", out_log,
        "/DumpDBCfgList", "-AllExtensions",
    ]


def check_db(*, platform_dir: str, db_connection: str, db_kind: str = "",
             user: str = "", password: str = "", run=subprocess.run) -> dict:
    """Проверяет доступ к базе (returncode==0 → успех).

    Запускает `1cv8 DESIGNER ... /DumpDBCfgList`. Путь к платформе обязателен.
    """
    if not platform_dir:
        return {"ok": False, "log": "Укажите путь к платформе 1С."}
    if platform_binary(platform_dir) is None:
        return {"ok": False,
                "log": f"Не найден исполняемый 1cv8 по пути платформы: {platform_dir}"}

    if not db_kind:
        db_kind = infer_db_kind(db_connection)

    import tempfile
    tmp = tempfile.NamedTemporaryFile(prefix="check-db-", suffix=".log", delete=False)
    tmp.close()
    out_log = tmp.name
    try:
        cmd = build_check_db_command(platform_dir, db_connection, user, password,
                                     db_kind=db_kind, out_log=out_log)
        try:
            result = run(cmd, capture_output=True, text=True)
        except FileNotFoundError as exc:
            return {"ok": False, "log": f"не удалось запустить 1cv8: {exc}"}

        ok = result.returncode == 0
        # При успехе /DumpDBCfgList выводит список расширений — к проверке доступа
        # он отношения не имеет, поэтому в лог кладём только диагностику при ошибке.
        pieces = []
        if not ok:
            try:
                file_log = Path(out_log).read_text(encoding="utf-8", errors="replace")
            except OSError:
                file_log = ""
            if file_log.strip():
                pieces.append(file_log.strip())
            tail = ((result.stdout or "") + (result.stderr or "")).strip()
            if tail:
                pieces.append(tail)
        log = "\n".join(pieces) or ("Доступ есть" if ok else f"Код возврата {result.returncode}")
        return {"ok": ok, "log": log}
    finally:
        try:
            Path(out_log).unlink()
        except OSError:
            pass
