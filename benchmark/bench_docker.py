"""Docker-размещение benchmark-проекта: всё внутри контейнера.

Проект живёт в именованном томе `<контейнер>-work`, смонтированном в
`/workspace`; code-index — в томе `<контейнер>-codeindex` (`/code-index`) и
запускается внутри контейнера. Bind-mount'ами остаются только вспомогательные
каталоги: репозиторий template (аналитику нужен каталог `template`, оттуда
же берутся `benchmark/cf` и `.dt`), HOME агента
(`benchmark/.bench-claude`), обёртка claude-ds, ключ DeepSeek и лицензии 1С.

Хост-раннер обращается к файлам проекта только через `docker exec`
(чтение/запись/снапшоты), поэтому проект целиком принадлежит контейнеру.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from agentmon.backends.docker import _DockerContainer, container_name

#: Каталог-«домашняя папка» агента на хосте (монтируется как CONTAINER_HOME).
BENCH_CLAUDE_HOME = ".bench-claude"
#: HOME внутри контейнера (host-каталог benchmark/.bench-claude).
CONTAINER_HOME = "/home/uam"
#: Каталог code-index внутри контейнера (именованный том).
CODE_INDEX_HOME = "/code-index"


# ─── Идентификация и спецификация контейнера ────────────────────────────────

def container_name_for(project_dir) -> str:
    """Имя контейнера от пути проекта внутри контейнера (/workspace)."""
    return container_name(str(project_dir))


def bench_claude_home(repo_root: Path) -> Path:
    return Path(repo_root) / "benchmark" / BENCH_CLAUDE_HOME


def sessions_root(repo_root: Path) -> Path:
    """Каталог, где claude в контейнере хранит projects/<session>.jsonl."""
    return bench_claude_home(repo_root) / ".claude" / "projects"


def host_argv(cmd: str) -> list[str]:
    """Разобрать AGENTMON_CLAUDE_CMD в argv с полным путём (как на хосте)."""
    bench_dir = Path(__file__).resolve().parent
    if str(bench_dir) not in sys.path:
        sys.path.insert(0, str(bench_dir))
    from claude_proc import resolve_command
    return resolve_command(cmd)


def _inner_command(argv: list[str]) -> tuple[str, list[str]]:
    """Команда внутри контейнера → (путь запуска, доп. спецификации -v)."""
    exe = Path(argv[0])
    home = str(Path.home())
    if str(exe).startswith(home + os.sep):
        target = f"/usr/local/bin/{exe.name}"
        return target, [f"{exe}:{target}:ro"]
    return exe.name, []


def _host_name_args() -> list[str]:
    """Прописать имя хоста в /etc/hosts контейнера (адрес менеджера 1С)."""
    try:
        name = socket.gethostname()
        ip = socket.gethostbyname(name)
    except OSError:
        return []
    return ["--add-host", f"{name}:{ip}"]


def _run_flags() -> list[str]:
    """Флаги `docker run`: host-сеть и хостовый uid/gid."""
    flags = ["--network", "host"]
    if os.name != "nt":
        flags += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return flags


def extra_volumes(repo_root: Path,
                  host_cmd_argv: list[str] | None = None) -> list[str]:
    """Вспомогательные bind-mount'ы (не файлы проекта)."""
    repo = str(Path(repo_root).resolve())
    vols = [f"{repo}:{repo}"]          # template, benchmark/cf, .dt, аналитик
    key = Path.home() / ".config" / "deepseek" / "key"
    if key.is_file():
        vols.append(f"{key}:{CONTAINER_HOME}/.config/deepseek/key:ro")
    licenses = Path("/var/1C/licenses")
    if licenses.is_dir():
        vols.append(f"{licenses}:{licenses}")
    if host_cmd_argv:
        _, cmd_vols = _inner_command(host_cmd_argv)
        vols.extend(cmd_vols)
    return vols


