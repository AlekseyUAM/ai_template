import json
import re
from pathlib import Path

from .scaffold import write_preserving
from .mcp_catalog import mcp_name_overrides

# Шаблон разворачиваемого окружения лежит в корне репозитория (template/).
# Содержимое .claude-окружения (агенты/скилы/правила/хуки/инструменты) —
# в template/.claude; в корень проекта кладём README с заголовком-именем проекта.
TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "template"
CONTENT_DIR = TEMPLATE_DIR / ".claude"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_EFFORT = "medium"

# Команда-токен вызова интерпретатора в хуках/доках навыков. Все вызовы имеют вид
# `python "<путь>"` / `python .claude/...` / `python -m ...`; в прозе `python `
# не встречается. При деплое токен заменяется на абсолютный путь интерпретатора
# .venv проекта — чтобы хуки/скиллы не зависели от того, что окажется в PATH.
# В settings.json кавычка экранирована (`python \"$...`), поэтому в класс
# символов-ограничителей входит и backslash.
_PY_INVOKE = re.compile(r"\bpython (?=[\"'.$\\-])")


# Сборочные/тестовые артефакты, которые не должны попадать в развёрнутый проект.
_CRUFT_DIRS = {"__pycache__", "build", ".pytest_cache"}


def _is_cruft(item: Path) -> bool:
    return any(p in _CRUFT_DIRS or p.endswith(".egg-info") for p in item.parts)


def _is_special(rel: Path) -> bool:
    """Файлы шаблона, которые разворачиваются не копией, а отдельно.

    Агенты рендерятся с подстановкой модели/эффорта, README и settings.json
    пишутся через write_preserving (с бэкапом при обновлении).
    """
    parts = rel.parts
    return (
        parts == ("README.md",)
        or parts[:2] == (".claude", "agents")
        or parts == (".claude", "settings.json")
    )


def _model_effort(config, name):
    for a in config.agents:
        if a.agent == name:
            return a.model, a.effort
    return _DEFAULT_MODEL, _DEFAULT_EFFORT


def _render_agents(prov, config, agents_dst, overrides: dict | None = None) -> None:
    prov.mkdirs([agents_dst])
    for src in sorted((CONTENT_DIR / "agents").glob("*.md")):
        model, effort = _model_effort(config, src.stem)
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{MODEL}}", model).replace("{{EFFORT}}", effort)
        if overrides:
            for placeholder, actual in overrides.items():
                text = text.replace(placeholder, actual)
        prov.write_text(f"{agents_dst}/{src.name}", text)


def _render_settings() -> str:
    # settings.json — часть шаблона (template/.claude/settings.json): единственный
    # источник истины. Читаем его дословно, но пишем через write_preserving
    # (с бэкапом при обновлении), т.к. файл принадлежит проекту и мог быть изменён.
    return (CONTENT_DIR / "settings.json").read_text(encoding="utf-8")


def _apply_mcp_names(prov, claude_dir, overrides) -> None:
    """Подставляет актуальные имена MCP вместо плейсхолдеров — пишем на цель.

    Обходим текстовые файлы шаблона .claude на мониторе; меняем и пишем на цель
    только изменившиеся. Агенты и settings.json пропускаем: агенты обрабатываются
    в _render_agents (с учётом model/effort), settings.json — через write_preserving.
    """
    for src in sorted(CONTENT_DIR.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(CONTENT_DIR)
        # agents/ обрабатываются в _render_agents; settings.json — через write_preserving
        if rel.parts[:1] == ("agents",) or rel.parts == ("settings.json",):
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}", new)


def venv_python(prov, project_dir) -> str:
    return prov.venv_python(project_dir)


def _py_cmd(prov, project_dir) -> str:
    return '"' + prov.venv_python(project_dir) + '"'


