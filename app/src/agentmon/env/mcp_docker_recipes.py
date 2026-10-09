"""Рецепты запуска стандартных MCP-серверов в Docker (страница «Справочник MCP»).

Для каждого docker-вида задаёт: образ, как собрать его из `deps/` (если можно),
имя env-переменной порта сервера, статические env, нужен ли токен и его env,
монтирование каталога кодовой базы. Чистые функции (`launch_params`) считают
параметры запуска из сохранённой карточки MCP и легко тестируются.
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


def container_name(row) -> str:
    """Имя docker-контейнера для карточки MCP.

    За основу берём «Имя в .mcp.json» (mcp_name), а не «Наименование» — последнее может
    содержать кириллицу/двоеточие и т.п., что недопустимо в именах контейнеров.
    Санитизируем под docker-правила `[a-zA-Z0-9][a-zA-Z0-9_.-]*` и префиксуем.
    """
    base = row.get("mcp_name") or row.get("name") or "mcp"
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", str(base)).strip("-._") or "mcp"
    return f"ai1c-mcp-{safe}"


@dataclass(frozen=True)
class BuildSpec:
    dockerfile: str     # путь относительно корня репозитория
    context: str        # контекст сборки относительно корня репозитория
    build_args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DockerRecipe:
    image: str                  # тег образа для запуска
    port_env: str               # env-переменная, задающая порт сервера
    static_env: dict = field(default_factory=dict)
    token_env: str | None = None   # куда положить токен (если вид его требует)
    catalog_mount: bool = False    # монтировать ли «Каталог кодовой базы»
    platform_env: str | None = None  # env с путём к платформе 1С (+ ro-монтирование)
    needs_host_network: bool = False  # серверу нужен внешний DNS/интернет → сеть хоста
    build: BuildSpec | None = None  # как собрать образ; None → только готовый


RECIPES: dict[str, DockerRecipe] = {
    # Статический анализ BSL — тонкая обёртка FastMCP над BSL LS (один инструмент
    # check). Настройки проверок приходят в самом вызове check(config=...) —
    # монтирования и доступа к ФС проектов не требуется.
    "bsl-ls": DockerRecipe(
        image="ai1c/mcp-bsl-ls:local",
        port_env="BSL_PORT",
        build=BuildSpec(
            dockerfile="app/docker/mcp/bsl-ls.Dockerfile",
            context="app/docker/mcp",
        ),
    ),
    # Справка по платформе — mcp-bsl-context (jar в репо, офлайн-сборка).
    "1c-platform": DockerRecipe(
        image="mcp-bsl-context:latest",
        port_env="MCP_BSL_CONTEXT_PORT",
        platform_env="ONEC_PLATFORM_PATH",
        build=BuildSpec(
            dockerfile="deps/docker_1c_sandbox/mcp-bsl-context/Dockerfile",
            context="deps/docker_1c_sandbox/mcp-bsl-context",
        ),
    ),
    # 1С:Напарник — spring-mcp-1c-copilot (Dockerfile в апстриме; только готовый образ).
    "1c-naparnic": DockerRecipe(
        image="copilot-spring-mcp-1c-copilot:latest",
        port_env="SSE_PORT",
        token_env="ONEC_AI_TOKEN",
        needs_host_network=True,   # проксирует запросы к code.1c.ai → нужен внешний DNS
        build=None,
    ),
    # Индексированная кодовая база — bsl-indexer (Rust; сборка из deps).
    "code-index": DockerRecipe(
        image="bsl-indexer:local",
        port_env="MCP_HTTP_PORT",
        static_env={"MCP_HTTP_HOST": "0.0.0.0",
                    "CODE_INDEX_HOME": "/data/code-index-home"},
        catalog_mount=True,
        build=BuildSpec(
            dockerfile="deps/code-index-mcp/deploy/docker/Dockerfile",
            context="deps/code-index-mcp",
        ),
    ),
}

_DAEMON_TOML = """# Сгенерировано автоматически при развёртывании code-index.
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[paths]]
path = "/repos/src"
alias = "src"
language = "bsl"
"""


def recipe_for(type_key: str) -> DockerRecipe | None:
    """Рецепт docker-запуска по ключу вида MCP или None, если вид не docker."""
    return RECIPES.get(type_key)


def launch_params(type_key: str, *, port: int, token=None,
                  catalog_dir=None, state_dir=None, platform_path=None) -> dict:
    """Считает параметры `mcp_docker.launch` из рецепта и данных карточки.

    Возвращает dict: image, internal_port, env, volumes, network.
    """
    recipe = RECIPES.get(type_key)
    if recipe is None:
        raise ValueError(f"нет docker-рецепта для вида MCP: {type_key}")

    env = dict(recipe.static_env)
    env[recipe.port_env] = str(port)
    if recipe.token_env:
        env[recipe.token_env] = token or ""

    volumes: list[str] = []
    if recipe.platform_env:
        if not platform_path:
            raise ValueError("для этого вида MCP нужен путь к платформе 1С")
        env[recipe.platform_env] = platform_path
        # путь к платформе одинаков внутри и снаружи (сервер читает файлы по нему)
        volumes.append(f"{platform_path}:{platform_path}:ro")
    if recipe.catalog_mount:
        if not catalog_dir:
            raise ValueError("для code-index нужен каталог кодовой базы")
        if not state_dir:
            raise ValueError("для code-index нужен state_dir для daemon.toml")
        sp = Path(state_dir)
        sp.mkdir(parents=True, exist_ok=True)
        (sp / "daemon.toml").write_text(_DAEMON_TOML, encoding="utf-8")
        # каталог кодовой базы rw (демон пишет <repo>/.code-index/index.db рядом)
        volumes.append(f"{catalog_dir}:/repos/src")
        # state-том с daemon.toml и runtime демона
        volumes.append(f"{sp}:/data/code-index-home")

    # сеть хоста нужна серверам с внешним DNS (напр. напарник → code.1c.ai);
    # host-сеть применима на Linux (на Docker Desktop DNS bridge и так работает)
    network = None
    if recipe.needs_host_network and sys.platform.startswith("linux"):
        network = "host"

    return {
        "image": recipe.image,
        "internal_port": int(port),
        "env": env,
        "volumes": volumes,
        "network": network,
    }
