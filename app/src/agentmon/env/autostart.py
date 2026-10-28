"""User-level автозапуск процессов под Windows/Linux/macOS (без root/admin)."""
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape


def _q(a):
    """Кавычки вокруг аргумента, если есть пробел."""
    return f'"{a}"' if " " in a else a


def windows_wrapper(argv, env):
    """Текст .cmd: выставляет env и запускает процесс."""
    lines = ["@echo off"]
    for k, v in env.items():
        lines.append(f'set "{k}={v}"')
    lines.append(" ".join(_q(a) for a in argv))
    return "\r\n".join(lines) + "\r\n"


def systemd_unit(argv, env, description):
    """Текст systemd user-unit."""
    def _esc_val(v):
        return v.replace("\\", "\\\\").replace('"', '\\"')
    env_lines = "\n".join(f'Environment="{k}={_esc_val(v)}"' for k, v in env.items())
    exec_start = " ".join(_q(a) for a in argv)
    return (f"[Unit]\nDescription={description}\n\n"
            f"[Service]\n{env_lines}\nExecStart={exec_start}\n"
            f"Restart=on-failure\n\n"
            f"[Install]\nWantedBy=default.target\n")


def launchd_plist(label, argv, env):
    """Текст LaunchAgent plist."""
    args = "".join(f"    <string>{_xml_escape(a)}</string>\n" for a in argv)
    envs = "".join(f"    <key>{_xml_escape(k)}</key><string>{_xml_escape(v)}</string>\n"
                   for k, v in env.items())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            f'  <key>Label</key><string>{label}</string>\n'
            f'  <key>ProgramArguments</key><array>\n{args}  </array>\n'
            f'  <key>EnvironmentVariables</key><dict>\n{envs}  </dict>\n'
            '  <key>RunAtLoad</key><true/>\n'
            '  <key>KeepAlive</key><true/>\n'
            '</dict></plist>\n')


def _run_logged(run, cmd, log, *, check=True):
    res = run(cmd, capture_output=True, text=True)
    rc = getattr(res, "returncode", 0)
    log.append(f"$ {' '.join(cmd)} → код {rc}")
    if check and rc != 0:
        err = (getattr(res, "stderr", "") or "").strip()
        raise ValueError(f"команда не выполнена ({' '.join(cmd)}): {err}")
    return res


def _install_linux(name, argv, env, state_dir, home, run):
    log = []
    unit_dir = Path(home) / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / f"{name}.service"
    unit_path.write_text(systemd_unit(argv, env, name), encoding="utf-8")
    log.append(f"Юнит: {unit_path}")
    _run_logged(run, ["systemctl", "--user", "daemon-reload"], log)
    _run_logged(run, ["systemctl", "--user", "enable", "--now", name], log)
    # best-effort: пережить ребут без входа
    _run_logged(run, ["loginctl", "enable-linger"], log, check=False)
    return log


def _install_windows(name, argv, env, state_dir, home, run):
    log = []
    wrapper = Path(state_dir) / f"{name}.cmd"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(windows_wrapper(argv, env), encoding="utf-8")
    log.append(f"Обёртка: {wrapper}")
    _run_logged(run, ["schtasks", "/Create", "/SC", "ONLOGON",
                      "/TN", name, "/TR", f'"{wrapper}"', "/F"], log)
    _run_logged(run, ["schtasks", "/Run", "/TN", name], log)
    return log


def _install_macos(name, argv, env, state_dir, home, run):
    log = []
    agents = Path(home) / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"{name}.plist"
    plist.write_text(launchd_plist(name, argv, env), encoding="utf-8")
    log.append(f"LaunchAgent: {plist}")
    _run_logged(run, ["launchctl", "unload", str(plist)], log, check=False)
    _run_logged(run, ["launchctl", "load", "-w", str(plist)], log)
    return log


def install_and_start(name, argv, *, env, state_dir, home=None,
                      run=subprocess.run, platform_name=None):
    """Зарегистрировать автозапуск процесса (user-level) и стартовать сразу."""
    home = Path(home) if home is not None else Path.home()
    pf = platform_name or sys.platform
    if pf.startswith("win"):
        return _install_windows(name, argv, env, state_dir, home, run)
    if pf.startswith("linux"):
        return _install_linux(name, argv, env, state_dir, home, run)
    if pf == "darwin":
        return _install_macos(name, argv, env, state_dir, home, run)
    raise ValueError(f"автозапуск не поддержан на платформе {pf}")