def _seed_claude_json(home: Path, project_dir) -> None:
    """Отметить проект доверенным для claude (HOME контейнера = bench-каталог)."""
    path = home / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    projects = data.setdefault("projects", {})
    projects.setdefault(str(project_dir), {})["hasTrustDialogAccepted"] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def container_for(project_dir, repo_root: Path, image: str,
                  host_cmd_argv: list[str] | None = None) -> _DockerContainer:
    """Описание контейнера benchmark-проекта (создаётся лениво в ensure)."""
    project = str(project_dir)
    name = container_name(project)
    home = bench_claude_home(repo_root)
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude").mkdir(exist_ok=True)
    _seed_claude_json(home, project)
    return _DockerContainer(
        name,
        image,
        workdir=project,
        volume=f"{name}-work",              # проект — именованный том
        env={"HOME": CONTAINER_HOME},
        extra_volumes=[f"{home}:{CONTAINER_HOME}",
                       f"{name}-codeindex:{CODE_INDEX_HOME}",
                       *extra_volumes(repo_root, host_cmd_argv)],
        extra_run_args=[*_run_flags(), *_host_name_args()],
    )


def image_present(image: str) -> bool:
    try:
        result = subprocess.run(["docker", "images", "-q", image],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool((result.stdout or "").strip())


def fix_ownership(project_dir) -> None:
    """Сделать корни томов доступными контейнерному uid/gid.

    Docker создаёт корень тома от root, а агент работает от хостового
    пользователя — без chown запись в /workspace и /code-index невозможна.
    Chown не рекурсивный: всё содержимое дальше создаёт сам пользователь.
    """
    if os.name == "nt":
        return
    try:
        subprocess.run(
            ["docker", "exec", "-u", "root", container_name_for(project_dir),
             "sh", "-c", f"chown {os.getuid()}:{os.getgid()} "
                         f"{shlex.quote(str(project_dir))} {CODE_INDEX_HOME}"],
            capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def ensure_container(project_dir, repo_root: Path, image: str,
                     host_cmd_argv: list[str] | None = None) -> _DockerContainer:
    if not image_present(image):
        raise RuntimeError(
            f"образ {image} не найден в Docker — соберите его в мастере "
            "создания проекта (backend «В Docker-контейнере»)")
    container = container_for(project_dir, repo_root, image, host_cmd_argv)
    container.ensure()
    fix_ownership(project_dir)
    return container


def remove_project(project_dir) -> None:
    """Удалить контейнер и тома проекта (для recreate)."""
    name = container_name_for(project_dir)
    for argv in (["docker", "rm", "-f", name],
                 ["docker", "volume", "rm", f"{name}-work",
                  f"{name}-codeindex"]):
        try:
            subprocess.run(argv, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass


def is_inside_container(project_dir) -> bool:
    """Путь проекта считается контейнерным (POSIX-абсолютным)."""
    return str(project_dir).startswith("/")


# ─── Доступ к файлам проекта через docker exec ──────────────────────────────

def run(project_dir, argv: list[str], *, cwd: str | None = None,
        timeout: float | None = None, input_bytes: bytes | None = None):
    """docker exec в контейнер проекта."""
    cmd = ["docker", "exec"]
    if input_bytes is not None:
        cmd.append("-i")
    if cwd:
        cmd += ["-w", cwd]
    cmd += [container_name_for(project_dir), *argv]
    return subprocess.run(cmd, input=input_bytes,
                          capture_output=True,
                          text=input_bytes is None, timeout=timeout)


def read_text(project_dir, path: str) -> str:
    result = run(project_dir, ["cat", path])
    if result.returncode != 0:
        raise OSError(f"{path}: {(result.stderr or '').strip()}")
    return result.stdout or ""


def write_text(project_dir, path: str, content: str) -> None:
    parent = str(Path(path).parent)
    run(project_dir, ["mkdir", "-p", parent])
    result = run(project_dir, ["sh", "-c", 'cat > "$1"', "sh", path],
                 input_bytes=content.encode("utf-8"))
    if result.returncode != 0:
        raise OSError(f"{path}: {(result.stderr or '').strip()}")


def exists(project_dir, path: str) -> bool:
    return run(project_dir, ["test", "-e", path]).returncode == 0


def list_dir(project_dir, path: str) -> list[str]:
    result = run(project_dir, ["sh", "-c", 'ls -A "$1" 2>/dev/null', "sh", path])
    return [line for line in (result.stdout or "").splitlines() if line]


def copy_tree_in(project_dir, local_src: Path, dst: str) -> None:
    """Скопировать локальное дерево в контейнер (tar-поток)."""
    run(project_dir, ["mkdir", "-p", dst])
    name = container_name_for(project_dir)
    with subprocess.Popen(["tar", "-C", str(local_src), "-cf", "-", "."],
                          stdout=subprocess.PIPE) as tar_out:
        result = subprocess.run(
            ["docker", "exec", "-i", name, "tar", "-C", dst, "-xf", "-"],
            stdin=tar_out.stdout, capture_output=True)
        tar_out.stdout.close()
    if result.returncode != 0:
        raise OSError(f"copy_tree_in {dst}: "
                      f"{(result.stderr or b'').decode('utf-8', 'replace')}")


def snapshot(project_dir, dest: Path) -> Path:
    """Снять копию /workspace на хост для метрик/диффов (без .venv и индекса)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    name = container_name_for(project_dir)
    with subprocess.Popen(
            ["docker", "exec", name, "tar", "-C", str(project_dir),
             "--exclude=.venv", "--exclude=.code-index", "-cf", "-", "."],
            stdout=subprocess.PIPE) as tar_out:
        result = subprocess.run(["tar", "-C", str(dest), "-xf", "-"],
                                stdin=tar_out.stdout, capture_output=True)
        tar_out.stdout.close()
    if result.returncode != 0:
        raise OSError(f"snapshot: {(result.stderr or b'').decode('utf-8', 'replace')}")
    return dest


def git(project_dir, *args: str, cwd: str | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    """git внутри контейнера (safe.directory — файлы томов могут быть чужими)."""
    result = run(project_dir, ["git", "-c", f"safe.directory={project_dir}",
                               *args], cwd=cwd or project_dir)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)}: {(result.stderr or result.stdout or '').strip()}")
    return result


# ─── Агент ───────────────────────────────────────────────────────────────────

def agent_prefix(project_dir, repo_root: Path, image: str,
                 host_cmd_argv: list[str],
                 extra_env: dict[str, str] | None = None) -> list[str]:
    """Префикс argv для запуска агента внутри контейнера."""
    container = container_name_for(project_dir)
    inner, _ = _inner_command(host_cmd_argv)
    args = ["docker", "exec", "-i", "-w", str(project_dir)]
    for key, value in (extra_env or {}).items():
        args += ["-e", f"{key}={value}"]
    args += [container, inner, *host_cmd_argv[1:]]
    return args


def kill_agent(project_dir) -> None:
    """Погасить агента внутри контейнера (docker exec без TTY не убивает его)."""
    try:
        run(project_dir,
            ["sh", "-c", "pkill -f '[c]laude' || true"], timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ─── code-index внутри контейнера ───────────────────────────────────────────

@dataclass(frozen=True)
class DockerIndex:
    """Запущенный code-index в контейнере (совместим по атрибутам с NativeIndex)."""
    code_index_dir: str
    binary: str


def _ci_exec(project_dir, argv: list[str], *, env: dict | None = None,
             detached: bool = False, timeout: float | None = None):
    cmd = ["docker", "exec"]
    if detached:
        cmd.append("-d")
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd += [container_name_for(project_dir), *argv]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def stop_code_index(project_dir) -> None:
    """Остановить bsl-indexer внутри контейнера."""
    try:
        _ci_exec(project_dir, ["sh", "-c", "pkill -f '[b]sl-indexer' || true"],
                 timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _index_alive(project_dir) -> bool:
    result = _ci_exec(project_dir,
                      ["sh", "-c", "pgrep -f '[b]sl-indexer' >/dev/null && echo y"])
    return (result.stdout or "").strip() == "y"


def _index_status(project_dir, ci: str) -> dict | None:
    result = _ci_exec(project_dir, [f"{ci}/bsl-indexer", "daemon", "status", "--json"],
                      env={"CODE_INDEX_HOME": ci})
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout or "")
    except ValueError:
        return None


def _log_tail(project_dir, path: str, lines: int = 15) -> str:
    result = _ci_exec(project_dir, ["sh", "-c", f'tail -n {lines} "$1" 2>/dev/null',
                                    "sh", path])
    return (result.stdout or "").strip()


def start_code_index(project_dir, *, code_index_dir, catalog_dir, alias, port,
                     host="127.0.0.1", download=None, log=print) -> DockerIndex:
    """Установить и запустить нативный code-index внутри контейнера."""
    from agentmon.env.code_index_release import download_binary
    from agentmon.env.code_index_toml import render_daemon_toml

    ci = str(code_index_dir)
    _ci_exec(project_dir, ["sh", "-c",
                           f"rm -rf {shlex.quote(ci)}/* {shlex.quote(ci)}/.[!.]* "
                           f"2>/dev/null; mkdir -p {shlex.quote(ci)}"])
    tmp = tempfile.mkdtemp(prefix="bsl-indexer-")
    try:
        binary = (download or download_binary)(tmp, log=log,
                                               platform_name="linux")
        name = container_name_for(project_dir)
        result = subprocess.run(
            ["docker", "cp", str(binary), f"{name}:{ci}/bsl-indexer"],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"не удалось скопировать code-index в контейнер: "
                               f"{(result.stderr or '').strip()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _ci_exec(project_dir, ["chmod", "+x", f"{ci}/bsl-indexer"])
    write_text(project_dir, f"{ci}/daemon.toml",
               render_daemon_toml(alias, str(catalog_dir), int(port)))
    bind_host = "127.0.0.1" if host in ("localhost", "::1", "") else host
    env = {"CODE_INDEX_HOME": ci}

    def _spawn(extra_env: dict, tail: str) -> None:
        cmd = (f"cd {shlex.quote(ci)} && ./bsl-indexer {tail} "
               f">> {tail.split()[0]}.log 2>&1")
        r = _ci_exec(project_dir, ["sh", "-c", cmd],
                     env={**env, **extra_env}, detached=True)
        if r.returncode != 0:
            raise RuntimeError(f"code-index не запустился ({tail}): "
                               f"{(r.stderr or '').strip()}")

    _spawn({}, "daemon run")
    _spawn({"MCP_HTTP_HOST": bind_host, "MCP_HTTP_PORT": str(port)},
           f"serve --transport http --host {bind_host} --port {int(port)} "
           f"--config {ci}/daemon.toml")
    log(f"✓ code-index запущен в контейнере, каталог {ci}, порт {port}")
    return DockerIndex(code_index_dir=ci, binary=f"{ci}/bsl-indexer")


def wait_code_index_ready(index: DockerIndex, *, project_dir, wait_minutes: int,
                          host: str, port: int, run=subprocess.run,
                          sleep=time.sleep, clock=time.monotonic,
                          tcp_ok=None, log=print) -> None:
    """Дождаться готовности code-index (процессы — в контейнере, порт — host-сеть)."""
    from agentmon.env.net_probe import default_tcp_ok
    from agentmon.env.bench_setup import SetupError
    tcp_ok = tcp_ok or default_tcp_ok
    deadline = clock() + wait_minutes * 60
    while True:
        data = _index_status(project_dir, index.code_index_dir)
        paths = (data or {}).get("paths") or []
        for p in paths:
            if p.get("status") == "error":
                raise SetupError(
                    f"code-index: ошибка индексации {p.get('path', '?')}: "
                    f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
        if not _index_alive(project_dir):
            serve_tail = _log_tail(project_dir,
                                   f"{index.code_index_dir}/serve.log")
            daemon_tail = _log_tail(project_dir,
                                    f"{index.code_index_dir}/daemon.log")
            raise SetupError(
                "native code-index завершился; последние строки логов:\n"
                f"--- serve.log ---\n{serve_tail or '(пусто)'}\n"
                f"--- daemon.log ---\n{daemon_tail or '(пусто)'}")
        ready = bool(paths) and all(p.get("status") == "ready"
                                    for p in paths)
        if ready and tcp_ok(f"http://{host}:{port}"):
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if clock() >= deadline:
            raise SetupError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {index.code_index_dir}/daemon.log в контейнере")
        sleep(5)


def exec_prefix(project_dir) -> list[str]:
    """Префикс для запуска произвольной команды проекта в контейнере."""
    return ["docker", "exec", "-w", str(project_dir),
            container_name_for(project_dir)]
