"""Скачивание готового бинаря bsl-indexer с GitHub Releases под текущий хост."""
import io
import json
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

GH_LATEST = "https://api.github.com/repos/Regsorm/code-index-mcp/releases/latest"


def host_asset_key():
    """Маркеры ассета bsl-indexer под хост или None, если платформа не из
    публикуемых upstream (Windows x64 / Linux x64 / macOS arm64)."""
    machine = platform.machine().lower()
    is_x64 = machine in ("x86_64", "amd64", "x64")
    is_arm64 = machine in ("arm64", "aarch64")
    if sys.platform.startswith("win") and is_x64:
        return ("windows", "x64")
    if sys.platform.startswith("linux") and is_x64:
        return ("linux", "x64")
    if sys.platform == "darwin" and is_arm64:
        return ("macos", "arm64")
    return None


def resolve_asset(release_json, markers):
    """(name, url) ассета bsl-indexer под платформу из JSON релиза."""
    os_m, arch_m = markers
    for a in release_json.get("assets", []):
        low = a["name"].lower()
        if "bsl-indexer" in low and os_m in low and arch_m in low:
            return a["name"], a["browser_download_url"]
    names = [a["name"] for a in release_json.get("assets", [])]
    raise ValueError(
        f"в релизе нет ассета bsl-indexer для {os_m}-{arch_m}; доступны: {names}")


def _default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai1c-agentmon"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _host_markers(platform_name):
    """markers по явному platform_name (для тестов) или по хосту.

    При явном platform_name доверяем единственной публикуемой upstream арке на
    каждую ОС (Windows/Linux — x64, macOS — arm64)."""
    if platform_name is None:
        return host_asset_key()
    if platform_name.startswith("win"):
        return ("windows", "x64")
    if platform_name.startswith("linux"):
        return ("linux", "x64")
    if platform_name == "darwin":
        return ("macos", "arm64")
    return None


def _extract(blob, asset_name, dest):
    """Распаковать архив ассета в dest."""
    low = asset_name.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            zf.extractall(dest)
    elif low.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            tf.extractall(dest)
    else:
        raise ValueError(f"неизвестный формат архива: {asset_name}")


def _find_binary(dest, os_marker):
    """Найти исполняемый bsl-indexer в распакованном дереве."""
    want = "bsl-indexer.exe" if os_marker == "windows" else "bsl-indexer"
    for p in Path(dest).rglob("*"):
        if p.is_file() and p.name == want:
            return p
    raise ValueError(f"в архиве не найден {want}")


def download_binary(code_index_dir, *, fetch=_default_fetch, log=None,
                    platform_name=None):
    """Скачать bsl-indexer под хост в code_index_dir, вернуть путь к бинарю."""
    log = log or (lambda s: None)
    markers = _host_markers(platform_name)
    if markers is None:
        raise ValueError("платформа не поддерживается "
                         "(нужны Windows x64, Linux x64 или macOS arm64)")
    log(f"Определение релиза для {markers[0]}-{markers[1]}…")
    release = json.loads(fetch(GH_LATEST).decode("utf-8"))
    name, url = resolve_asset(release, markers)
    log(f"Скачивание {name}…")
    blob = fetch(url)
    dest = Path(code_index_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _extract(blob, name, dest)
    binary = _find_binary(dest, markers[0])
    if markers[0] != "windows":
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                     | stat.S_IXOTH)
    log(f"Бинарь установлен: {binary}")
    return binary
