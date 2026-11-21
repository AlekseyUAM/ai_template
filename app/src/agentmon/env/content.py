import json
import re
from pathlib import Path

from .scaffold import write_preserving
from .mcp_catalog import _server_name, mcp_name_overrides

# Шаблон разворачиваемого окружения лежит в корне репозитория (template/).
# Содержимое .claude-окружения (чеклисты/скилы/правила/хуки/инструменты) —
# в template/.claude; в корень проекта кладём README, CLAUDE.md и настройки.
TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "template"
CONTENT_DIR = TEMPLATE_DIR / ".claude"

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


# Условие шаблона → id MCP-выборов, включающих блок. Новый сервер: добавьте
# строку сюда и поставьте в шаблоне маркер <!-- @if <условие> -->.
_CONDITION_MCP_IDS = {
    "1c-md": ("1c-md", "1c-md-queries"),
    "1c_naparnic": ("1c-naparnic",),
}


def conditional_flags(mcp) -> dict[str, bool]:
    """Какие условные блоки включать — по включённым MCP проекта."""
    enabled = {getattr(sel, "id", None) for sel in mcp
               if getattr(sel, "enabled", False)}
    return {cond: any(mid in enabled for mid in ids)
            for cond, ids in _CONDITION_MCP_IDS.items()}


def _render_conditional_blocks(text: str, conditions: dict[str, bool], *,
                               filename: str = "") -> str:
    """Оставляет/вырезает условные блоки шаблона по составу MCP проекта.

    `conditions` — карта условие→включено (см. conditional_flags).
    Незакрытый, вложенный или лишний маркер — ValueError: маркеры не должны
    попасть в развёрнутый проект.
    """

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


# Конфиг хука code-index-guard в развёрнутом проекте: генерируется из выбранных
# MCP code-index (а не копируется из шаблона — образец .toml.example остаётся).
_GUARD_CFG_REL = Path(".claude/hooks/code-index-guard.toml")
_GUARD_MCP_IDS = ("code-index", "code-index-local")
# Сколько раз подряд guard может отклонить один и тот же нативный вызов, прежде
# чем разрешить его. Защита от зацикливания локальных моделей на deny: охранник
# остаётся, но после N отказов уступает и даёт прочитать файл нативно.
_GUARD_MAX_DENIES = 2


def _is_special(rel: Path) -> bool:
    """Файлы шаблона, которые разворачиваются не копией, а отдельно.

    README, CLAUDE.md и settings.json пишутся через write_preserving
    (с бэкапом при обновлении), settings.json — ещё и с подстановкой пути venv.
    """
    parts = rel.parts
    return (
        parts == ("README.md",)
        or parts == ("CLAUDE.md",)
        or parts == (".claude", "settings.json")
        or rel == _GUARD_CFG_REL
    )


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _default_alias(path: str) -> str:
    """alias репозитория по пути, если в карточке MCP имя не задано."""
    last = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return last.lower().replace(" ", "_")


def _guard_mcp_name(mcp) -> str:
    """Ключ сервера code-index в .mcp.json — основа префикса гарда.

    Берём **последний** включённый выбор с id из `_GUARD_MCP_IDS` и имя из
    `_server_name` — той же функции, что строит `.mcp.json`. В `build_mcp_json`
    серверы складываются в dict по ключу, т.е. при совпадении имён (обе карточки
    по умолчанию дают `code_index`) выживает последний выбор. Гард обязан
    называть именно его, иначе deny-сообщения укажут на несуществующий сервер.
    Без connection-фрагмента ключ — `sel.id` (`code-index`), с фрагментом — имя
    из него.

    Без включённых code-index конфиг получается только из комментариев (он
    нейтрализует устаревший сгенерированный конфиг при обновлении), и префикс
    не используется гардом. Для него оставляем плейсхолдер `code_index` (как
    `DEFAULT_MCP_PREFIX` хука) либо переименование из `mcp_name_overrides`.
    """
    last = None
    for sel in mcp:
        if getattr(sel, "enabled", False) and sel.id in _GUARD_MCP_IDS:
            last = sel
    if last is not None:
        return _server_name(last)
    return mcp_name_overrides(mcp).get("code_index", "code_index")


