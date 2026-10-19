import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .config_schema import EnvConfig
from .scaffold import scaffold_layout, write_env_files
from .platform_dump import dump
from .content import deploy_content, provision_venv
from .devbase import git_commit_all, git_init_project, write_devbase
from .tools_install import install_tools as install_tools_fn
from ..backends.local import LocalProvisioner


@dataclass
class ProgressEvent:
    step: str
    status: str                 # "start" | "ok" | "warn" | "error"
    detail: str = ""


def install_environment(
    config: EnvConfig, *, update: bool,
    register: Callable[[EnvConfig], None],
    dump_cf: bool, dump_cfe: bool,
    install_tools: bool = False,
    git_init: bool = True,
    db_user: str = "",
    db_password: str = "",
    run=subprocess.run,
    prov=None,
) -> Iterator[ProgressEvent]:
    prov = prov or LocalProvisioner()
    base = Path(config.project_dir)

    def step(name, fn):
        yield ProgressEvent(name, "start")
        try:
            result = fn()
        except Exception as exc:                       # noqa: BLE001
            yield ProgressEvent(name, "error", str(exc))
            raise
        # Шаг может вернуть текст предупреждения (напр. provision_venv при сбое
        # pip): установку не прерываем, но и "ok" не показываем.
        if isinstance(result, str) and result:
            yield ProgressEvent(name, "warn", result)
        else:
            yield ProgressEvent(name, "ok")

    def _prepare_src():
        write_devbase(prov, config, user=db_user, password=db_password)
        if git_init:
            git_init_project(prov, str(base), config=config)

    # ai1c.config.json не генерируем: источник истины — внутренняя БД.
    # При обновлении версии окружения трогаем только контент шаблона: .mcp.json
    # и .1c-devbase.json не перезаписываем, git init и выгрузки cf/cfe не делаем.
    steps = [
        ("layout", lambda: scaffold_layout(prov, config.project_dir)),
        ("content", lambda: deploy_content(prov, config, update=update)),
        # Изолированный .venv проекта с рантайм-зависимостями навыков (lxml/psutil/
        # click). Путь к интерпретатору уже впечатан в хуки/доки шагом content.
        ("venv", lambda: provision_venv(prov, config, update=update)),
    ]
    if not update:
        steps.append(("mcp", lambda: write_env_files(prov, config, update=update)))
        steps.append(("prepare-src", _prepare_src))
    if dump_cf and not update:
        steps.append(("dump-cf",
                      lambda: dump(config, "cf", user=db_user, password=db_password, prov=prov)))
    if dump_cfe and not update:
        steps.append(("dump-cfe",
                      lambda: dump(config, "cfe", user=db_user, password=db_password, prov=prov)))
    if install_tools:
        steps.append(("tools-install", lambda: install_tools_fn(config, run=run)))
    # Фиксируем все сгенерированные файлы одним коммитом — только при создании.
    if git_init and not update:
        steps.append(("git-commit",
                      lambda: git_commit_all(prov, str(base), "init", config=config)))
    steps.append(("register", lambda: register(config)))

    try:
        for name, fn in steps:
            yield from step(name, fn)
    except Exception:
        return                      # error-событие уже отдано шагом
