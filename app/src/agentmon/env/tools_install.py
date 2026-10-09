import subprocess
import sys
from pathlib import Path


def install_tools(config, *, run=subprocess.run) -> None:
    scripts = Path(config.project_dir) / ".claude" / "skills" / "1c-batch" / "scripts"
    cmds = [
        [sys.executable, "-m", "pip", "install", str(scripts)],
        [sys.executable, "-m", "pip", "install", "lxml", "Pillow", "psutil"],
    ]
    for cmd in cmds:
        r = run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "установка инструментов не удалась")
