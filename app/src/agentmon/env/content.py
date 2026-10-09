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


def _copy_tree(src: Path, dst: Path, *, skip=None) -> None:
    for item in sorted(src.rglob("*")):
        if "__pycache__" in item.parts:
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


def deploy_content(config, *, update: bool) -> None:
    project = Path(config.project_dir)
    claude = project / ".claude"
    # template — источник истины: копируем всё дерево целиком, чтобы любой
    # добавленный в шаблон файл/каталог попал в проект. Спец-файлы (_is_special)
    # разворачиваются отдельно ниже.
    _copy_tree(TEMPLATE_DIR, project, skip=_is_special)
    _render_agents(config, claude / "agents")
    write_preserving(claude / "settings.json", _render_settings(), update=update)
    # README проекта — пустой с заголовком-именем (шаблонный template/README.md
    # при установке заменяется на этот). При обновлении версии окружения README
    # не трогаем — он уже принадлежит проекту.
    if not update:
        write_preserving(project / "README.md",
                         f"## {config.project_name}\n", update=update)
        # Подстановка актуальных имён выбранных MCP вместо плейсхолдеров шаблона —
        # только при создании (на обновлении окружения имена не трогаем).
        overrides = mcp_name_overrides(config.mcp)
        if overrides:
            _apply_mcp_names(claude, overrides)
