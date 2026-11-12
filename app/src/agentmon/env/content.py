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

# Условные блоки шаблона: <!-- @if 1c-md --> … <!-- @endif -->. Маркер @if
# стоит сразу после строки-разделителя (без пустой строки перед ним), первая
# строка внутри блока — пустая для отбивки абзаца, @endif — сразу после
# последней строки контента; пустая строка после @endif остаётся в шаблоне.
_CONDITIONAL_BLOCK = re.compile(
    r"^<!-- @if (?P<cond>[a-z0-9_-]+) -->\n(?P<body>.*?)^<!-- @endif -->\n",
    re.MULTILINE | re.DOTALL,
)


def _render_conditional_blocks(text: str, has_1c_md: bool, *,
                               filename: str = "") -> str:
    """Оставляет/вырезает условные блоки шаблона по составу MCP проекта.

    Сейчас условие одно: `1c-md` — включён MCP вида `1c-md` или
    `1c-md-queries`. Незакрытый, вложенный или лишний маркер — ValueError:
    маркеры не должны попасть в развёрнутый проект.
    """
    conditions = {"1c-md": has_1c_md}

    def repl(match: re.Match) -> str:
        cond = match.group("cond")
        if cond not in conditions:
            raise ValueError(
                f"неизвестное условие {cond!r} в {filename or '<текст>'}")
        return match.group("body") if conditions[cond] else ""

    rendered = _CONDITIONAL_BLOCK.sub(repl, text)
    if "<!-- @if " in rendered or "<!-- @endif -->" in rendered:
        raise ValueError(
            f"несбалансированный условный блок в {filename or '<текст>'}: "
            "@if/@endif должны быть парными и не вложенными")
    return rendered


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


def _render_template_texts(prov, claude_dir, overrides, *,
                           has_1c_md: bool, py_cmd: str) -> None:
    """Подставляет имена MCP и рендерит условные блоки — пишем на цель.

    Обходим текстовые файлы шаблона .claude на мониторе; меняем и пишем на цель
    только изменившиеся. Агенты и settings.json пропускаем: агенты обрабатываются
    в _render_agents (с учётом model/effort), settings.json — через write_preserving.
    При записи применяется и подстановка интерпретатора .venv: файл с условными
    блоками (query-analyze) содержит вызовы `python …`.
    """
    for src in sorted(CONTENT_DIR.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(CONTENT_DIR)
        if "__pycache__" in rel.parts:
            continue
        # agents/ обрабатываются в _render_agents; settings.json — через write_preserving
        if rel.parts[:1] == ("agents",) or rel.parts == ("settings.json",):
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # Сначала рендер условных блоков, потом подстановка имён MCP: иначе
        # override `1c-md` → `1c-md-queries` (если сервер назван по-другому)
        # испортил бы имя условия в маркере `<!-- @if 1c-md -->`.
        new = _render_conditional_blocks(
            text, has_1c_md, filename=rel.as_posix())
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}",
                            _rewrite_python_text(new, py_cmd))


def venv_python(prov, project_dir) -> str:
    return prov.venv_python(project_dir)


def _shell_path(path: str) -> str:
    """Путь для текста команды оболочки: Windows-backslash → прямой слэш.

    Хуки и команды в доках исполняет Git Bash (на Windows — тоже). Литеральный
    backslash в тексте команды Bash съедает как escape-символ ещё до запуска
    (claude-code#26759), поэтому в команды путь впечатываем через `/`: Windows
    понимает прямые слэши, а Bash их не трогает.
    """
    return path.replace("\\", "/")


def _py_cmd(prov, project_dir) -> str:
    return '"' + _shell_path(prov.venv_python(project_dir)) + '"'


def _deploy_vscode(prov, project_dir, *, update: bool) -> None:
    content = json.dumps(
        {"python.defaultInterpreterPath": prov.venv_python(project_dir)},
        ensure_ascii=False, indent=2) + "\n"
    write_preserving(prov, f"{project_dir}/.vscode/settings.json",
                     content, update=update)


def _rewrite_python_text(text: str, py_cmd: str) -> str:
    """Заменяет вызовы `python …` на интерпретатор .venv проекта."""
    return _PY_INVOKE.sub(lambda _m: py_cmd + " ", text)


def _rewrite_python_invocations(prov, claude_dir, py_cmd) -> None:
    """Пишет версии *.md шаблона с заменой `python ` на путь venv — на цель.

    Источник списка файлов — шаблон на мониторе (CONTENT_DIR); пишем на цель.
    """
    for src in sorted(CONTENT_DIR.rglob("*.md")):
        rel = src.relative_to(CONTENT_DIR)
        if "__pycache__" in rel.parts:
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = _rewrite_python_text(text, py_cmd)
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
    # backup=True: обновление не должно молча стирать правки пользователя в
    # .claude/skills|rules|hooks|tools — прежняя версия остаётся рядом в .bak.
    prov.put_tree(str(TEMPLATE_DIR), project_dir, skip=_is_special,
                  backup=update)
    # Имя проекта → alias репозитория code-index в подсказках агенту: берётся из
    # записи проекта, стабильно, поэтому подставляем ВСЕГДА. Имена MCP берём из
    # карточки проекта и на обновлении — иначе хук останется с прежним именем
    # сервера после переименования.
    mcp_subs = mcp_name_overrides(config.mcp)
    subs = {**mcp_subs, "{{CODE_INDEX_REPO}}": config.project_name}
    has_1c_md = any(
        getattr(sel, "enabled", False)
        and sel.id in ("1c-md", "1c-md-queries")
        for sel in config.mcp
    )
    # tools агентов — allow-list: без явной записи mcp__<имя 1c-md>__* субагент
    # не сможет вызвать validate_query, даже если навык его рекомендует. Хвост
    # строки tools дописываем только при включённом 1c-md; имя — фактическое.
    agent_subs = dict(subs)
    agent_subs["{{MCP_1C_MD_TOOLS}}"] = (
        f", mcp__{mcp_subs.get('1c-md', '1c-md')}__*" if has_1c_md else "")
    _render_agents(prov, config, f"{claude}/agents", overrides=agent_subs)
    # settings.json — текст JSON, а путь к интерпретатору впечатывается прямо в
    # него. Слэши — прямые: Git Bash на Windows съедает литеральный backslash в
    # команде (claude-code#26759), а JSON-строка требует экранировать кавычки.
    # json.dumps делает и то и другое; [1:-1] снимает внешние кавычки, оставляя
    # готовую к вставке JSON-строку `\"C:/.../python.exe\"`.
    py_json = json.dumps('"' + _shell_path(prov.venv_python(project_dir)) + '"')[1:-1]
    settings = _PY_INVOKE.sub(lambda m: py_json + " ", _render_settings())
    for placeholder, actual in subs.items():
        settings = settings.replace(placeholder, actual)
    write_preserving(prov, f"{claude}/settings.json", settings, update=update)
    # _rewrite_python_invocations проходит ВСЕ *.md, включая неизменённые;
    # _render_template_texts пишет только изменённые. Не удалять этот проход.
    _rewrite_python_invocations(prov, claude, _py_cmd(prov, project_dir))
    _deploy_vscode(prov, project_dir, update=update)
    if not update:
        write_preserving(prov, f"{project_dir}/README.md",
                         _project_readme(config.project_name), update=update)
    _render_template_texts(prov, claude, subs, has_1c_md=has_1c_md,
                           py_cmd=_py_cmd(prov, project_dir))
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
