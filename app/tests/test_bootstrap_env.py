"""Тесты для bootstrap.env_file_contents.

Импорт bootstrap.py выполняется через sys.path — аналогично test_run_launcher.py.
bootstrap.py живёт в корне репо (ROOT); импорт не вызывает main() (она под if __name__).
"""
import sys
from pathlib import Path

# Вставляем корень репо в путь, чтобы `import bootstrap` нашёл bootstrap.py
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402


# ---------------------------------------------------------------------------
# Вспомогательный парсер KEY=value — воспроизводит логику run.load_env
# ---------------------------------------------------------------------------

def _parse_env(text: str) -> dict[str, str]:
    """Парсит текст .ai1c.env: пропускает # и пустые строки, делит по первому '='."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Тесты env_file_contents
# ---------------------------------------------------------------------------

_DSN = "postgresql://ai1c:ai1c@127.0.0.1:5432/ai1c"
_DB = "/opt/ai1c/app/agentmon.db"


class TestEnvFileContents:
    def test_contains_dsn(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert f"AGENTMON_DSN={_DSN}" in text

    def test_contains_db(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert f"AGENTMON_DB={_DB}" in text

    def test_default_mode_is_host(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert "AI1C_MONITOR_MODE=host" in text

    def test_explicit_mode_docker(self):
        text = bootstrap.env_file_contents(_DSN, _DB, mode="docker")
        assert "AI1C_MONITOR_MODE=docker" in text

    def test_ends_with_newline(self):
        text = bootstrap.env_file_contents(_DSN, _DB)
        assert text.endswith("\n")

    def test_round_trip_parse_three_keys(self):
        """Текст корректно разбирается парсером KEY=value — все три ключа присутствуют."""
        text = bootstrap.env_file_contents(_DSN, _DB, mode="host")
        env = _parse_env(text)
        assert env["AGENTMON_DSN"] == _DSN
        assert env["AGENTMON_DB"] == _DB
        assert env["AI1C_MONITOR_MODE"] == "host"

    def test_round_trip_parse_docker_mode(self):
        text = bootstrap.env_file_contents(_DSN, _DB, mode="docker")
        env = _parse_env(text)
        assert env["AI1C_MONITOR_MODE"] == "docker"

    def test_no_spaces_around_equals(self):
        """KEY=value без пробелов вокруг '=' для совместимости с run.load_env."""
        text = bootstrap.env_file_contents(_DSN, _DB)
        for line in text.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            assert " = " not in line, f"пробелы вокруг '=' в строке: {line!r}"
