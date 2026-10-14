import json
import os
import re
import subprocess
import sys
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


def _copy_tree(src: Path, dst: Path, *, skip=None) -> None:
    for item in sorted(src.rglob("*")):
        if _is_cruft(item):
            continue
        rel = item.relative_to(src)
        if skip is not None and skip(rel):
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


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


def _render_agents(config, agents_dst: Path) -> None:
    agents_dst.mkdir(parents=True, exist_ok=True)
    for src in sorted((CONTENT_DIR / "agents").glob("*.md")):
        model, effort = _model_effort(config, src.stem)
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{MODEL}}", model).replace("{{EFFORT}}", effort)
        (agents_dst / src.name).write_text(text, encoding="utf-8")


def _render_settings() -> str:
    # settings.json — часть шаблона (template/.claude/settings.json): единственный
    # источник истины. Читаем его дословно, но пишем через write_preserving
    # (с бэкапом при обновлении), т.к. файл принадлежит проекту и мог быть изменён.
    return (CONTENT_DIR / "settings.json").read_text(encoding="utf-8")


def _apply_mcp_names(claude_dir: Path, overrides: dict) -> None:
    """Подставляет актуальные имена MCP вместо плейсхолдеров шаблона.

    Проходит по всем текстовым файлам .claude и заменяет каждое имя-плейсхолдер
    на актуальное. Бинарные/нечитаемые файлы и __pycache__ пропускаются.
    """
    for path in sorted(claude_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            path.write_text(new, encoding="utf-8")


def venv_python(project: Path) -> Path:
    """Путь к интерпретатору .venv проекта (ветка по ОС, как в bootstrap.py)."""
    if os.name == "nt":
        return project / ".venv" / "Scripts" / "python.exe"
    return project / ".venv" / "bin" / "python"


def _deploy_vscode(project: Path, *, update: bool) -> None:
    """Пин интерпретатора .venv для VS Code (расширение Python).

    Без этого файла расширение при первом открытии проекта полагается на авто-детект
    и успевает выбрать глобальный интерпретатор (ошибка «Invalid python interpreter»),
    пока асинхронно не разрешится .venv. Пишем абсолютный путь из того же источника
    (venv_python), что и вызовы в хуках/доках, — тулинг не зависит от PATH/детекта.
    Через write_preserving: на обновлении окружения пользовательские правки сохраняются
    в .bak, а не затираются молча.
    """
    vscode = project / ".vscode"
    vscode.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        {"python.defaultInterpreterPath": venv_python(project).as_posix()},
        ensure_ascii=False, indent=2) + "\n"
    write_preserving(vscode / "settings.json", content, update=update)


def _py_cmd(project: Path) -> str:
    """Токен для вставки в команды: абсолютный путь venv в кавычках, forward-slash.

    as_posix() даёт прямые слэши даже на Windows (`C:/.../python.exe`) — так путь
    корректно отрабатывает и в git-bash, которым агент исполняет команды.
    """
    return '"' + venv_python(project).as_posix() + '"'


def _rewrite_python_invocations(claude_dir: Path, py_cmd: str) -> None:
    """Заменяет токен `python ` на путь venv во всех `*.md` развёрнутого .claude.

    Трогает только md-доки навыков/правил/агентов; шебанги `.py` и внутренние
    `sys.executable`-вызовы не затрагиваются (дочерние процессы и так наследуют
    интерпретатор родителя). settings.json переписывается отдельно (см. deploy).
    """
    for path in sorted(claude_dir.rglob("*.md")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = _PY_INVOKE.sub(lambda m: py_cmd + " ", text)
        if new != text:
            path.write_text(new, encoding="utf-8")


def provision_venv(config, *, update: bool, run=subprocess.run) -> str | None:
    """Создаёт .venv проекта и ставит туда рантайм-зависимости навыков.

    venv строится интерпретатором самого agentmon (sys.executable) — он гарантирован.
    Ошибки venv/pip НЕ валят создание проекта. Возвращает None при успехе либо текст
    предупреждения (его шаг установки покажет статусом "warn"), чтобы сбой не остался
    незамеченным до рантайма навыка.
    """
    project = Path(config.project_dir)
    venv_dir = project / ".venv"
    py = venv_python(project)
    req = TEMPLATE_DIR / "requirements.txt"
    try:
        if not venv_dir.exists():
            run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        if req.is_file():
            run([str(py), "-m", "pip", "install", "-r", str(req)], check=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        return (
            f"не удалось подготовить .venv ({exc}); зависимости навыков "
            f"(lxml/psutil/click) не установлены. Доустановите: python setup-venv.py"
        )
    return None


def _project_readme(project_name: str) -> str:
    """README проекта: заголовок-имя + как переподнять .venv на свежем клоне."""
    return (
        f"## {project_name}\n\n"
        "### Окружение разработки\n\n"
        "Python-зависимости навыков живут в изолированном `.venv` (он в `.gitignore`).\n"
        "На свежем клоне подними его одной командой:\n\n"
        "    python setup-venv.py\n"
    )


def deploy_content(config, *, update: bool) -> None:
    project = Path(config.project_dir)
    claude = project / ".claude"
    # template — источник истины: копируем всё дерево целиком, чтобы любой
    # добавленный в шаблон файл/каталог попал в проект. Спец-файлы (_is_special)
    # разворачиваются отдельно ниже.
    _copy_tree(TEMPLATE_DIR, project, skip=_is_special)
    _render_agents(config, claude / "agents")
    # Вызовы интерпретатора указываем на .venv проекта (абсолютный путь), чтобы
    # хуки/скиллы не зависели от PATH. Путь детерминирован из project_dir, сам
    # .venv создаётся отдельным шагом (provision_venv) в пайплайне установки.
    py_cmd = _py_cmd(project)
    # В settings.json вызов живёт внутри JSON-строки, поэтому кавычки пути должны
    # быть экранированы (\"...\"), иначе ломается JSON. В .md — обычные кавычки.
    py_json = '\\"' + venv_python(project).as_posix() + '\\"'
    settings = _PY_INVOKE.sub(lambda m: py_json + " ", _render_settings())
    write_preserving(claude / "settings.json", settings, update=update)
    _rewrite_python_invocations(claude, py_cmd)
    # VS Code: пин интерпретатора .venv, чтобы при открытии проекта не всплывала
    # ошибка «Invalid python interpreter» из-за авто-детекта глобального python.
    _deploy_vscode(project, update=update)
    # README проекта — пустой с заголовком-именем (шаблонный template/README.md
    # при установке заменяется на этот). При обновлении версии окружения README
    # не трогаем — он уже принадлежит проекту.
    if not update:
        write_preserving(project / "README.md",
                         _project_readme(config.project_name), update=update)
        # Подстановка актуальных имён выбранных MCP вместо плейсхолдеров шаблона —
        # только при создании (на обновлении окружения имена не трогаем).
        overrides = mcp_name_overrides(config.mcp)
        if overrides:
            _apply_mcp_names(claude, overrides)
