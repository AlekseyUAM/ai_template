"""TCP/HTTP-пробы без зависимостей от bench_setup."""
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse


def url_host_port(url: str) -> tuple[str, int]:
    """Хост и порт URL; ValueError на некорректном порту (http://host:abc)."""
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise ValueError(f"некорректный порт в URL: {url}")
    return parsed.hostname or "", port


def default_tcp_ok(url: str, timeout: float = 3.0) -> bool:
    """True, если TCP-соединение с хостом/портом URL устанавливается."""
    host, port = url_host_port(url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def default_http_ok(url: str, timeout: float = 5.0) -> bool:
    """Любой HTTP-ответ (включая 4xx) означает, что сервис слушает."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "ai1c-agentmon"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
