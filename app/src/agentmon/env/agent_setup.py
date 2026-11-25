"""Подготовка агента внутри docker-контейнера: обёртка, ключ, Strata."""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
WRAPPERS = {"claude-ds": "claude-ds.sh", "claude-local": "claude-local.sh"}
CLAUDE_BASENAMES = {"claude", "claude.exe", "claude.cmd", "claude.bat"}


class AgentSetupError(RuntimeError):
    """Ошибка подготовки агента (сообщение — для пользователя)."""


def split_command(command: str) -> list[str]:
    cmd = (command or "").strip()
    if not cmd:
        raise AgentSetupError("пустая команда агента")
    posix = os.name != "nt" and "\\" not in cmd
    try:
        argv = shlex.split(cmd, posix=posix)
    except ValueError as exc:
        raise AgentSetupError(f"команда агента: {exc}") from None
    if not posix:
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a
                for a in argv]
    argv = [a for a in argv if a]
    if not argv:
        raise AgentSetupError("пустая команда агента")
    return argv


def _basename(executable: str) -> str:
    return executable.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def container_command(command: str) -> str:
    """Команда для docker exec: хостовый путь заменяется именем из образа."""
    argv = split_command(command)
    base = _basename(argv[0])
    if base.lower() in CLAUDE_BASENAMES:
        argv = ["claude", *argv[1:]]
    elif base in WRAPPERS:
        argv = [base, *argv[1:]]
    else:
        return command
    return " ".join(shlex.quote(a) for a in argv)


def container_home(prov) -> str:
    try:
        res = prov.run(["sh", "-c", 'printf %s "$HOME"'])
        home = (getattr(res, "stdout", "") or "").strip()
        if getattr(res, "returncode", 1) == 0 and home.startswith("/"):
            return home.rstrip("/") or "/root"
    except Exception:                                  # noqa: BLE001
        pass
    return "/root"


def _copy_wrapper(prov, *, name, repo_root, log):
    src = Path(repo_root) / "deploy" / "claude" / WRAPPERS[name]
    if not src.is_file():
        raise AgentSetupError(f"не найдена обёртка {src}")
    text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    dst = f"/usr/local/bin/{name}"
    prov.write_text(dst, text)
    res = prov.run(["chmod", "0755", dst])
    if getattr(res, "returncode", 1) != 0:
        raise AgentSetupError(
            f"не удалось сделать обёртку исполняемой: {dst}: "
            f"{(getattr(res, 'stderr', '') or '').strip()}")
    log(f"✓ обёртка агента: {dst}")


def _deepseek_token(*, key_path=None, environ=None) -> str:
    env = environ if environ is not None else os.environ
    token = (env.get("DEEPSEEK_API_KEY") or "").strip()
    if token:
        return token
    path = Path(key_path) if key_path is not None else (
        Path.home() / ".config" / "deepseek" / "key")
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if not token:
        raise AgentSetupError(
            "не найден ключ DeepSeek: задайте DEEPSEEK_API_KEY или положите "
            f"ключ в {path}")
    return token


def _write_key(prov, *, token, log):
    path = f"{container_home(prov)}/.config/deepseek/key"
    prov.write_text(path, token + "\n")
    res = prov.run(["chmod", "0600", path])
    if getattr(res, "returncode", 1) != 0:
        raise AgentSetupError(f"не удалось выставить права на ключ: {path}")
    log(f"✓ ключ DeepSeek: {path}")


def _write_strata_settings(prov, *, project_dir, strata_cmd, fetch_strata,
                           build_settings, log):
    env = fetch_strata(strata_cmd)
    settings = build_settings(env)
    path = f"{str(project_dir).rstrip('/')}/.claude/settings.local.json"
    prov.write_text(path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    log(f"✓ настройки Strata: {path}")


def prepare(prov, project_dir, command, *, repo_root=REPO_ROOT, key_path=None,
            environ=None, strata_cmd="strata", fetch_strata=None,
            build_settings=None, log=print) -> None:
    """Скопировать в контейнер всё, что нужно команде агента."""
    argv = split_command(command)
    base = _basename(argv[0])
    if base.lower() in CLAUDE_BASENAMES:
        log("✓ агент claude уже в образе")
        return
    if base not in WRAPPERS:
        raise AgentSetupError(
            "для docker-проекта поддерживаются команды claude, claude-ds, "
            f"claude-local (получено {base!r})")
    _copy_wrapper(prov, name=base, repo_root=repo_root, log=log)
    if base == "claude-ds":
        _write_key(prov, token=_deepseek_token(key_path=key_path,
                                               environ=environ), log=log)
        return
    if fetch_strata is None or build_settings is None:
        from .bench_setup import build_strata_settings, fetch_strata_env
        fetch_strata = fetch_strata or fetch_strata_env
        build_settings = build_settings or build_strata_settings
    _write_strata_settings(prov, project_dir=project_dir,
                           strata_cmd=strata_cmd,
                           fetch_strata=fetch_strata,
                           build_settings=build_settings, log=log)