def _guard_entries(mcp) -> list[tuple[str, str]]:
    """(path, alias) репозиториев, реально обслуживаемых сервером гарда.

    Гард несёт один `mcp_prefix`, а `build_mcp_json` складывает серверы в dict
    по `_server_name(sel)` — при совпадении имён (обе карточки code-index по
    умолчанию дают `code_index`) в `.mcp.json` остаётся только последний.
    Поэтому входят лишь включённые гардом карточки, чей `_server_name` равен
    имени выжившего сервера (см. `_guard_mcp_name`).

    Ограничение: при разных именах гардом защищается только последний сервер;
    репозиторий другого (оно же — доступное модели без deny) гард не упоминает:
    он абстендится, а не ведёт модель к несуществующему серверу.

    Каталог обязан быть абсолютным путём: ни хук, ни демон code-index не
    раскрывают `~`, поэтому такая карточка — ошибка конфигурации.
    """
    served: tuple[str, str] | None = None
    for sel in mcp:
        if not getattr(sel, "enabled", False):
            continue
        if sel.id not in _GUARD_MCP_IDS:
            continue
        path = getattr(sel, "catalog_dir", None)
        if not path:
            continue
        if path.strip().startswith("~"):
            raise ValueError(
                f"catalog_dir {path!r} карточки {sel.id}: code-index не "
                "раскрывает домашний каталог (~), укажите абсолютный путь")
        if _server_name(sel) == _guard_mcp_name(mcp):
            served = (path, getattr(sel, "project_name", None)
                      or _default_alias(path))
    return [served] if served else []


def _guard_config_text(mcp) -> str:
    """Текст code-index-guard.toml: префикс MCP + [[local]] по репозиториям.

    Префикс — фактический ключ сервера code-index в `.mcp.json` (см.
    `_guard_mcp_name`); `[[local]]` — только по репозиториям, обслуживаемым
    этим сервером (см. `_guard_entries`).
    """
    actual = _guard_mcp_name(mcp)
    lines = [
        "# Generated when the agentmon environment is deployed.",
        "# Manual edits will be overwritten when the environment is updated.",
        f'mcp_prefix = "mcp__{actual}__"',
        f"max_denies = {_GUARD_MAX_DENIES}",
        "",
    ]
    for path, alias in _guard_entries(mcp):
        lines += ["[[local]]",
                  f'path = "{_toml_escape(path)}"',
                  f'alias = "{_toml_escape(alias)}"', ""]
    return "\n".join(lines) + "\n"


def _inject_guard_hook(settings_text: str, py_cmd: str) -> str:
    """Добавляет PreToolUse-запись хука code-index-guard в settings.json.

    Вызывается ПОСЛЕ подстановки имён MCP: иначе `code_index` в имени файла
    хука будет переименован вместе с плейсхолдерами.
    """
    data = json.loads(settings_text)
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre.insert(0, {
        "matcher": "Read|Grep|Glob|Bash|PowerShell",
        "hooks": [{
            "type": "command",
            "command": (f'{py_cmd} "$CLAUDE_PROJECT_DIR/.claude/'
                        'hooks/code_index_guard.py"'),
            "timeout": 10,
        }],
    })
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _render_settings() -> str:
    # settings.json — часть шаблона (template/.claude/settings.json): единственный
    # источник истины. Читаем его дословно, но пишем через write_preserving
    # (с бэкапом при обновлении), т.к. файл принадлежит проекту и мог быть изменён.
    return (CONTENT_DIR / "settings.json").read_text(encoding="utf-8")


def _render_template_texts(prov, claude_dir, overrides, *,
                           conditions: dict[str, bool], py_cmd: str) -> None:
    """Подставляет имена MCP и рендерит условные блоки — пишем на цель.

    Обходим текстовые файлы шаблона .claude на мониторе; меняем и пишем на цель
    только изменившиеся. settings.json пропускаем: он пишется через
    write_preserving. При записи применяется и подстановка интерпретатора .venv:
    файлы с условными блоками (query-analyze) содержат вызовы `python …`.
    """
    for src in sorted(CONTENT_DIR.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(CONTENT_DIR)
        if "__pycache__" in rel.parts:
            continue
        if rel.parts == ("settings.json",):
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # Сначала рендер условных блоков, потом подстановка имён MCP: иначе
        # override `1c-md` → `1c-md-queries` (если сервер назван по-другому)
        # испортил бы имя условия в маркере `<!-- @if 1c-md -->`.
        new = _render_conditional_blocks(
            text, conditions, filename=rel.as_posix())
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}",
                            _rewrite_python_text(new, py_cmd))


