"""Load the project configuration (.1c-devbase.json) and auto-detect the 1C platform."""

import json
import platform
from dataclasses import dataclass
from pathlib import Path

import click


CONFIG_FILENAME = ".1c-devbase.json"

# Standard 1C platform search paths per OS
PLATFORM_SEARCH_PATHS = {
    "Linux": [
        Path("/opt/1cv8/x86_64"),
        Path("/opt/1C/v8.3/x86_64"),
    ],
    "Darwin": [
        Path("/opt/1cv8/x86_64"),
    ],
    "Windows": [
        Path(r"C:\Program Files\1cv8"),
        Path(r"C:\Program Files (x86)\1cv8"),
    ],
}


@dataclass
class Config:
    """1C connection configuration."""

    platform_path: str = ""
    connection_type: str = "file"  # "file" or "server"
    connection_path: str = ""      # path to the file infobase
    server: str = ""               # server host
    base: str = ""                 # infobase name on the server
    user: str = ""
    password: str = ""
    cf_dir: str = "src/cf"
    cfe_dir: str = "src/cfe"
    log_dir: str = "logs"

    def validate(self) -> list[str]:
        """Validate the configuration. Returns a list of errors."""
        errors: list[str] = []

        if not self.platform_path:
            errors.append("Не задан путь к платформе 1С (platform_path). "
                          "Укажите его в .1c-devbase.json или установите платформу в стандартный каталог.")
        elif not Path(self.platform_path).exists():
            errors.append(f"Исполняемый файл платформы не найден: {self.platform_path}")

        if self.connection_type == "file":
            if not self.connection_path:
                errors.append("Не указан путь к файловой базе (connection.path).")
        elif self.connection_type == "server":
            if not self.server:
                errors.append("Не указан сервер (connection.server).")
            if not self.base:
                errors.append("Не указано имя базы на сервере (connection.base).")
        else:
            errors.append(f"Неизвестный тип подключения: {self.connection_type}. "
                          "Допустимые значения: file, server.")

        return errors


def find_platform_binary() -> str | None:
    """Auto-detect the path to the 1cv8 executable."""
    system = platform.system()
    search_dirs = PLATFORM_SEARCH_PATHS.get(system, [])

    for base_dir in search_dirs:
        if not base_dir.is_dir():
            continue
        # Find the newest version (directory-name sort follows version order)
        versions = sorted(base_dir.iterdir(), reverse=True)
        for version_dir in versions:
            if system == "Windows":
                binary = version_dir / "bin" / "1cv8.exe"
            else:
                binary = version_dir / "1cv8"
                if not binary.exists():
                    binary = version_dir / "bin" / "1cv8"
            if binary.exists():
                return str(binary)
    return None


def load_config(start_dir: Path | None = None) -> Config:
    """Load the configuration from .1c-devbase.json.

    Searches for the config file upward from start_dir (cwd by default).
    """
    if start_dir is None:
        start_dir = Path.cwd()

    config_file = _find_config_file(start_dir)
    cfg = Config()

    if config_file:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        cfg.platform_path = data.get("platform_path", "")
        cfg.user = data.get("user", "")
        cfg.password = data.get("password", "")
        cfg.cf_dir = data.get("cf_dir", cfg.cf_dir)
        cfg.cfe_dir = data.get("cfe_dir", cfg.cfe_dir)
        cfg.log_dir = data.get("log_dir", cfg.log_dir)

        conn = data.get("connection", {})
        cfg.connection_type = conn.get("type", "file")
        if cfg.connection_type == "file":
            cfg.connection_path = conn.get("path", "")
        else:
            cfg.server = conn.get("server", "")
            cfg.base = conn.get("base", "")
    else:
        click.echo("Файл .1c-devbase.json не найден, используются значения по умолчанию.", err=True)

    # Auto-detect the platform if not set explicitly
    if not cfg.platform_path:
        auto = find_platform_binary()
        if auto:
            cfg.platform_path = auto
            click.echo(f"Автоопределена платформа: {auto}")

    return cfg


def _find_config_file(start_dir: Path) -> Path | None:
    """Search for .1c-devbase.json upward through the directory tree."""
    current = start_dir.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None
