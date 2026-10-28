import pytest
from pathlib import Path
from agentmon.env import autostart as A


def test_systemd_unit_has_env_and_exec():
    unit = A.systemd_unit(["/opt/ci/bsl-indexer", "serve"],
                          {"CODE_INDEX_HOME": "/opt/ci", "MCP_HTTP_PORT": "8005"},
                          "ai1c code-index mcp")
    assert 'Environment="CODE_INDEX_HOME=/opt/ci"' in unit
    assert 'Environment="MCP_HTTP_PORT=8005"' in unit
    assert "ExecStart=/opt/ci/bsl-indexer serve" in unit
    assert "WantedBy=default.target" in unit


def test_launchd_plist_has_args_and_env():
    pl = A.launchd_plist("ai1c.ci.mcp", ["/opt/ci/bsl-indexer", "serve"],
                         {"MCP_HTTP_PORT": "8005"})
    assert "<string>/opt/ci/bsl-indexer</string>" in pl
    assert "<string>serve</string>" in pl
    assert "<key>MCP_HTTP_PORT</key><string>8005</string>" in pl
    assert "<key>RunAtLoad</key><true/>" in pl


def test_windows_wrapper_sets_env_and_runs():
    cmd = A.windows_wrapper(["C:\\ci\\bsl-indexer.exe", "serve"],
                            {"MCP_HTTP_PORT": "8005"})
    assert 'set "MCP_HTTP_PORT=8005"' in cmd
    assert "bsl-indexer.exe" in cmd


def test_install_and_start_linux(tmp_path, monkeypatch):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    home = tmp_path / "home"
    log = A.install_and_start(
        "ai1c-code-index-mcp-7", ["/opt/ci/bsl-indexer", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(tmp_path / "ci"),
        home=home, run=run, platform_name="linux")
    unit = home / ".config" / "systemd" / "user" / "ai1c-code-index-mcp-7.service"
    assert unit.exists()
    assert any("systemctl" in c and "enable" in c for c in calls)
    assert any("ExecStart" in l or "systemctl" in l or "юнит" in l.lower()
               for l in log)


def test_install_and_start_windows(tmp_path, monkeypatch):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    state = tmp_path / "ci"
    A.install_and_start(
        "ai1c-code-index-mcp-7", ["C:\\ci\\bsl-indexer.exe", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(state),
        home=tmp_path / "home", run=run, platform_name="win32")
    assert (state / "ai1c-code-index-mcp-7.cmd").exists()
    assert any("schtasks" in c and "/Create" in c for c in calls)
    assert any("schtasks" in c and "/Run" in c for c in calls)


def test_install_and_start_macos(tmp_path):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    home = tmp_path / "home"
    A.install_and_start(
        "ai1c-code-index-mcp-7", ["/opt/ci/bsl-indexer", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(tmp_path / "ci"),
        home=home, run=run, platform_name="darwin")
    plist = home / "Library" / "LaunchAgents" / "ai1c-code-index-mcp-7.plist"
    assert plist.exists()
    assert any("launchctl" in c for c in calls)


def test_install_and_start_unsupported(tmp_path):
    with pytest.raises(ValueError, match="платформ"):
        A.install_and_start("n", ["x"], env={}, state_dir=str(tmp_path),
                            run=lambda *a, **k: None, platform_name="sunos5")
