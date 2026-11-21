import pytest

from agentmon.env import mcp_docker_recipes as R


def test_container_name_from_mcp_name():
    assert R.container_name({"mcp_name": "1c_naparnic", "name": "1С:Напарник"}) \
        == "ai1c-mcp-1c_naparnic"


def test_container_name_sanitizes_invalid_chars():
    import re
    n = R.container_name({"name": "1С:Напарник"})
    assert n.startswith("ai1c-mcp-")
    assert re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", n)


def test_recipe_none_for_non_docker():
    assert R.recipe_for("custom") is None
    assert R.recipe_for("1c-md") is None
    assert R.recipe_for("unknown") is None


def test_recipe_present_for_docker_types():
    for key in ("bsl-ls", "1c-platform", "1c-naparnic"):
        assert R.recipe_for(key) is not None


def test_code_index_has_no_docker_recipe():
    # code-index разворачивается нативно (code_index_local), рецепта нет
    assert "code-index" not in R.RECIPES
    assert R.recipe_for("code-index") is None
    with pytest.raises(ValueError, match="нет docker-рецепта"):
        R.launch_params("code-index", port=8004)


def test_bsl_ls_params_buildable_no_token():
    # Настройки проверок приходят в вызове check(config=...), а не монтированием —
    # поэтому ни томов, ни доступа к ФС проектов контейнеру не нужно.
    p = R.launch_params("bsl-ls", port=8001)
    assert p["image"] == "ai1c/mcp-bsl-ls:local"
    assert p["internal_port"] == 8001
    assert p["env"]["BSL_PORT"] == "8001"
    assert p["volumes"] == []
    # собирается из репозитория (есть build-спек)
    assert R.recipe_for("bsl-ls").build is not None


def test_naparnic_params_inject_token_and_build_from_deps():
    p = R.launch_params("1c-naparnic", port=8003, token="SECRET")
    assert p["env"]["SSE_PORT"] == "8003"
    assert p["env"]["ONEC_AI_TOKEN"] == "SECRET"
    # образ собирается из апстримного Dockerfile.build (исходники — в deps/)
    b = R.recipe_for("1c-naparnic").build
    assert b is not None
    assert (b.dockerfile, b.context) == (
        "deps/spring-mcp-1c-copilot/Dockerfile.build",
        "deps/spring-mcp-1c-copilot",
    )
    assert b.repo_dir == "deps/spring-mcp-1c-copilot"
    assert b.repo_url == \
        "https://github.com/SteelMorgan/spring-mcp-1c-copilot.git"
    assert b.repo_sha  # пин: сборка не должна уезжать за HEAD


def test_naparnic_host_network_on_linux(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    p = R.launch_params("1c-naparnic", port=8003, token="T")
    assert p["network"] == "host"


def test_naparnic_no_host_network_on_windows(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "win32")
    p = R.launch_params("1c-naparnic", port=8003, token="T")
    assert p["network"] is None


def test_platform_requires_platform_path():
    with pytest.raises(ValueError, match="платформ"):
        R.launch_params("1c-platform", port=8002)
    p = R.launch_params("1c-platform", port=8002, platform_path="/opt/1cv8/x")
    assert p["env"]["MCP_BSL_CONTEXT_PORT"] == "8002"
    assert p["env"]["ONEC_PLATFORM_PATH"] == "/opt/1cv8/x"
    assert any("/opt/1cv8/x:/opt/1cv8/x:ro" in v for v in p["volumes"])
    assert p["internal_port"] == 8002


def test_platform_windows_path_mounts_to_fixed_container_dir():
    # Windows-путь нельзя монтировать «сам в себя»: двоеточие диска в target
    # ломает разбор -v в Docker Desktop («too many colons»). Внутри — /opt/1cv8,
    # и ONEC_PLATFORM_PATH должен указывать уже на контейнерный путь.
    win = r"C:\Program Files (x86)\1cv8\8.3.27.2170\bin"
    p = R.launch_params("1c-platform", port=8002, platform_path=win)
    assert p["env"]["ONEC_PLATFORM_PATH"] == "/opt/1cv8"
    assert p["volumes"] == [
        "C:/Program Files (x86)/1cv8/8.3.27.2170/bin:/opt/1cv8:ro",
    ]


def test_platform_unc_path_uses_container_dir_too():
    unc = r"\\server\share\1cv8\8.3.27.2170\bin"
    p = R.launch_params("1c-platform", port=8002, platform_path=unc)
    assert p["env"]["ONEC_PLATFORM_PATH"] == "/opt/1cv8"
    assert p["volumes"] == [f"{unc}:/opt/1cv8:ro"]


def test_platform_build_knows_source_repo():
    b = R.recipe_for("1c-platform").build
    assert b.repo_dir == "deps/docker_1c_sandbox"
    assert b.repo_url == "https://github.com/AlekseyUAM/docker_1c_sandbox.git"


def test_bsl_ls_build_has_no_source_repo():
    b = R.recipe_for("bsl-ls").build
    assert b.repo_dir is None
    assert b.repo_url is None
