"""Тесты подготовки benchmark-окружения (без 1С, Docker и PostgreSQL)."""
from pathlib import Path

import pytest

from agentmon.env.bench_setup import BenchConfig, SetupError, load_config, parse_env_file


def make_platform(tmp_path: Path) -> Path:
    """Фейковый бинарник платформы в каталоге с версией в пути."""
    platform = tmp_path / "8.3.27.2130"
    platform.mkdir(exist_ok=True)
    binary = platform / "1cv8"
    binary.write_text("", encoding="utf-8")
    return binary


def write_env(tmp_path: Path, **overrides: str) -> Path:
    binary = make_platform(tmp_path) if not (tmp_path / "8.3.27.2130" / "1cv8").exists() else (
        tmp_path / "8.3.27.2130" / "1cv8")
    values = {
        "BENCH_PROJECT_NAME": "bench",
        "BENCH_PROJECT_DIR": str(tmp_path / "project"),
        "BENCH_DEVELOPER_ID": "alex",
        "BENCH_DEVELOPER_EMAIL": "alex@example.ru",
        "BENCH_PLATFORM_PATH": str(binary),
        "BENCH_DB_CONNECTION": "Srvr=localhost;Ref=bench",
        "BENCH_DB_USER": "Администратор",
        "BENCH_DB_PASSWORD": "",
        "MCP_BSL_LS_URL": "http://localhost:8001/mcp",
        "MCP_1C_PLATFORM_URL": "http://localhost:8002/sse",
        "MCP_CODE_INDEX_PORT": "8004",
    }
    values.update(overrides)
    path = tmp_path / "test.env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return path


def test_parse_env_file_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "test.env"
    path.write_text("# comment\n\nA=1\nB=two=2\n", encoding="utf-8")
    assert parse_env_file(path) == {"A": "1", "B": "two=2"}


def test_load_config_required_optional_and_defaults(tmp_path):
    env = write_env(tmp_path)
    cfg = load_config(env, repo_root=tmp_path)
    assert isinstance(cfg, BenchConfig)
    assert cfg.project_name == "bench"
    assert cfg.project_dir == str((tmp_path / "project").resolve())
    assert cfg.platform_version == "8.3.27.2130"
    assert cfg.db_kind == "server"
    assert cfg.db_connection == "Srvr=localhost;Ref=bench"
    assert cfg.code_index_port == 8004
    assert cfg.code_index_host == "localhost"
    assert cfg.code_index_wait_minutes == 360
    assert cfg.one_c_md_url is None
    assert cfg.dt_path is None


