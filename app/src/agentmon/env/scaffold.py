import json

from .mcp_catalog import build_mcp_json

LAYOUT_DIRS = [
    ".claude/agents", ".claude/skills", ".claude/hooks",
    "src/cf", "src/cfe", "tasks",
]


def scaffold_layout(prov, project_dir) -> None:
    prov.mkdirs([f"{project_dir}/{rel}" for rel in LAYOUT_DIRS])


def write_json(prov, path, data) -> None:
    prov.write_text(
        path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_preserving(prov, path, content, *, update: bool) -> None:
    if update and prov.exists(path):
        prov.write_text(path + ".bak", prov.read_text(path))
    prov.write_text(path, content)


def write_env_files(prov, config, *, update: bool) -> None:
    # Пишем только .mcp.json в корень проекта (docker-compose.mcp.yml не нужен:
    # контейнеры MCP поднимаются со страницы «MCP-серверы»).
    write_json(prov, f"{config.project_dir}/.mcp.json", build_mcp_json(config.mcp))
