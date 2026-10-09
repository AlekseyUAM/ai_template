import json
import subprocess
from pathlib import Path

from .project_checks import infer_db_kind


def git_init_project(project_dir, *, config=None, run=subprocess.run) -> None:
    """Инициализирует git в КОРНЕ каталога проекта.

    Если передан config — настраивает user.name/user.email из идентификатора и
    почты разработчика.
    """
    root = Path(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        r = run(["git", "init"], cwd=str(root), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "git init не удался")
    if config is not None:
        if getattr(config, "developer_id", ""):
            run(["git", "config", "user.name", config.developer_id],
                cwd=str(root), capture_output=True, text=True)
        if getattr(config, "developer_email", ""):
            run(["git", "config", "user.email", config.developer_email],
                cwd=str(root), capture_output=True, text=True)
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text("logs/\n*.log\n", encoding="utf-8")


def git_commit_all(project_dir, message="init", *, config=None,
                   run=subprocess.run) -> None:
    """Делает `git add .` и коммит всех файлов в КОРНЕ каталога проекта.

    Идентичность автора передаётся инлайн через `-c user.name`/`-c user.email`,
    чтобы коммит не падал с «Author identity unknown» на свежем репозитории.
    Имя/почта берутся из config (с запасными значениями ai1c/ai1c@local).
    Ситуация «нечего коммитить» считается успехом.
    """
    root = Path(project_dir)
    run(["git", "add", "."], cwd=str(root), capture_output=True, text=True)
    name = getattr(config, "developer_id", "") or "ai1c"
    email = getattr(config, "developer_email", "") or "ai1c@local"
    r = run(["git", "-c", f"user.name={name}", "-c", f"user.email={email}",
             "commit", "-m", message],
            cwd=str(root), capture_output=True, text=True)
    if r.returncode != 0:
        combined = ((r.stdout or "") + (r.stderr or "")).lower()
        if "nothing to commit" in combined:
            return                      # нечего коммитить — это не ошибка
        raise RuntimeError(r.stderr or "git commit не удался")


def _platform_path(platform_dir: str) -> str:
    # 1c-batch ждёт путь к бинарнику 1cv8 (не каталог). Пустая строка → CLI
    # определит платформу сам (find_platform_binary).
    if not platform_dir:
        return ""
    p = Path(platform_dir)
    if p.is_file():
        return str(p)
    for name in ("1cv8", "1cv8.exe"):
        cand = p / name
        if cand.exists():
            return str(cand)
    return ""


def _parse_connection(db_kind: str, connection: str) -> dict:
    conn = connection or ""
    if db_kind == "file":
        path = conn
        if "=" in conn and conn.split("=", 1)[0].strip().lower() == "file":
            path = conn.split("=", 1)[1].strip().strip('"')
        return {"type": "file", "path": path}
    # серверная: формат Srvr=...;Ref=... или server/base
    srvr = ref = ""
    for part in conn.replace(";", "\n").splitlines():
        key, _, val = part.partition("=")
        key = key.strip().lower(); val = val.strip().strip('"')
        if key == "srvr":
            srvr = val
        elif key == "ref":
            ref = val
    if srvr or ref:
        return {"type": "server", "server": srvr, "base": ref}
    server, sep, base = conn.rpartition("/")
    if not sep:
        server, base = conn, ""
    return {"type": "server", "server": server, "base": base}


def write_devbase(config, *, user: str = "", password: str = "") -> None:
    db_kind = getattr(config, "db_kind", "") or infer_db_kind(config.db_connection)
    conn = _parse_connection(db_kind, config.db_connection)
    data = {
        "platform_path": _platform_path(config.platform_dir),
        "connection": conn,
        "user": user,
        "password": password,
        "cf_dir": "src/cf",
        "cfe_dir": "src/cfe",
        "log_dir": "logs",
    }
    (Path(config.project_dir) / ".1c-devbase.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
