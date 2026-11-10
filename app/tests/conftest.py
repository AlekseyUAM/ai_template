import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentmon import config  # noqa: E402

# TestClient ходит с Host: testserver; в проде такого хоста нет, но проверка
# Host должна пропускать его в тестах.
config.HOST = "testserver"
config.TOKEN = None
config.ALLOWED_HOSTS = []

FIXTURES = Path(__file__).parent / "fixtures"
