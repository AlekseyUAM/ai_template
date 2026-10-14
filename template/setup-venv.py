#!/usr/bin/env python
"""Подъём изолированного .venv проекта с зависимостями навыков (кроссплатформенно).

Одна команда:  python setup-venv.py            (рантайм-зависимости)
               python setup-venv.py --dev      (+ инструменты для юнит-тестов)

При развёртывании окружения .venv создаётся автоматически. Этот скрипт нужен на
свежем клоне (где .venv в .gitignore и отсутствует) либо чтобы доустановить
зависимости после правок requirements.txt. Идемпотентен: существующий .venv
переиспользуется, pip install обновляет недостающее.

Запускается системным python — сам не зависит от пакетов окружения.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def main() -> None:
    dev = "--dev" in sys.argv[1:]
    req = ROOT / ("requirements-dev.txt" if dev else "requirements.txt")
    if not req.is_file():
        print(f"Не найден {req.name} рядом с setup-venv.py", file=sys.stderr)
        sys.exit(1)

    if not VENV.is_dir():
        print(f"[setup] создаю {VENV.name}")
        try:
            subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
        except subprocess.CalledProcessError:
            print("Не удалось создать venv. На Debian/Ubuntu: "
                  "sudo apt install python3-venv", file=sys.stderr)
            sys.exit(1)

    py = str(venv_python())
    print(f"[setup] ставлю зависимости из {req.name}")
    subprocess.run([py, "-m", "pip", "install", "--upgrade", "pip"],
                   stdout=subprocess.DEVNULL, check=True)
    subprocess.run([py, "-m", "pip", "install", "-r", str(req)], check=True)
    print(f"[setup] готово: {VENV}")


if __name__ == "__main__":
    main()
