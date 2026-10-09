import json
from dataclasses import dataclass


@dataclass(frozen=True)
class McpSpec:
    id: str
    title: str
    transport: str          # "http" | "stdio"
    default_port: int | None
    image: str | None       # образ для managed; None для stdio-only
    needs_secret: bool
    kind: str = "docker"
    needs_token: bool = False
    download: str | None = None


# Порты/образы — стартовые значения, уточняются при интеграции с docker_1c_sandbox.
CATALOG: dict[str, McpSpec] = {
    "1c-md": McpSpec("1c-md", "Запросы к метаданным", "http", 8811,
                     "ai1c/mcp-1c-md:latest", False,
                     kind="extension", download="deps/mcp_tools_cfe/MCP_Сервер.cfe"),
    "1c-syntax-checker-mcp": McpSpec("1c-syntax-checker-mcp",
                     "Статический анализ BSL", "http", 8812,
                     "ai1c/mcp-bsl-syntax:latest", False),
    "bsl-platform-context": McpSpec("bsl-platform-context",
                     "Справка по платформе", "http", 8813,
                     "ai1c/mcp-bsl-context:latest", False),
    "1c-naparnic": McpSpec("1c-naparnic", "1С:Напарник", "http", 8814,
                     "ai1c/mcp-1c-naparnic:latest", True,
                     needs_token=True),
    "code-index": McpSpec("code-index", "Индекс кодовой базы", "http", 8815,
                     "ai1c/mcp-code-index:latest", False),
}


def _external_entry(endpoint: str) -> dict:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        raise ValueError("для external-режима укажите endpoint (url или команду)")
    if endpoint.startswith(("http://", "https://")):
        return {"url": endpoint}
    # команда вида "cmd arg1 arg2"
    parts = endpoint.split()
    return {"command": parts[0], "args": parts[1:]}


def _parse_connection(fragment: str, sel_id: str) -> tuple[str, dict]:
    """Разбирает фрагмент `"<имя>": { ... }` справочника MCP.

    Возвращает (ключ, запись). Ключ берётся из фрагмента, а не из sel.id.
    """
    try:
        entry = json.loads("{" + fragment + "}")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"не удалось разобрать connection MCP-сервера {sel_id}: {exc}"
        ) from exc
    if not isinstance(entry, dict) or len(entry) != 1:
        raise ValueError(
            f"connection MCP-сервера {sel_id} должен задавать ровно один сервер"
        )
    (name, value), = entry.items()
    if not isinstance(value, dict):
        raise ValueError(
            f"connection MCP-сервера {sel_id}: значение сервера должно быть объектом"
        )
    return name, value


def _server_name(sel) -> str:
    """Ключ сервера в .mcp.json для выбранного MCP.

    С connection — имя берётся из фрагмента справочника; иначе — sel.id
    (standard_key вида или имя карточки). Единый источник истины для
    build_mcp_json и mcp_name_overrides.
    """
    connection = getattr(sel, "connection", None)
    if connection:
        name, _ = _parse_connection(connection, sel.id)
        return name
    return sel.id


def build_mcp_json(selections, catalog=CATALOG) -> dict:
    servers: dict[str, dict] = {}
    for sel in selections:
        if not sel.enabled:
            continue
        name = _server_name(sel)
        connection = getattr(sel, "connection", None)
        if connection:
            _, value = _parse_connection(connection, sel.id)
            servers[name] = value
            continue
        if sel.id not in catalog:
            raise ValueError(f"неизвестный MCP-сервер: {sel.id}")
        spec = catalog[sel.id]
        if sel.mode == "external":
            servers[name] = _external_entry(sel.endpoint or "")
        elif spec.transport == "http":
            servers[name] = {"url": f"http://127.0.0.1:{spec.default_port}"}
        else:  # managed stdio: команда docker exec по container id (sel.id)
            servers[name] = {"command": "docker",
                             "args": ["exec", "-i", sel.id]}
    return {"mcpServers": servers}


def mcp_name_overrides(selections) -> dict[str, str]:
    """{плейсхолдер: актуальное_имя} для включённых выбранных MCP.

    Плейсхолдер — дефолтный mcp_name вида (env/mcp_types). Пропускаем виды без
    дефолтного имени, неизвестные виды и случаи, где актуальное имя совпадает
    с плейсхолдером.
    """
    from .mcp_types import get_type   # локальный импорт — без цикла модулей
    overrides: dict[str, str] = {}
    for sel in selections:
        if not getattr(sel, "enabled", False):
            continue
        try:
            placeholder = get_type(sel.id).defaults.get("mcp_name")
        except KeyError:
            placeholder = None
        if not placeholder:
            continue
        actual = _server_name(sel)
        if actual and actual != placeholder:
            overrides[placeholder] = actual
    return overrides


