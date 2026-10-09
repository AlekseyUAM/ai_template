"""Запуск дочернего процесса с записью его кода выхода в файл (для detached-прогонов)."""
import subprocess
import sys
from pathlib import Path


def run(exit_file: str, cmd: list) -> int:
    try:
        code = subprocess.call(cmd)
    except OSError:
        code = 127            # команда не запустилась
    Path(exit_file).write_text(str(code), encoding="utf-8")
    return code


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3 or argv[1] != "--":
        raise SystemExit("использование: run_wrapper <exit_file> -- <cmd...>")
    raise SystemExit(run(argv[0], argv[2:]))


if __name__ == "__main__":
    main()
