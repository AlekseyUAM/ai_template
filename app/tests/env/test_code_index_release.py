import io
import json

import pytest
from agentmon.env import code_index_release as R

_RELEASE = {"assets": [
    {"name": "code-index-linux-x64.tar.gz", "browser_download_url": "u1"},
    {"name": "bsl-indexer-linux-x64.tar.gz", "browser_download_url": "u2"},
    {"name": "bsl-indexer-windows-x64.zip", "browser_download_url": "u3"},
    {"name": "bsl-indexer-macos-arm64.tar.gz", "browser_download_url": "u4"},
]}


def test_host_asset_key_linux_x64(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    monkeypatch.setattr(R.platform, "machine", lambda: "x86_64")
    assert R.host_asset_key() == ("linux", "x64")


def test_host_asset_key_macos_arm64(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "darwin")
    monkeypatch.setattr(R.platform, "machine", lambda: "arm64")
    assert R.host_asset_key() == ("macos", "arm64")


def test_host_asset_key_unsupported(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    monkeypatch.setattr(R.platform, "machine", lambda: "armv7l")
    assert R.host_asset_key() is None


def test_resolve_asset_picks_bsl_indexer():
    name, url = R.resolve_asset(_RELEASE, ("linux", "x64"))
    assert name == "bsl-indexer-linux-x64.tar.gz" and url == "u2"


def test_resolve_asset_missing_raises():
    with pytest.raises(ValueError, match="bsl-indexer"):
        R.resolve_asset({"assets": []}, ("linux", "x64"))


def _zip_bytes(names):
    buf = io.BytesIO()
    import zipfile as z
    with z.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, b"BINDATA")
    return buf.getvalue()


def test_download_binary_extracts_and_returns_path(tmp_path, monkeypatch):
    def fetch(url):
        if url == R.GH_LATEST:
            return json.dumps(_RELEASE).encode("utf-8")
        return _zip_bytes(["bsl-indexer.exe", "README.txt"])
    dest = tmp_path / "ci"
    path = R.download_binary(str(dest), fetch=fetch, platform_name="win32")
    assert path.name == "bsl-indexer.exe"
    assert path.exists()


def test_download_binary_unsupported_platform(tmp_path):
    with pytest.raises(ValueError, match="платформ"):
        R.download_binary(str(tmp_path), fetch=lambda u: b"", platform_name="sunos5")
