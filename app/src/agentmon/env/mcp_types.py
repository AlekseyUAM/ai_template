"""Виды MCP для справочника (страница «Справочник MCP»).

Это описание карточки MCP в справочнике: какие поля показывать, значения по
умолчанию и шаблон поля «Подключение». Отдельно от `mcp_catalog.CATALOG`, который
обслуживает генерацию `.mcp.json` мастером проекта.

Шаблон подключения содержит плейсхолдеры `{mcp_name}`, `{url}`, `{port}` — и
сервер (`build_connection`), и клиент (mcp.js) подставляют в него значения полей.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class McpType:
    key: str
    title: str
    fields: tuple           # поля карточки по порядку
    connection_template: str
    defaults: dict = field(default_factory=dict)
    action: str | None = None       # "cfe" | "docker" | None
    cfe_path: str | None = None
    required: tuple = ()             # обязательные поля сверх name
    # Пер-типовые подписи полей: переопределяют глобальные (напр. url→"URL хоста").
    field_labels: dict = field(default_factory=dict)


_HTTP_1C = (
    '"{mcp_name}": {\n'
    '    "type": "http",\n'
    '    "url": "http://{url}/{db_name}/hs/mcp"\n'
    '}'
)
_HTTP_PORT = (
    '"{mcp_name}": {\n'
    '    "type": "http",\n'
    '    "url": "http://{url}:{port}/mcp"\n'
    '}'
)
_SSE_PORT = (
    '"{mcp_name}": {\n'
    '    "type": "sse",\n'
    '    "url": "http://{url}:{port}/sse",\n'
    '    "transport": "sse"\n'
    '}'
)
_CUSTOM = (
    '"name": {\n'
    '    "type": "http",\n'
    '    "url": "http://localhost:8000/mcp"\n'
    '}'
)


MCP_TYPES: list[McpType] = [
    McpType(
        key="custom",
        title="Произвольный",
        fields=("name", "purpose", "connection"),
        connection_template=_CUSTOM,
    ),
    McpType(
        key="1c-md",
        title="Метаданные (http-сервис в 1С)",
        fields=("name", "mcp_name", "purpose", "url", "db_name", "connection"),
        connection_template=_HTTP_1C,
        defaults={
            "mcp_name": "1c-md",
            "url": "localhost",
            "db_name": "my_database",
            "purpose": "Вся информация об актуальных метаданных конфигурации",
        },
        action="cfe",
        cfe_path="deps/mcp_tools_cfe/MCP_Сервер.cfe",
        field_labels={"url": "URL хоста", "db_name": "Имя базы"},
    ),
    McpType(
        key="1c-md-queries",
        title="Метаданные + произвольные запросы (http-сервис в 1С)",
        fields=("name", "mcp_name", "purpose", "url", "db_name", "connection"),
        connection_template=_HTTP_1C,
        defaults={
            "mcp_name": "1c-md",
            "url": "localhost",
            "db_name": "my_database",
            "purpose": ("Произвольные запросы к данным, вся информация об "
                        "актуальных метаданных конфигурации"),
        },
        action="cfe",
        cfe_path="deps/mcp_tools_cfe/1c-mcp-tools-1.0.6.cfe",
        field_labels={"url": "URL хоста", "db_name": "Имя базы"},
    ),
    McpType(
        key="bsl-ls",
        title="Статический анализ BSL",
        fields=("name", "mcp_name", "purpose", "url", "port", "connection"),
        connection_template=_HTTP_PORT,
        defaults={
            "mcp_name": "bsl_ls",
            "url": "localhost",
            "port": 8001,
            "purpose": "Статический анализ кода на соответствие стандартам 1С",
        },
        action="docker",
    ),
    McpType(
        key="1c-platform",
        title="Справка по платформе",
        fields=("name", "mcp_name", "purpose", "url", "port",
                "platform_path", "connection"),
        connection_template=_SSE_PORT,
        defaults={
            "mcp_name": "1c_platform",
            "url": "localhost",
            "port": 8002,
            "purpose": ("Справочная информация по встроенным функциям, типам "
                        "данных, методам и свойствам платформы"),
        },
        action="docker",
        required=("platform_path",),
    ),
    McpType(
        key="1c-naparnic",
        title="1С:Напарник",
        fields=("name", "mcp_name", "purpose", "url", "port", "token", "connection"),
        connection_template=_HTTP_PORT,
        defaults={
            "mcp_name": "1c_naparnic",
            "url": "localhost",
            "port": 8003,
            "purpose": ("Объяснение логики кода, любые вопросы по информационно-"
                        "технологическому сопровождению 1С"),
        },
        action="docker",
    ),
    McpType(
        key="code-index",
        title="Индексированная кодовая база",
        fields=("name", "mcp_name", "purpose", "url", "port", "catalog_dir", "connection"),
        connection_template=_HTTP_PORT,
        defaults={
            "mcp_name": "code_index",
            "url": "localhost",
            "port": 8004,
            "purpose": ("Полнотекстовый поиск по функциям и классам, граф "
                        "вызовов, паспорт объекта, смысловой поиск процедур по "
                        "именам, синонимам и комментариям"),
        },
        action="docker",
        required=("catalog_dir",),
    ),
]

_BY_KEY = {t.key: t for t in MCP_TYPES}


def get_type(key: str) -> McpType:
    """Возвращает описание вида MCP по ключу или бросает KeyError."""
    return _BY_KEY[key]


def build_connection(key: str, *, mcp_name=None, url=None, port=None,
                     db_name=None) -> str:
    """Формирует текст поля «Подключение» из шаблона вида и значений полей.

    Пустые аргументы берутся из defaults вида.
    """
    t = get_type(key)
    eff_name = mcp_name or t.defaults.get("mcp_name", "name")
    eff_url = url or t.defaults.get("url", "localhost")
    eff_port = port if port is not None else t.defaults.get("port", "")
    eff_db = db_name or t.defaults.get("db_name", "my_database")
    # Плейсхолдеры заменяем по токенам, чтобы не трогать литеральные JSON-скобки.
    return (t.connection_template
            .replace("{mcp_name}", str(eff_name))
            .replace("{url}", str(eff_url))
            .replace("{port}", str(eff_port))
            .replace("{db_name}", str(eff_db)))


def types_payload() -> list[dict]:
    """Сериализует виды MCP для фронтенда (/api/mcp/types)."""
    return [
        {
            "key": t.key,
            "title": t.title,
            "fields": list(t.fields),
            "defaults": dict(t.defaults),
            "connection_template": t.connection_template,
            "action": t.action,
            "has_cfe": t.action == "cfe",
            "required": list(t.required),
            "field_labels": dict(t.field_labels),
        }
        for t in MCP_TYPES
    ]
