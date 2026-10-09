"""Подъём MCP-серверов в Docker.

Команды выполняются через инъектируемый `run`/`popen` (тесты — без докера).
Построители команд (`launch_cmd`/`build_cmd`) выделены отдельно и переиспользуются
как блокирующими функциями (`launch`/`build`), так и потоковым `iter_output`
для живого стриминга лога сборки/запуска в UI.
"""
import subprocess
import sys

_RC_PREFIX = "\x00rc\x00"


def _default_build_network():
    """Сеть для `docker build`.

    На Linux (в т.ч. sandbox) DNS сборочного namespace часто недоступен — нужен
    `--network=host`. На Docker Desktop (Windows/macOS) host-сеть не поддерживается
    так же и не требуется (DNS в сборке работает), поэтому флаг не добавляем.
    """
    return "host" if sys.platform.startswith("linux") else None


def launch_cmd(name, image, port, *, internal_port=None, token_env=None,
               token=None, env=None, volumes=None, network=None) -> list[str]:
    """Строит команду `docker run` (без выполнения).

    network="host" — контейнер в сети хоста (нужно, когда серверу требуется
    внешний DNS/доступ в интернет; при этом публикация портов `-p` не нужна).
    """
    internal_port = internal_port or port
    # restart=unless-stopped — контейнер переживает перезагрузку хоста/докера,
    # но не поднимается после явной остановки пользователем.
    cmd = ["docker", "run", "-d", "--restart", "unless-stopped", "--name", name]
    if network:
        cmd.append(f"--network={network}")
    else:
        cmd += ["-p", f"127.0.0.1:{port}:{internal_port}"]
    full_env = dict(env or {})
    if token_env and token:  # обратная совместимость
        full_env[token_env] = token
    for k, v in full_env.items():
        cmd += ["-e", f"{k}={v}"]
    for vol in (volumes or []):
        cmd += ["-v", vol]
    cmd.append(image)
    return cmd


def build_cmd(tag, dockerfile, context, *, build_args=None,
              network="__auto__") -> list[str]:
    """Строит команду `docker build` (без выполнения).

    network="__auto__" → `--network=host` только на Linux (см.
    `_default_build_network`); можно переопределить явно (строкой или None).
    """
    net = _default_build_network() if network == "__auto__" else network
    cmd = ["docker", "build"]
    if net:
        cmd.append(f"--network={net}")
    cmd += ["-t", tag, "-f", dockerfile]
    for k, v in (build_args or {}).items():
        cmd += ["--build-arg", f"{k}={v}"]
    cmd.append(context)
    return cmd


def launch(name, image, port, *, internal_port=None, token_env=None, token=None,
           env=None, volumes=None, network=None, run=subprocess.run) -> dict:
    """Запускает контейнер MCP-сервера (блокирующе)."""
    cmd = launch_cmd(name, image, port, internal_port=internal_port,
                     token_env=token_env, token=token, env=env, volumes=volumes,
                     network=network)
    r = run(cmd, capture_output=True, text=True)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "container": name, "log": log}


def build(tag, dockerfile, context, *, build_args=None, run=subprocess.run) -> dict:
    """Собирает образ `tag` (блокирующе)."""
    cmd = build_cmd(tag, dockerfile, context, build_args=build_args)
    r = run(cmd, capture_output=True, text=True)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "log": log}


def iter_output(cmd, popen=subprocess.Popen):
    """Генератор строк вывода команды для живого стриминга.

    Выдаёт строки stdout+stderr по мере поступления, затем служебную строку с
    кодом возврата (распознаётся `is_rc`).
    """
    proc = popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 text=True, bufsize=1)
    for line in proc.stdout:
        yield line.rstrip("\n")
    proc.wait()
    yield rc_line(proc.returncode)


def rc_line(code: int) -> str:
    """Служебная строка-маркер кода возврата для `iter_output`."""
    return f"{_RC_PREFIX}{code}"


def is_rc(line: str):
    """Возвращает код возврата, если строка — служебный маркер `iter_output`, иначе None."""
    if isinstance(line, str) and line.startswith(_RC_PREFIX):
        return int(line[len(_RC_PREFIX):])
    return None


def image_exists(tag, run=subprocess.run) -> bool:
    """True, если локально есть образ с таким тегом."""
    r = run(["docker", "images", "-q", tag], capture_output=True, text=True)
    return bool((getattr(r, "stdout", "") or "").strip())


def status(name, run=subprocess.run) -> str:
    r = run(["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True)
    if r.returncode != 0:
        return "absent"
    return "running" if "true" in (r.stdout or "").lower() else "absent"


def stop(name, run=subprocess.run) -> dict:
    r = run(["docker", "rm", "-f", name], capture_output=True, text=True)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "log": log}
