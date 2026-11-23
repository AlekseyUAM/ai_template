"""Обёртки deploy/claude: код возврата claude должен доходить до вызывающего."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BAT_WRAPPERS = [
    REPO / "deploy" / "claude" / "claude-local.bat",
    REPO / "deploy" / "claude" / "claude-ds.bat",
]


@pytest.mark.skipif(os.name != "nt", reason="batch-обёртки Windows")
@pytest.mark.parametrize("wrapper", BAT_WRAPPERS, ids=lambda path: path.name)
def test_bat_wrapper_propagates_claude_exit_code(wrapper, tmp_path):
    # where.exe завершается с кодом 1, если ничего не нашёл. Под именем
    # claude.exe он имитирует упавший агент и выигрывает у реального claude
    # в PATH.
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    shutil.copy2(Path(system_root) / "System32" / "where.exe",
                 tmp_path / "claude.exe")
    env = dict(os.environ)
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    env["DEEPSEEK_API_KEY"] = "test-key"
    proc = subprocess.run(
        ["cmd", "/c", str(wrapper), "--version"],
        env=env, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 1, (
        f"{wrapper.name}: код возврата claude потерян\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
