import json
from pathlib import Path

from .mcp_catalog import build_mcp_json

LAYOUT_DIRS = [
    ".claude/agents", ".claude/skills", ".claude/hooks",
    "src/cf", "src/cfe", "tasks",
]


def scaffold_layout(project_dir) -> None:
    base = Path(project_dir)
    for rel in LAYOUT_DIRS:
        (base / rel).mkdir(parents=True, exist_ok=True)


def write_json(path, data) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_preserving(path, content, *, update: bool) -> None:
    path = Path(path)
    if update and path.exists():
        backup = path.with_name(path.name + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")


def write_env_files(config, *, update: bool) -> None:
    # Пишем только .mcp.json в корень проекта. docker-compose.mcp.yml не нужен:
    # контейнеры MCP поднимаются со страницы «MCP-серверы».
    base = Path(config.project_dir)
    write_json(base / ".mcp.json", build_mcp_json(config.mcp))
