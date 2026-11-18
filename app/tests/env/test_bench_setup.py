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


def test_load_config_optional_1c_naparnic(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    assert cfg.one_c_naparnic_url is None
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    assert cfg.one_c_naparnic_url == "http://localhost:8003/mcp"


def test_load_config_rejects_bad_1c_naparnic_url(tmp_path):
    with pytest.raises(SetupError, match="MCP_1C_NAPARNIC_URL"):
        load_config(
            write_env(tmp_path, MCP_1C_NAPARNIC_URL="localhost:8003/mcp"),
            repo_root=tmp_path)


import json

from agentmon.env.bench_setup import (
    build_env_config,
    build_mcp_plans,
    create_project_row,
    preflight,
    remove_existing_project,
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


def test_preflight_checks_naparnic_http(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    calls = []
    preflight(cfg, repo_root=make_repo_root(tmp_path),
              store=make_store(tmp_path), registry=make_registry(tmp_path),
              tcp_ok=lambda url: True,
              http_ok=lambda url: calls.append(url) or True)
    assert calls == ["http://localhost:8003/mcp"]


def test_preflight_rejects_unreachable_naparnic(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    with pytest.raises(SetupError, match="MCP_1C_NAPARNIC_URL"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True,
                  http_ok=lambda url: False)


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


def test_preflight_allow_existing_skips_project_checks(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project_dir = Path(cfg.project_dir)
    project_dir.mkdir(parents=True)
    (project_dir / "x").write_text("x")
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    create_project_row(store, cfg)
    registry.add(name=cfg.project_name, path=cfg.project_dir, backend="local")
    preflight(cfg, repo_root=make_repo_root(tmp_path), store=store,
              registry=registry, tcp_ok=lambda url: True, allow_existing=True)


def test_remove_existing_project_removes_dir_store_registry(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project_dir = Path(cfg.project_dir)
    project_dir.mkdir(parents=True)
    (project_dir / ".1c-devbase.json").write_text("{}", encoding="utf-8")
    (project_dir / "old.txt").write_text("old", encoding="utf-8")
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    create_project_row(store, cfg)
    registry.add(name=cfg.project_name, path=cfg.project_dir, backend="local")

    remove_existing_project(cfg, store=store, registry=registry,
                            log=lambda line: None)

    assert not project_dir.exists()
    assert ProjectRepo(store).list() == []
    assert registry.list() == []


def test_remove_existing_project_refuses_unmarked_dir(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project_dir = Path(cfg.project_dir)
    project_dir.mkdir(parents=True)
    (project_dir / "stranger.txt").write_text("data", encoding="utf-8")

    with pytest.raises(SetupError, match="не похож"):
        remove_existing_project(cfg, store=make_store(tmp_path),
                                registry=make_registry(tmp_path),
                                log=lambda line: None)

    assert project_dir.exists()
    assert (project_dir / "stranger.txt").exists()


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


def test_build_mcp_plans_with_1c_naparnic(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://ai.local:8003/mcp"),
        repo_root=tmp_path,
    )
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "1c_naparnic", "code_index"]
    naparnic = plans[2]
    assert naparnic.standard_key == "1c-naparnic"
    assert naparnic.kind == "docker"
    assert naparnic.url == "ai.local"
    assert naparnic.port == 8003
    assert json.loads("{" + naparnic.connection_json + "}") == {
        "1c_naparnic": {
            "type": "http",
            "url": "http://ai.local:8003/mcp",
        }
    }
    servers = build_mcp_json(build_env_config(cfg, plans).mcp)["mcpServers"]
    assert servers["1c_naparnic"] == {
        "type": "http", "url": "http://ai.local:8003/mcp"}


def test_build_mcp_plans_order_with_both_optional(tmp_path):
    cfg = load_config(
        write_env(tmp_path,
                  MCP_1C_MD_URL="http://localhost/bench/hs/mcp",
                  MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path,
    )
    assert [plan.mcp_name for plan in build_mcp_plans(cfg)] == [
        "bsl_ls", "1c_platform", "1c-md", "1c_naparnic", "code_index"]


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


from dataclasses import dataclass

from agentmon.env.bench_setup import (
    _venv_python,
    base_dump_steps,
    base_load_steps,
    build_create_base_command,
    check_mcp_url,
    ensure_base,
    run_batch_step,
)


@dataclass
class RunResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeProv:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def run(self, cmd, cwd=None, timeout=None):
        self.calls.append((list(cmd), cwd))
        return self.results.pop(0) if self.results else RunResult()


def test_create_base_command_server(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    cmd = build_create_base_command(cfg)
    assert cmd[1:] == [
        "CREATEINFOBASE", "Srvr=localhost;Ref=bench"]


def test_create_base_command_file(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DB_CONNECTION=str(tmp_path / "ib")),
        repo_root=tmp_path,
    )
    expected = tmp_path / "ib"
    cmd = build_create_base_command(cfg)
    assert cmd[1:] == ["CREATEINFOBASE", f'File="{expected}"']


def test_ensure_base_creates_file_base_only_when_missing(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DB_CONNECTION=str(tmp_path / "ib")),
        repo_root=tmp_path,
    )
    prov = FakeProv()
    expected = tmp_path / "ib"
    expected.mkdir()
    ensure_base(cfg, prov=prov, log=lambda line: None)
    assert prov.calls == []

    expected.rmdir()
    ensure_base(cfg, prov=prov, log=lambda line: None)
    assert prov.calls[0][0][1:] == [
        "CREATEINFOBASE", f'File="{expected}"']


def test_ensure_base_tolerates_existing_server_base(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    prov = FakeProv([RunResult(1, stderr="база уже существует")])
    lines = []
    ensure_base(cfg, prov=prov, log=lines.append)
    assert prov.calls[0][0][1] == "CREATEINFOBASE"
    assert any("⚠" in line for line in lines)


def test_base_load_steps_without_dt(tmp_path):
    root = make_repo_root(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    steps = base_load_steps(cfg, root)
    assert steps[0] == ["load-config", str(root / "benchmark" / "cf")]
    assert steps[1] == [
        "load-cfg-extension",
        str(root / "app" / "web" / "assets" / "ЮнитТесты.cfe"),
        "--name", "ЮнитТесты",
    ]
    assert steps[2] == ["update-db-cfg", "--extension", "ЮнитТесты"]
    assert steps[3] == [
        "load-cfg-extension",
        str(root / "deps" / "mcp_tools_cfe" / "1c-mcp-tools-1.0.6.cfe"),
        "--name", "mcp_tools",
    ]
    assert steps[4] == ["update-db-cfg", "--extension", "mcp_tools"]


def test_base_load_steps_with_dt(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="base.dt"), repo_root=tmp_path)
    assert base_load_steps(cfg, tmp_path) == [["restore-ib", cfg.dt_path]]


def test_base_dump_steps():
    assert base_dump_steps() == [
        ["dump-config", "src/cf"],
        ["dump-config", "src/cfe", "--all-extensions"],
    ]


def make_project_venv(project: Path) -> Path:
    """Создаёт интерпретатор .venv там же, где его ищет bench_setup.

    Раскладка зависит от ОС: на Windows — Scripts\\python.exe, иначе bin/python.
    """
    python = Path(_venv_python(str(project)))
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("")
    return python


def test_run_batch_step_uses_project_venv_and_raises_on_error(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project = Path(cfg.project_dir)
    venv_python = make_project_venv(project)
    (project / ".claude" / "skills" / "1c-batch" / "scripts").mkdir(parents=True)
    (project / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py").write_text("")

    prov = FakeProv([RunResult(1, stdout="line1\n", stderr="ошибка 1С")])
    with pytest.raises(SetupError, match="ошибка 1С"):
        run_batch_step(cfg.project_dir, ["load-config", "/cf"],
                       prov=prov, log=lambda line: None)
    cmd, cwd = prov.calls[0]
    assert cmd[:2] == [
        str(venv_python),
        str(project / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py"),
    ]
    assert cwd == cfg.project_dir


def test_run_batch_step_retries_db_lock(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project = Path(cfg.project_dir)
    make_project_venv(project)
    (project / ".claude" / "skills" / "1c-batch" / "scripts").mkdir(parents=True)
    (project / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py").write_text("")

    prov = FakeProv([
        RunResult(1, stdout="Ошибка исключительной блокировки информационной базы"),
        RunResult(0, stdout="ok"),
    ])
    sleeps = []
    run_batch_step(cfg.project_dir, ["load-config", "/cf"], prov=prov,
                   retry_delays=(30,), sleep=sleeps.append,
                   log=lambda line: None)
    assert len(prov.calls) == 2
    assert sleeps == [30]


def test_check_mcp_url_fails_when_unreachable(tmp_path):
    with pytest.raises(SetupError, match="недоступен"):
        check_mcp_url("http://localhost:9999/hs/mcp", http_ok=lambda url: False)


def test_check_mcp_url_accepts_reachable():
    check_mcp_url("http://localhost:9999/hs/mcp", http_ok=lambda url: True)


import shutil

from agentmon.env.bench_setup import (
    ImportedTask,
    commit_baseline,
    commit_init,
    import_tasks,
)
from agentmon.store.tasks import TaskRepo


def make_tasks(root: Path) -> Path:
    task_dir = root / "benchmark" / "tasks" / "task#001"
    task_dir.mkdir(parents=True)
    data = {
        "id": 23,
        "project_id": 13,
        "name": "Метаданные",
        "identifier": "#001",
        "goal": "Добавить метаданные",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "Тесты",
        "status": "planned",
        "stage": None,
        "started_at": None,
        "finished_at": None,
        "created_at": None,
        "kind": "real",
        "update_db": True,
        "max_minutes": 60,
        "mark_changes": False,
        "developer_id": "alex",
        "stages": [
            {"name": "develop", "enabled": True, "subagent": "developer",
             "artifact": "DEVELOP.md", "gate": False, "approved": False,
             "status": "pending", "changed_files": [], "started_at": None,
             "finished_at": None, "iteration": 1},
        ],
    }
    (task_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "TASK.md").write_text(
        "# Задача #001 (#23): Метаданные\n\n## Цель\nДобавить метаданные\n\n"
        "## Правка пользователя\nНе потерять эту строку.\n",
        encoding="utf-8",
    )
    (task_dir / "extra.txt").write_text("extra", encoding="utf-8")
    return task_dir


def test_import_tasks_copies_rewrites_and_preserves_body(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)

    imported = import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                            store=store, log=lambda line: None)

    assert len(imported) == 1
    item = imported[0]
    assert isinstance(item, ImportedTask)
    assert item.identifier == "#001"
    assert item.folder == "task#001"

    task_row = TaskRepo(store).get(item.task_id)
    assert task_row["project_id"] == project_id
    assert task_row["name"] == "Метаданные"
    assert task_row["identifier"] == "#001"
    assert json.loads(task_row["stages_json"])[0]["name"] == "develop"

    task_dir = Path(cfg.project_dir) / "tasks" / "task#001"
    assert (task_dir / "extra.txt").read_text(encoding="utf-8") == "extra"
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    assert data["id"] == item.task_id
    assert data["project_id"] == project_id
    assert data["developer_id"] == "alex"
    assert data["status"] == "planned"
    assert data["created_at"] and "T" in data["created_at"]
    assert data["update_db"] is True
    assert data["mark_changes"] is False
    assert data["stages"][0]["status"] == "pending"

    md = (task_dir / "TASK.md").read_text(encoding="utf-8")
    assert md.startswith(f"# Задача #001 (#{item.task_id}):")
    assert "Не потерять эту строку." in md


def test_import_tasks_requires_at_least_one_task(tmp_path):
    root = make_repo_root(tmp_path)
    (root / "benchmark" / "tasks").mkdir(parents=True)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)
    with pytest.raises(SetupError, match="ни одной задачи"):
        import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                     store=store, log=lambda line: None)


class GitProv:
    def __init__(self):
        self.calls = []

    def mkdirs(self, paths):
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

    def exists(self, path):
        return False

    def is_file(self, path):
        return False

    def write_text(self, path, content):
        pass

    def read_text(self, path):
        return ""

    def run(self, cmd, cwd=None, timeout=None):
        self.calls.append((list(cmd), cwd))
        return RunResult()


def test_commit_init_and_baseline(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    Path(cfg.project_dir).mkdir(parents=True)
    prov = GitProv()

    commit_init(cfg, prov)
    assert prov.calls[0][0] == ["git", "init"]
    init_commit = prov.calls[-1][0]
    assert "commit" in init_commit and "init" in init_commit

    tasks = [ImportedTask(identifier="#001", task_id=7, folder="task#001")]
    commit_baseline(cfg, tasks, prov)
    baseline_commit = prov.calls[-1][0]
    assert "baseline before task#001" in baseline_commit


def test_import_tasks_copy_failure_leaves_no_task_row(tmp_path, monkeypatch):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)

    def boom(src, dst, *args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(shutil, "copytree", boom)

    with pytest.raises(OSError, match="boom"):
        import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                     store=store, log=lambda line: None)

    assert TaskRepo(store).list(project_id=project_id) == []


class FailingCommitProv(GitProv):
    def run(self, cmd, cwd=None, timeout=None):
        self.calls.append((list(cmd), cwd))
        if "commit" in cmd:
            return RunResult(1, stderr="boom")
        return RunResult()


def test_commit_init_raises_on_commit_failure(tmp_path):
    root = make_repo_root(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    Path(cfg.project_dir).mkdir(parents=True)
    prov = FailingCommitProv()

    with pytest.raises(RuntimeError, match="boom"):
        commit_init(cfg, prov)
    assert prov.calls[0][0] == ["git", "init"]


from agentmon.env.bench_setup import (
    CODE_INDEX_CONTAINER,
    launch_code_index,
    wait_code_index_ready,
)


def test_launch_code_index_removes_old_container_with_volumes(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project = Path(cfg.project_dir)
    (project / "src" / "cf").mkdir(parents=True)
    state_root = tmp_path / "repo"
    state_root.mkdir()
    calls = []
    launched = {}

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return RunResult(1)  # docker rm для отсутствующего контейнера

    def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"ok": True, "log": ""}

    name = launch_code_index(
        cfg, repo_root=state_root, mid=42, run=fake_run,
        image_exists=lambda image: True, launch=fake_launch,
        build_image=lambda: (_ for _ in ()).throw(
            AssertionError("готовая сборка не нужна")),
        log=lambda line: None,
    )
    assert name == CODE_INDEX_CONTAINER
    assert calls[0] == ["docker", "rm", "-f", "-v", CODE_INDEX_CONTAINER]
    assert launched["name"] == CODE_INDEX_CONTAINER
    assert launched["port"] == cfg.code_index_port
    from agentmon.env.mcp_docker_recipes import _docker_host_path

    volumes = launched["volumes"]
    assert f"{_docker_host_path(project / 'src' / 'cf')}:/repos/src" in volumes
    toml = state_root / ".ai1c" / "mcp-state" / "42" / "daemon.toml"
    assert toml.is_file()
    assert f'alias = "{cfg.project_name}"' in toml.read_text(encoding="utf-8")
    assert 'path = "/repos/src"' in toml.read_text(encoding="utf-8")


def test_launch_code_index_default_image_exists_uses_module_probe(
        tmp_path, monkeypatch):
    from agentmon.env import bench_setup, mcp_docker
    from agentmon.env.mcp_docker_recipes import recipe_for

    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    (Path(cfg.project_dir) / "src" / "cf").mkdir(parents=True)
    probed = []
    launched = {}

    def fake_image_exists(tag):
        probed.append(tag)
        return True

    def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"ok": True, "log": ""}

    monkeypatch.setattr(mcp_docker, "image_exists", fake_image_exists)
    name = launch_code_index(
        cfg, repo_root=tmp_path, mid=7,
        run=lambda cmd, **kwargs: bench_setup.subprocess.CompletedProcess(
            list(cmd), 0, "", ""),
        launch=fake_launch,
        log=lambda line: None,
    )
    assert probed == [recipe_for("code-index").image]
    assert name == CODE_INDEX_CONTAINER
    assert launched["name"] == CODE_INDEX_CONTAINER


def test_launch_code_index_raises_when_launch_fails(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    with pytest.raises(SetupError, match="контейнер"):
        launch_code_index(
            cfg, repo_root=tmp_path, mid=1,
            run=lambda cmd, **kwargs: RunResult(),
            image_exists=lambda image: True,
            launch=lambda **kwargs: {"ok": False, "log": "boom"},
            log=lambda line: None,
        )


def test_wait_code_index_ready_returns_when_ready(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    status = json.dumps({
        "status": "running",
        "paths": [{"path": "/repos/src", "status": "ready"}],
    })
    lines = []
    wait_code_index_ready(
        CODE_INDEX_CONTAINER, cfg=cfg,
        run=lambda cmd, **kwargs: RunResult(0, status),
        sleep=lambda seconds: None, clock=lambda: 0.0,
        log=lines.append,
    )
    assert any("готов" in line for line in lines)


def test_wait_code_index_ready_fails_on_error_status(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    status = json.dumps({
        "status": "running",
        "paths": [{"path": "/repos/src", "status": "error"}],
    })
    with pytest.raises(SetupError, match="error"):
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=lambda cmd, **kwargs: RunResult(0, status),
            sleep=lambda seconds: None, clock=lambda: 0.0,
            log=lambda line: None,
        )


def test_wait_code_index_ready_times_out(tmp_path):
    cfg = load_config(
        write_env(tmp_path, CODE_INDEX_WAIT_MINUTES="1"), repo_root=tmp_path)
    now = [0.0]

    def fake_sleep(seconds):
        now[0] += seconds

    with pytest.raises(SetupError, match="CODE_INDEX_WAIT_MINUTES"):
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=lambda cmd, **kwargs: RunResult(
                0, json.dumps({"paths": [
                    {"path": "/repos/src", "status": "initial_indexing"}]})),
            sleep=fake_sleep, clock=lambda: now[0],
            log=lambda line: None,
        )


from agentmon.env.bench_setup import RollbackState, run_setup, rollback


class OrchestratorProv(GitProv):
    """Провизор, которого хватает install_env-фейку и git-хелперам."""

    def mkdirs(self, paths):
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)


def fake_install_env(config, **kwargs):
    Path(config.project_dir, ".claude").mkdir(parents=True, exist_ok=True)
    Path(config.project_dir, ".claude", "VERSION").write_text("test")
    (Path(config.project_dir) / "src" / "cf").mkdir(parents=True, exist_ok=True)
    (Path(config.project_dir) / "src" / "cfe").mkdir(parents=True, exist_ok=True)
    return []


def test_run_setup_happy_path(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    batch_calls, waited = [], []

    result = run_setup(
        cfg, repo_root=root, store=store, registry=registry,
        prov=OrchestratorProv(),
        tcp_ok=lambda url: True,
        http_ok=lambda url: True,
        install_env=fake_install_env,
        batch_run=lambda project_dir, args, **kwargs: batch_calls.append(args),
        launch_index=lambda cfg, **kwargs: CODE_INDEX_CONTAINER,
        wait_index=lambda name, **kwargs: waited.append(name),
        log=lambda line: None,
    )

    assert result.project_id > 0
    assert result.container == CODE_INDEX_CONTAINER
    assert result.task_ids and len(result.task_ids) == 1
    assert batch_calls[0][0] == "load-config"
    assert batch_calls[-1][0] == "dump-config"
    assert waited == [CODE_INDEX_CONTAINER]
    assert registry.list()[0].path == cfg.project_dir
    assert TaskRepo(store).list(project_id=result.project_id)


def test_run_setup_recreate_removes_old_project(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    project_dir = Path(cfg.project_dir)
    project_dir.mkdir(parents=True)
    (project_dir / ".1c-devbase.json").write_text("{}", encoding="utf-8")
    (project_dir / "old.txt").write_text("old", encoding="utf-8")
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    create_project_row(store, cfg)
    registry.add(name=cfg.project_name, path=cfg.project_dir, backend="local")

    result = run_setup(
        cfg, repo_root=root, store=store, registry=registry,
        prov=OrchestratorProv(), recreate=True,
        tcp_ok=lambda url: True,
        http_ok=lambda url: True,
        install_env=fake_install_env,
        batch_run=lambda project_dir, args, **kwargs: None,
        launch_index=lambda cfg, **kwargs: CODE_INDEX_CONTAINER,
        wait_index=lambda name, **kwargs: None,
        log=lambda line: None,
    )

    assert not (project_dir / "old.txt").exists()
    assert [row["id"] for row in ProjectRepo(store).list()] == [result.project_id]
    assert len(registry.list()) == 1
    assert registry.list()[0].path == cfg.project_dir


def test_run_setup_recreate_keeps_old_project_if_preflight_fails(tmp_path):
    root = make_repo_root(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    project_dir = Path(cfg.project_dir)
    project_dir.mkdir(parents=True)
    (project_dir / ".1c-devbase.json").write_text("{}", encoding="utf-8")
    (project_dir / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(SetupError, match="недоступен"):
        run_setup(
            cfg, repo_root=root, store=make_store(tmp_path),
            registry=make_registry(tmp_path), recreate=True,
            tcp_ok=lambda url: False, log=lambda line: None,
        )

    assert (project_dir / "old.txt").exists()


def test_run_setup_rolls_back_db_and_container_on_error(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    removed = []

    def failing_wait(name, **kwargs):
        raise SetupError("индексация не удалась")

    def fake_run(cmd, **kwargs):
        removed.append(list(cmd))
        return RunResult()

    with pytest.raises(SetupError, match="индексация"):
        run_setup(
            cfg, repo_root=root, store=store, registry=registry,
            prov=OrchestratorProv(), run=fake_run,
            tcp_ok=lambda url: True, http_ok=lambda url: True,
            install_env=fake_install_env,
            batch_run=lambda project_dir, args, **kwargs: None,
            launch_index=lambda cfg, **kwargs: CODE_INDEX_CONTAINER,
            wait_index=failing_wait,
            log=lambda line: None,
        )

    assert ProjectRepo(store).list() == []
    assert McpRepo(store).list() == []
    assert TaskRepo(store).list() == []
    assert registry.list() == []
    assert ["docker", "rm", "-f", "-v", CODE_INDEX_CONTAINER] in removed
    assert Path(cfg.project_dir).exists()


def test_rollback_deletes_created_cards_and_logs_failures(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    mcp_repo = McpRepo(store)
    shared = mcp_repo.add(name="shared", standard_key="bsl-ls")
    own = mcp_repo.add(name="own", standard_key="code-index")
    state = RollbackState(project_dir=cfg.project_dir, project_id=project_id,
                          created_mcp_ids=[own])
    lines = []
    removed = []

    class FlakyStore:
        """Прокси store, на котором падает удаление карточки MCP."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def execute(self, sql, params=None):
            if sql.startswith("DELETE FROM mcp_servers"):
                raise RuntimeError("занята")
            return self._inner.execute(sql, params)

        def transaction(self):
            return self._inner.transaction()

    rollback(state, store=FlakyStore(store),
             run=lambda cmd, **kwargs: removed.append(list(cmd)),
             log=lines.append)

    assert McpRepo(store).get(shared) is not None
    assert McpRepo(store).get(own) is not None
    assert any(f"MCP #{own}" in line and "занята" in line for line in lines)
    assert any("Каталог проекта оставлен" in line for line in lines)
    assert any("Удалите его перед повторным запуском" in line
               for line in lines)
    assert removed == []


def test_rollback_removes_container_after_db(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store = make_store(tmp_path)
    state = RollbackState(project_dir=cfg.project_dir,
                          container=CODE_INDEX_CONTAINER)
    removed = []

    rollback(state, store=store,
             run=lambda cmd, **kwargs: removed.append(list(cmd)),
             log=lambda line: None)

    assert removed == [["docker", "rm", "-f", "-v", CODE_INDEX_CONTAINER]]


def test_rollback_reports_failed_container_removal(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    state = RollbackState(project_dir=cfg.project_dir,
                          container=CODE_INDEX_CONTAINER)
    lines = []

    rollback(state, store=make_store(tmp_path),
             run=lambda cmd, **kwargs: RunResult(
                 1, stderr="no such container"),
             log=lines.append)

    partial = [line for line in lines if "Откат выполнен частично" in line]
    assert partial, lines
    assert "1" in partial[0]
    assert "no such container" in partial[0]
    assert not any(line.startswith("✗ Откат выполнен.") for line in lines)


from agentmon.env.bench_setup import load_env_file


def test_load_env_file_overwrites_existing_keys(tmp_path):
    path = tmp_path / ".ai1c.env"
    path.write_text("# comment\nA=1\n\nB=2\n", encoding="utf-8")
    env = {"A": "old", "C": "keep"}
    load_env_file(path, env)
    assert env == {"A": "1", "B": "2", "C": "keep"}


def test_load_env_file_missing_file_is_noop(tmp_path):
    env = {"A": "old"}
    load_env_file(tmp_path / "absent.env", env)
    assert env == {"A": "old"}


def test_load_config_rejects_malformed_port_in_url(tmp_path):
    with pytest.raises(SetupError, match="MCP_BSL_LS_URL"):
        load_config(
            write_env(tmp_path, MCP_BSL_LS_URL="http://localhost:abc/mcp"),
            repo_root=tmp_path)


def _status_run(status=None, *, inspect_running="true", inspect_rc=0):
    """Фейковый docker run: exec status → status (rc по None), inspect → running.

    Успешный `docker inspect` отдаёт rc=0 и `{{.State.Running}}` в stdout;
    несуществующий контейнер → rc!=0 и пустой stdout.
    """
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "exec"]:
            if status is None:
                return RunResult(1, "", "container not found")
            return RunResult(0, status)
        if cmd[:3] == ["docker", "inspect", "-f"]:
            return RunResult(inspect_rc, f"{inspect_running}\n")
        raise AssertionError(f"неожиданная команда: {cmd}")
    return fake_run


def test_wait_code_index_ready_error_message_includes_diagnostics(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    status = json.dumps({"paths": [
        {"path": "/repos/src", "status": "error", "error": "disk full"}]})
    with pytest.raises(SetupError) as excinfo:
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=_status_run(status), sleep=lambda s: None,
            clock=lambda: 0.0, log=lambda line: None)
    message = str(excinfo.value)
    assert "disk full" in message
    assert CODE_INDEX_CONTAINER in message
    assert str(cfg.code_index_port) in message
    assert "/data/code-index-home/daemon.json" in message


def test_wait_code_index_ready_fails_fast_when_container_stopped(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    sleeps = []
    with pytest.raises(SetupError) as excinfo:
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=_status_run(None, inspect_running="false", inspect_rc=0),
            sleep=sleeps.append, clock=lambda: 0.0,
            log=lambda line: None)
    message = str(excinfo.value)
    assert "не запущен" in message
    assert CODE_INDEX_CONTAINER in message
    assert str(cfg.code_index_port) in message
    assert "/data/code-index-home/daemon.json" in message
    assert f"docker logs {CODE_INDEX_CONTAINER}" in message
    assert sleeps == []


def test_wait_code_index_ready_keeps_waiting_while_container_runs(tmp_path):
    cfg = load_config(
        write_env(tmp_path, CODE_INDEX_WAIT_MINUTES="1"), repo_root=tmp_path)
    now = [0.0]

    def fake_sleep(seconds):
        now[0] += seconds

    with pytest.raises(SetupError) as excinfo:
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=_status_run(None, inspect_running="true"),
            sleep=fake_sleep, clock=lambda: now[0],
            log=lambda line: None)
    message = str(excinfo.value)
    assert "CODE_INDEX_WAIT_MINUTES" in message
    assert CODE_INDEX_CONTAINER in message
    assert str(cfg.code_index_port) in message
    assert "/data/code-index-home/daemon.json" in message
    assert now[0] >= 60


def test_wait_code_index_ready_keeps_waiting_when_inspect_fails(tmp_path):
    cfg = load_config(
        write_env(tmp_path, CODE_INDEX_WAIT_MINUTES="1"), repo_root=tmp_path)
    now = [0.0]

    def fake_sleep(seconds):
        now[0] += seconds

    with pytest.raises(SetupError) as excinfo:
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=_status_run(None, inspect_running="", inspect_rc=1),
            sleep=fake_sleep, clock=lambda: now[0],
            log=lambda line: None)
    message = str(excinfo.value)
    assert "не запущен" not in message
    assert "CODE_INDEX_WAIT_MINUTES" in message
    assert CODE_INDEX_CONTAINER in message
    assert now[0] >= 60


def _tasks_root(tmp_path):
    root = make_repo_root(tmp_path)
    task_dir = make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)
    return root, task_dir, cfg, store, project_id


def _edit_task(task_dir, *, remove=(), **changes):
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    data.update(changes)
    for key in remove:
        data.pop(key, None)
    (task_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_import_tasks_rejects_non_integer_max_minutes(tmp_path):
    root, task_dir, cfg, store, project_id = _tasks_root(tmp_path)
    _edit_task(task_dir, max_minutes="90 мин")
    with pytest.raises(SetupError) as excinfo:
        import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                     store=store, log=lambda line: None)
    message = str(excinfo.value)
    assert "task#001" in message
    assert "90 мин" in message
    assert TaskRepo(store).list(project_id=project_id) == []


def test_import_tasks_rejects_zero_max_minutes(tmp_path):
    root, task_dir, cfg, store, project_id = _tasks_root(tmp_path)
    _edit_task(task_dir, max_minutes=0)
    with pytest.raises(SetupError, match="task#001"):
        import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                     store=store, log=lambda line: None)


def test_import_tasks_defaults_max_minutes_to_60(tmp_path):
    root, task_dir, cfg, store, project_id = _tasks_root(tmp_path)
    _edit_task(task_dir, remove=("max_minutes",))
    imported = import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                            store=store, log=lambda line: None)
    assert TaskRepo(store).get(imported[0].task_id)["max_minutes"] == 60


def test_import_tasks_identifier_falls_back_to_folder_number(tmp_path):
    root, task_dir, cfg, store, project_id = _tasks_root(tmp_path)
    _edit_task(task_dir, identifier="")
    imported = import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                            store=store, log=lambda line: None)
    assert imported[0].identifier == "#001"


def test_import_tasks_warns_when_task_md_header_unrecognized(tmp_path):
    root, task_dir, cfg, store, project_id = _tasks_root(tmp_path)
    (task_dir / "TASK.md").write_text(
        "Задача без шапки\n\n## Цель\nx\n", encoding="utf-8")
    lines = []
    imported = import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                            store=store, log=lines.append)
    assert any("task#001/TASK.md" in line and "⚠" in line for line in lines)
    md = (Path(cfg.project_dir) / "tasks" / "task#001" / "TASK.md").read_text(
        encoding="utf-8")
    assert md.startswith("Задача без шапки")
