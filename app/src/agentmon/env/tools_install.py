from ..backends.local import LocalProvisioner


def install_tools(config, *, prov=None) -> None:
    """Устанавливает инструменты 1C-batch и зависимости в venv целевого проекта.

    Использует провайдер цели (prov), поэтому работает как локально, так и на
    удалённых бэкендах (SSH, Docker). Интерпретатор берётся из venv проекта через
    prov.venv_python, а не из sys.executable монитора.
    """
    prov = prov or LocalProvisioner()
    py = prov.venv_python(config.project_dir)
    scripts = f"{config.project_dir}/.claude/skills/1c-batch/scripts"
    cmds = [
        [py, "-m", "pip", "install", scripts],
        [py, "-m", "pip", "install", "lxml", "Pillow", "psutil"],
    ]
    for cmd in cmds:
        r = prov.run(cmd)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "установка инструментов не удалась")