def _deploy_vscode(prov, project_dir, *, update: bool) -> None:
    content = json.dumps(
        {"python.defaultInterpreterPath": prov.venv_python(project_dir)},
        ensure_ascii=False, indent=2) + "\n"
    write_preserving(prov, f"{project_dir}/.vscode/settings.json",
                     content, update=update)


def _rewrite_python_invocations(prov, claude_dir, py_cmd) -> None:
    """Пишет версии *.md шаблона с заменой `python ` на путь venv — на цель.

    Источник списка файлов — шаблон на мониторе (CONTENT_DIR); пишем на цель.
    """
    for src in sorted(CONTENT_DIR.rglob("*.md")):
        if "__pycache__" in src.parts:
            continue
        rel = src.relative_to(CONTENT_DIR)
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = _PY_INVOKE.sub(lambda m: py_cmd + " ", text)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}", new)


def provision_venv(prov, config, *, update: bool) -> str | None:
    """Создаёт .venv на ЦЕЛЕВОЙ машине интерпретатором цели (prov.python_cmd()).

    Раньше venv строился sys.executable — для SSH это интерпретатор монитора, не
    цели. Теперь интерпретатор задаёт provisioner (local → sys.executable,
    ssh → python3 на удалённом хосте). Ошибки venv/pip НЕ валят создание проекта.
    """
    project_dir = config.project_dir
    venv_dir = f"{project_dir}/.venv"
    py = prov.venv_python(project_dir)
    req = TEMPLATE_DIR / "requirements.txt"
    if not prov.exists(venv_dir):
        res = prov.run(prov.python_cmd() + ["-m", "venv", venv_dir])
        if res.returncode != 0:
            return (f"не удалось подготовить .venv ({res.stderr.strip()}); "
                    f"зависимости навыков не установлены. "
                    f"Доустановите: python setup-venv.py")
    if req.is_file():
        # requirements.txt — исходник на мониторе; заливаем его на цель внутри
        # .venv (не в корень проекта — чтобы не нарушать byte-for-byte инвариант
        # значимого дерева проекта; .venv гитигнорен/эфемерен).
        req_dst = f"{venv_dir}/ai1c-requirements.txt"
        prov.write_text(req_dst, req.read_text(encoding="utf-8"))
        res = prov.run([py, "-m", "pip", "install", "-r", req_dst])
        if res.returncode != 0:
            return (f"не удалось поставить зависимости навыков "
                    f"({res.stderr.strip()}). Доустановите: python setup-venv.py")
    return None


def deploy_content(prov, config, *, update: bool) -> None:
    project_dir = config.project_dir
    claude = f"{project_dir}/.claude"
    prov.put_tree(str(TEMPLATE_DIR), project_dir, skip=_is_special)
    overrides = mcp_name_overrides(config.mcp) if not update else {}
    _render_agents(prov, config, f"{claude}/agents", overrides=overrides or None)
    py_json = '\\"' + prov.venv_python(project_dir) + '\\"'
    settings = _PY_INVOKE.sub(lambda m: py_json + " ", _render_settings())
    if overrides:
        for placeholder, actual in overrides.items():
            settings = settings.replace(placeholder, actual)
    write_preserving(prov, f"{claude}/settings.json", settings, update=update)
    _rewrite_python_invocations(prov, claude, _py_cmd(prov, project_dir))
    _deploy_vscode(prov, project_dir, update=update)
    if not update:
        write_preserving(prov, f"{project_dir}/README.md",
                         _project_readme(config.project_name), update=update)
        if overrides:
            _apply_mcp_names(prov, claude, overrides)
    from .nethasp import deploy_nethasp
    deploy_nethasp(prov, config)


def _project_readme(project_name: str) -> str:
    """README проекта: заголовок-имя + как переподнять .venv на свежем клоне."""
    return (
        f"## {project_name}\n\n"
        "### Окружение разработки\n\n"
        "Python-зависимости навыков живут в изолированном `.venv` (он в `.gitignore`).\n"
        "На свежем клоне подними его одной командой:\n\n"
        "    python setup-venv.py\n"
    )
