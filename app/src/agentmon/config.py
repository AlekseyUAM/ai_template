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
