import json

from .project_checks import infer_db_kind


def git_init_project(prov, project_dir, *, config=None) -> None:
    """Инициализирует git в КОРНЕ каталога проекта.

    Если передан config — настраивает user.name/user.email из идентификатора и
    почты разработчика.
    """
    root = str(project_dir)
    prov.mkdirs([root])
    if not prov.exists(f"{root}/.git"):
        res = prov.run(["git", "init"], cwd=root)
        if res.returncode != 0:
            raise RuntimeError(res.stderr or "git init не удался")
    if config is not None:
        if getattr(config, "developer_id", ""):
            prov.run(["git", "config", "user.name", config.developer_id], cwd=root)
        if getattr(config, "developer_email", ""):
            prov.run(["git", "config", "user.email", config.developer_email], cwd=root)
    if not prov.exists(f"{root}/.gitignore"):
        prov.write_text(f"{root}/.gitignore", "logs/\n*.log\n")


def git_commit_all(prov, project_dir, message="init", *, config=None) -> None:
    """Делает `git add .` и коммит всех файлов в КОРНЕ каталога проекта.

    Идентичность автора передаётся инлайн через `-c user.name`/`-c user.email`,
    чтобы коммит не падал с «Author identity unknown» на свежем репозитории.
    Имя/почта берутся из config (с запасными значениями ai1c/ai1c@local).
    Ситуация «нечего коммитить» считается успехом.
    """
    root = str(project_dir)
    prov.run(["git", "add", "."], cwd=root)
    name = getattr(config, "developer_id", "") or "ai1c"
    email = getattr(config, "developer_email", "") or "ai1c@local"
    res = prov.run(["git", "-c", f"user.name={name}", "-c", f"user.email={email}",
                    "commit", "-m", message], cwd=root)
    if res.returncode != 0:
        combined = ((res.stdout or "") + (res.stderr or "")).lower()
        if "nothing to commit" in combined:
            return                      # нечего коммитить — это не ошибка
        raise RuntimeError(res.stderr or "git commit не удался")


def _platform_path(prov, platform_dir: str) -> str:
    # 1c-batch ждёт путь к бинарнику 1cv8 (не каталог). Пустая строка → CLI
    # определит платформу сам (find_platform_binary).
    if not platform_dir:
        return ""
    if prov.is_file(platform_dir):
        return platform_dir
    for name in ("1cv8", "1cv8.exe"):
        cand = f"{platform_dir}/{name}"
        if prov.exists(cand):
            return cand
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


def write_devbase(prov, config, *, user: str = "", password: str = "") -> None:
    db_kind = getattr(config, "db_kind", "") or infer_db_kind(config.db_connection)
    conn = _parse_connection(db_kind, config.db_connection)
    data = {
        "platform_path": _platform_path(prov, config.platform_dir),
        "connection": conn,
        "user": user,
        "password": password,
        "cf_dir": "src/cf",
        "cfe_dir": "src/cfe",
        "log_dir": "logs",
    }
    prov.write_text(
        f"{config.project_dir}/.1c-devbase.json",
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    )
