import hmac
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("AGENTMON_DB", "agentmon.db"))
# Хранилище (store) по умолчанию — отдельный файл store.db рядом с реестром:
# у таблиц projects в реестре и хранилище разные схемы, общий файл их ломает.
DSN = os.environ.get("AGENTMON_DSN", str(DB_PATH.with_name("store.db")))
# Логи/exit-файлы detached-прогонов. Для local они лежат в проекте, для
# ssh/docker — на машине монитора (рядом с БД), потому что project.path —
# путь на цели и локально может не существовать.
RUNS_DIR = Path(os.environ.get(
    "AGENTMON_RUNS_DIR", str(Path(DB_PATH).resolve().parent / "agentmon-runs")))

# Сессия считается "generating", если журнал менялся не позже этого окна (сек).
GENERATING_WINDOW = 10.0

# Команда запуска агента; переопределяется через env или в настройках проекта.
CLAUDE_CMD = os.environ.get("AGENTMON_CLAUDE_CMD", "claude --dangerously-skip-permissions .")

# Адрес/порт HTTP-сервера; в Docker ставим AGENTMON_HOST=0.0.0.0.
HOST = os.environ.get("AGENTMON_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENTMON_PORT", "8765"))

# --- Доступ к API ---
# Токен обязателен, если сервер слушает не loopback: приложение умеет
# запускать процессы и писать файлы от имени пользователя.
TOKEN = os.environ.get("AGENTMON_TOKEN") or None
# Дополнительные Host, которым разрешено обращаться к API (через запятую).
# Нужны при работе за reverse-proxy/по имени хоста.
ALLOWED_HOSTS = [
    part.strip().lower()
    for part in os.environ.get("AGENTMON_ALLOWED_HOSTS", "").split(",")
    if part.strip()
]

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_loopback(host: str) -> bool:
    return (host or "").strip().lower() in _LOOPBACK_HOSTS


def ensure_secure_bind(host: str | None = None, token: str | None = None) -> None:
    """Не дать поднять сервер наружу без токена.

    Вызывается на старте uvicorn: если bind не loopback, а токен не задан,
    процесс завершается с понятной ошибкой вместо тихой публикации API.
    """
    host = HOST if host is None else host
    token = TOKEN if token is None else token
    if not is_loopback(host) and not token:
        raise SystemExit(
            f"AGENTMON_HOST={host!r}: сервер слушает не loopback, но "
            "AGENTMON_TOKEN не задан. Задайте токен или слушайте 127.0.0.1."
        )


def token_matches(provided: str | None) -> bool:
    if not TOKEN:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided, TOKEN)


def host_allowed(host_header: str | None, request_host: str | None = None) -> bool:
    """Разрешён ли Host из запроса (защита от DNS-rebinding).

    При bind на 0.0.0.0 список хостов неизвестен — границей становится токен,
    поэтому при заданном токене Host не ограничиваем.
    """
    if not host_header:
        return False
    hostname = host_header.strip().lower()
    if hostname.startswith("["):                # [::1]:8765
        hostname = hostname[1:hostname.find("]")] if "]" in hostname else hostname
    elif hostname.count(":") == 1:              # host:port
        hostname = hostname.split(":", 1)[0]
    if hostname in _LOOPBACK_HOSTS:
        return True
    # Starlette TestClient; реального хоста с таким именем нет.
    if hostname == "testserver":
        return True
    if hostname in ALLOWED_HOSTS:
        return True
    bound = (HOST or "").strip().lower()
    if bound and bound not in {"0.0.0.0", "::"} and hostname == bound:
        return True
    if bound in {"0.0.0.0", "::"} and TOKEN:
        return True
    return False

# Период опроса диспетчера и минимальная длительность задачи (сек).
DISPATCH_INTERVAL = 3.0
MIN_RUN_SECONDS = 5.0

# --- Telegram-интеграция (опционально) ---
# Нет токена → фича выключена: ни бот, ни нотификатор не стартуют.
TG_TOKEN = os.environ.get("AGENTMON_TG_TOKEN") or None

# Разрешённые chat_id (через запятую). Чужие чаты игнорируются.
TG_CHAT_IDS = [
    part.strip()
    for part in os.environ.get("AGENTMON_TG_CHAT_IDS", "").split(",")
    if part.strip()
]

# База Bot API и локальный REST приложения (вызовы изнутри процесса).
TG_API_BASE = os.environ.get("AGENTMON_TG_API_BASE", "https://api.telegram.org")


def local_base_url() -> str:
    return f"http://127.0.0.1:{PORT}"