def _render_claude_md(prov, project_dir, overrides, *,
                      conditions: dict[str, bool], py_cmd: str,
                      update: bool) -> None:
    """Рендерит корневой CLAUDE.md шаблона (single-agent протокол).

    Файл принадлежит проекту: на обновлении сохраняем прежнюю версию в .bak
    и не теряем ручные правки пользователя.
    """
    src = TEMPLATE_DIR / "CLAUDE.md"
    if not src.is_file():
        return
    text = src.read_text(encoding="utf-8")
    text = _render_conditional_blocks(text, conditions, filename="CLAUDE.md")
    for placeholder, actual in overrides.items():
        text = text.replace(placeholder, actual)
    text = _rewrite_python_text(text, py_cmd)
    write_preserving(prov, f"{project_dir}/CLAUDE.md", text, update=update)


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
    # .claude/checklists|skills|rules|hooks|tools — прежняя версия остаётся в .bak.
    prov.put_tree(str(TEMPLATE_DIR), project_dir, skip=_is_special,
                  backup=update)
    # Имя проекта → alias репозитория code-index в подсказках исполнителю: берётся из
    # записи проекта, стабильно, поэтому подставляем ВСЕГДА. Имена MCP берём из
    # карточки проекта и на обновлении — иначе хук останется с прежним именем
    # сервера после переименования.
    mcp_subs = mcp_name_overrides(config.mcp)
    subs = {**mcp_subs, "{{CODE_INDEX_REPO}}": config.project_name}
    conditions = conditional_flags(config.mcp)
    # settings.json — текст JSON, а путь к интерпретатору впечатывается прямо в
    # него. Слэши — прямые: Git Bash на Windows съедает литеральный backslash в
    # команде (claude-code#26759), а JSON-строка требует экранировать кавычки.
    # json.dumps делает и то и другое; [1:-1] снимает внешние кавычки, оставляя
    # готовую к вставке JSON-строку `\"C:/.../python.exe\"`.
    py_json = json.dumps('"' + _shell_path(prov.venv_python(project_dir)) + '"')[1:-1]
    settings = _PY_INVOKE.sub(lambda m: py_json + " ", _render_settings())
    for placeholder, actual in subs.items():
        settings = settings.replace(placeholder, actual)
    # Хук code-index-guard регистрируем ПОСЛЕ подстановки имён MCP: имя файла
    # хука содержит `code_index`, который подстановка иначе переименовала бы.
    # Конфиг хука пишем всегда (без code-index — только комментарии): так он
    # нейтрализует устаревший сгенерированный конфиг при обновлении.
    prov.write_text(f"{claude}/hooks/code-index-guard.toml",
                    _guard_config_text(config.mcp))
    if _guard_entries(config.mcp):
        settings = _inject_guard_hook(settings, _py_cmd(prov, project_dir))
    write_preserving(prov, f"{claude}/settings.json", settings, update=update)
    # _rewrite_python_invocations проходит ВСЕ *.md, включая неизменённые;
    # _render_template_texts пишет только изменённые. Не удалять этот проход.
    _rewrite_python_invocations(prov, claude, _py_cmd(prov, project_dir))
    _deploy_vscode(prov, project_dir, update=update)
    if not update:
        write_preserving(prov, f"{project_dir}/README.md",
                         _project_readme(config.project_name), update=update)
    _render_claude_md(prov, project_dir, subs, conditions=conditions,
                      py_cmd=_py_cmd(prov, project_dir), update=update)
    _render_template_texts(prov, claude, subs, conditions=conditions,
                           py_cmd=_py_cmd(prov, project_dir))
    from .nethasp import deploy_nethasp
    deploy_nethasp(prov, config)


def _project_readme(project_name: str) -> str:
    """README проекта: заголовок-имя + как переподнять .venv на свежем клоне."""
    return (
        f"## {project_name}\n\n"
        "### Development environment\n\n"
        "The Python dependencies of the skills live in an isolated `.venv` (it is in `.gitignore`).\n"
        "On a fresh clone, create it with one command:\n\n"
        "    python setup-venv.py\n"
    )
