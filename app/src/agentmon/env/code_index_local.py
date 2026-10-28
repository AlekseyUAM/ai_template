"""Оркестратор локального (нативного) развёртывания code-index."""
from pathlib import Path

from .mcp_docker_recipes import _daemon_toml
from .code_index_release import download_binary as _download
from .autostart import install_and_start as _install


def deploy_local(*, mid, code_index_dir, catalog_dir, project_name, port,
                 download=_download, install=_install):
    """Генератор строк лога: скачать bsl-indexer, написать daemon.toml, поставить
    индексатор и MCP-сервер в автозапуск (и стартовать)."""
    yield (f"▶ Локальное развёртывание code-index: проект «{project_name}», "
           f"порт {port}")
    buf = []
    binary = download(code_index_dir, log=buf.append)
    for s in buf:
        yield s

    toml_path = Path(code_index_dir) / "daemon.toml"
    toml_path.write_text(_daemon_toml(project_name, catalog_dir),
                         encoding="utf-8")
    yield (f"✓ daemon.toml: {toml_path} (alias={project_name}, "
           f"path={catalog_dir})")

    home_env = {"CODE_INDEX_HOME": str(code_index_dir)}

    yield "=== Автозапуск: индексатор (daemon) ==="
    for s in install(f"ai1c-code-index-daemon-{mid}",
                     [str(binary), "daemon", "run"],
                     env=home_env, state_dir=code_index_dir):
        yield s

    yield "=== Автозапуск: MCP-сервер (serve) ==="
    serve_env = {**home_env, "MCP_HTTP_HOST": "127.0.0.1",
                 "MCP_HTTP_PORT": str(port)}
    for s in install(f"ai1c-code-index-mcp-{mid}", [str(binary), "serve"],
                     env=serve_env, state_dir=code_index_dir):
        yield s

    yield f"✓ Готово. MCP доступен на http://127.0.0.1:{port}/mcp"
