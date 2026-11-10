"""Запуск дочернего процесса с записью его кода выхода в файл (для detached-прогонов)."""
import signal
import subprocess
import sys
from pathlib import Path


def _set_pdeathsig() -> None:
    """Linux: убить дочерний процесс, если wrapper погиб (OOM/SIGKILL).

    Без этого `claude` остаётся сиротой, монитор фиксирует прогон завершённым,
    а в каталоге проекта продолжает работать невидимый агент.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)      # PR_SET_PDEATHSIG = 1
    except Exception:
        pass


def run(exit_file: str, cmd: list) -> int:
    kwargs = {}
    if sys.platform.startswith("linux"):
        # preexec_fn допустим: у wrapper нет потоков.
        kwargs["preexec_fn"] = _set_pdeathsig
    try:
        proc = subprocess.Popen(cmd, **kwargs)
        code = proc.wait()
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
