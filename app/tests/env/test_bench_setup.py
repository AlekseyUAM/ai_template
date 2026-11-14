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