def test_load_config_allows_empty_password(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    assert cfg.db_password == ""


def test_load_config_missing_required_key(tmp_path):
    env = write_env(tmp_path)
    env.write_text(
        env.read_text(encoding="utf-8").replace("BENCH_DB_USER=Администратор\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(SetupError, match="BENCH_DB_USER"):
        load_config(env, repo_root=tmp_path)


def test_load_config_rejects_relative_project_dir(tmp_path):
    with pytest.raises(SetupError, match="абсолют"):
        load_config(write_env(tmp_path, BENCH_PROJECT_DIR="relative"), repo_root=tmp_path)


def test_load_config_warns_unknown_key(tmp_path):
    warnings = []
    load_config(
        write_env(tmp_path, UNKNOWN_KEY="x"),
        repo_root=tmp_path,
        warn=warnings.append,
    )
    assert any("UNKNOWN_KEY" in warning for warning in warnings)


def test_load_config_dt_path_is_relative_to_repo(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="benchmark/base.dt"),
        repo_root=tmp_path,
    )
    assert cfg.dt_path == str((tmp_path / "benchmark" / "base.dt").resolve())


def test_load_config_optional_1c_md_and_code_index_overrides(tmp_path):
    cfg = load_config(
        write_env(
            tmp_path,
            MCP_1C_MD_URL="http://localhost/t_bench/hs/mcp",
            MCP_CODE_INDEX_HOST="127.0.0.1",
            MCP_CODE_INDEX_PORT="8104",
            CODE_INDEX_WAIT_MINUTES="120",
        ),
        repo_root=tmp_path,
    )
    assert cfg.one_c_md_url == "http://localhost/t_bench/hs/mcp"
    assert cfg.code_index_host == "127.0.0.1"
    assert cfg.code_index_port == 8104
    assert cfg.code_index_wait_minutes == 120


import json

from agentmon.env.bench_setup import (
    build_env_config,
    build_mcp_plans,
    create_project_row,
    preflight,
    resolve_mcp_cards,
)
from agentmon.env.config_schema import EnvConfig
from agentmon.env.mcp_catalog import build_mcp_json
from agentmon.paths import same_path
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.mcp import McpRepo
from agentmon.store.projects import ProjectRepo
from agentmon.store.schema import init_schema


def make_store(tmp_path: Path):
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return store


def make_registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(open_db(tmp_path / "agentmon.db"))


def make_repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "benchmark" / "cf").mkdir(parents=True)
    (root / "app" / "web" / "assets").mkdir(parents=True)
    (root / "app" / "web" / "assets" / "ЮнитТесты.cfe").write_bytes(b"")
    (root / "deps" / "mcp_tools_cfe").mkdir(parents=True)
    (root / "deps" / "mcp_tools_cfe" / "1c-mcp-tools-1.0.6.cfe").write_bytes(b"")
    return root


def test_preflight_ok(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    preflight(cfg, repo_root=make_repo_root(tmp_path), store=store,
              registry=registry, tcp_ok=lambda url: True)


def test_preflight_rejects_non_empty_project_dir(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    (Path(cfg.project_dir) / "x").write_text("x")
    with pytest.raises(SetupError, match="не пуст"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True)


def test_preflight_rejects_duplicate_project(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store = make_store(tmp_path)
    create_project_row(store, cfg)
    with pytest.raises(SetupError, match="уже существует"):
        preflight(cfg, repo_root=make_repo_root(tmp_path), store=store,
                  registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_rejects_unreachable_shared_mcp(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    with pytest.raises(SetupError, match="недоступен"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: False)


def test_preflight_requires_cf_and_extensions(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    root = make_repo_root(tmp_path)
    (root / "app" / "web" / "assets" / "ЮнитТесты.cfe").unlink()
    with pytest.raises(SetupError, match="ЮнитТесты.cfe"):
        preflight(cfg, repo_root=root, store=make_store(tmp_path),
                  registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_dt_branch_does_not_require_cf(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="base.dt"), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    root = make_repo_root(tmp_path)
    (root / "benchmark" / "cf").rmdir()
    (tmp_path / "base.dt").write_bytes(b"")
    # project_dir пуст; dt существует
    preflight(cfg, repo_root=root, store=make_store(tmp_path),
              registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_rejects_missing_dt(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="missing.dt"), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    with pytest.raises(SetupError, match="BENCH_DT_PATH"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True)


def test_preflight_rejects_registered_path(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    registry = make_registry(tmp_path)
    registry.add(name="old", path=cfg.project_dir, backend="local")
    with pytest.raises(SetupError, match="реестр"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=registry,
                  tcp_ok=lambda url: True)


def test_build_mcp_plans_without_1c_md(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "code_index"]
    code_index = plans[-1]
    assert code_index.catalog_dir == str(Path(cfg.project_dir) / "src" / "cf")
    assert code_index.project_name == cfg.project_name
    assert json.loads("{" + code_index.connection_json + "}") == {
        "code_index": {
            "type": "http",
            "url": "http://localhost:8004/mcp",
        }
    }
    servers = build_mcp_json(build_env_config(cfg, plans).mcp)["mcpServers"]
    assert set(servers) == {"bsl_ls", "1c_platform", "code_index"}


def test_build_mcp_plans_with_1c_md(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_MD_URL="http://localhost/bench/hs/mcp"),
        repo_root=tmp_path,
    )
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "1c-md", "code_index"]
    md = plans[2]
    assert md.standard_key == "1c-md-queries"
    assert json.loads("{" + md.connection_json + "}")["1c-md"]["url"] == (
        "http://localhost/bench/hs/mcp")


def test_build_env_config_produces_mcp_json(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_MD_URL="http://localhost/bench/hs/mcp"),
        repo_root=tmp_path,
    )
    config = build_env_config(cfg, build_mcp_plans(cfg))
    assert isinstance(config, EnvConfig)
    assert config.agents == []
    servers = build_mcp_json(config.mcp)["mcpServers"]
    assert set(servers) == {"bsl_ls", "1c_platform", "1c-md", "code_index"}
    assert servers["1c_platform"]["type"] == "stdio"
    assert servers["1c_platform"]["args"][1] == "http://localhost:8002/sse"


def test_resolve_mcp_cards_reuses_shared_and_creates_project_cards(tmp_path):
    store = make_store(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project_id = create_project_row(store, cfg)
    repo = McpRepo(store)
    plans = build_mcp_plans(cfg)

    ids, created = resolve_mcp_cards(
        repo, plans, project_id=project_id, project_name=cfg.project_name)
    assert set(ids) == {"bsl-ls", "1c-platform", "code-index"}
    assert len(created) == 3

    cfg2 = load_config(
        write_env(tmp_path, BENCH_PROJECT_NAME="bench2",
                  BENCH_PROJECT_DIR=str(tmp_path / "project2")),
        repo_root=tmp_path)
    other_id = create_project_row(store, cfg2)
    ids2, created2 = resolve_mcp_cards(
        repo, build_mcp_plans(cfg2), project_id=other_id,
        project_name=cfg2.project_name)
    assert set(ids2) == set(ids)
    # bsl_ls и 1c_platform переиспользованы, code-index — новый (другой
    # catalog_dir/project_name), поэтому создана ровно одна карточка.
    assert len(created2) == 1
    assert repo.get(ids["code-index"])["catalog_dir"] != repo.get(
        ids2["code-index"])["catalog_dir"]
