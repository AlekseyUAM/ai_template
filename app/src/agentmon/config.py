import os
from pathlib import Path

DB_PATH = Path(os.environ.get("AGENTMON_DB", "agentmon.db"))
DSN = os.environ.get("AGENTMON_DSN", str(DB_PATH))

# Сессия считается "generating", если журнал менялся не позже этого окна (сек).
GENERATING_WINDOW = 10.0

# Команда запуска агента; переопределяется через env или в настройках проекта.
CLAUDE_CMD = os.environ.get("AGENTMON_CLAUDE_CMD", "claude --dangerously-skip-permissions .")

# Адрес/порт HTTP-сервера; в Docker ставим AGENTMON_HOST=0.0.0.0.
HOST = os.environ.get("AGENTMON_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENTMON_PORT", "8765"))

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
