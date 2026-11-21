"""Run 1cv8 processes - interactive and batch modes."""

import shlex
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click

from .config import Config


def _pdeathsig_preexec() -> None:
    """Linux: kill the child 1cv8 if the parent (wrapper) dies.

    Protection against orphaned Configurator processes: if the wrapper is
    killed by a timeout/signal, an unfinished restructure in the orphaned 1cv8
    may leave the infobase in the "Infobase structure error" state.
    PR_SET_PDEATHSIG=1 makes the kernel send SIGKILL to the child when the
    parent dies.
    """
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG = 1
    except Exception:
        pass


def _run_kwargs() -> dict:
    """subprocess.run parameters: tie the life of 1cv8 to the wrapper (Linux only)."""
    if sys.platform.startswith("linux"):
        return {"preexec_fn": _pdeathsig_preexec}
    return {}


def build_connection_args(cfg: Config) -> list[str]:
    """Build infobase connection arguments.

    Values are passed as separate argv items without literal quotes -
    the shell/list2cmdline adds them when needed. 1C receives the raw value.
    """
    if cfg.connection_type == "server":
        return ["/S", f"{cfg.server}/{cfg.base}"]
    return ["/F", cfg.connection_path]


def build_auth_args(cfg: Config) -> list[str]:
    """Build authentication arguments."""
    args: list[str] = []
    if cfg.user:
        args.extend(["/N", cfg.user])
    if cfg.password:
        args.extend(["/P", cfg.password])
    return args


def build_base_command(cfg: Config, mode: str) -> list[str]:
    """Build the base 1cv8 command line with common connection parameters.

    mode: "ENTERPRISE", "DESIGNER" or "CREATEINFOBASE"
    """
    cmd = [cfg.platform_path, mode]
    cmd.extend(build_connection_args(cfg))
    cmd.extend(build_auth_args(cfg))
    return cmd


def build_log_path(cfg: Config, command_name: str) -> Path:
    """Build the log file path for a batch command."""
    log_dir = Path(cfg.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{command_name}_{timestamp}.log"


def read_log(log_path: Path) -> str | None:
    """Read and return the contents of the log file (/Out)."""
    if not log_path.exists():
        return None
    try:
        # 1C may write in different encodings
        for encoding in ("utf-8-sig", "utf-8", "cp1251", "cp866"):
            try:
                return log_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return log_path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return None


def _echo_command(cmd: list[str]) -> None:
    """Print the command for the user - quote values only where needed."""
    click.echo(f"Запуск: {shlex.join(cmd)}")


def run_interactive(cfg: Config, mode: str, extra_args: list[str] | None = None,
                    wait: bool = False) -> int:
    """Run 1C in Enterprise/Configurator mode.

    mode: "ENTERPRISE" or "DESIGNER"
    wait=False - do not wait for completion (interactive app launch).
    wait=True  - wait for the session to finish (automated run: /C, /Execute).
                 Returns the process exit code.
    """
    errors = cfg.validate()
    if errors:
        for e in errors:
            click.echo(f"Ошибка: {e}", err=True)
        sys.exit(1)

    cmd = build_base_command(cfg, mode)
    if extra_args:
        cmd.extend(extra_args)

    _echo_command(cmd)
    if wait:
        # Wait for the session to finish so the caller knows the run is over
        # and does not start the next stage in parallel with a live session.
        return subprocess.run(cmd, **_run_kwargs()).returncode
    subprocess.Popen(cmd)
    return 0


def run_batch(cfg: Config, command_name: str, extra_args: list[str]) -> int:
    """Run 1C in batch mode (DESIGNER with /DisableStartupDialogs).

    Returns the process exit code.
    Logs the output (/Out) to a file and prints its contents on error.
    """
    errors = cfg.validate()
    if errors:
        for e in errors:
            click.echo(f"Ошибка: {e}", err=True)
        return 1

    log_path = build_log_path(cfg, command_name)

    cmd = build_base_command(cfg, "DESIGNER")
    cmd.append("/DisableStartupDialogs")
    cmd.extend(["/Out", str(log_path)])
    cmd.extend(extra_args)

    _echo_command(cmd)
    # No timeout: updating the DB configuration can take hours. _run_kwargs()
    # protects against orphaning when the wrapper dies (PR_SET_PDEATHSIG on Linux).
    result = subprocess.run(cmd, **_run_kwargs())

    # Read and print the log contents
    log_content = read_log(log_path)

    if result.returncode != 0:
        click.echo(f"Ошибка (код {result.returncode}). Лог: {log_path}", err=True)
        if log_content:
            click.echo("--- Содержимое лога ---", err=True)
            click.echo(log_content, err=True)
            click.echo("--- Конец лога ---", err=True)
    else:
        click.echo(f"Готово. Лог: {log_path}")
        if log_content and log_content.strip():
            click.echo(log_content)

    return result.returncode


def run_create_infobase(cfg: Config, path: str, extra_args: list[str] | None = None) -> int:
    """Create an infobase.

    Uses the special connection string syntax `File="..."` - this is **one**
    argv value; the quotes are part of 1C syntax here, not formatting.
    """
    if not cfg.platform_path:
        click.echo("Ошибка: Не задан путь к платформе 1С (platform_path).", err=True)
        return 1
    if '"' in path:
        click.echo('Ошибка: путь к базе не может содержать символ "', err=True)
        return 1

    cmd = [cfg.platform_path, "CREATEINFOBASE", f'File="{path}"']
    if extra_args:
        cmd.extend(extra_args)

    _echo_command(cmd)
    return subprocess.run(cmd).returncode
