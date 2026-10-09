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
    for key in ("bsl-ls", "1c-platform", "1c-naparnic", "code-index"):
        assert R.recipe_for(key) is not None


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


def test_naparnic_params_inject_token_prebuilt_only():
    p = R.launch_params("1c-naparnic", port=8003, token="SECRET")
    assert p["env"]["SSE_PORT"] == "8003"
    assert p["env"]["ONEC_AI_TOKEN"] == "SECRET"
    # напарник — только готовый образ (нет Dockerfile в репо)
    assert R.recipe_for("1c-naparnic").build is None


def test_code_index_requires_catalog_dir(tmp_path):
    with pytest.raises(ValueError, match="катал"):
        R.launch_params("code-index", port=8004)
    state = tmp_path / "state"
    catalog = tmp_path / "cfg"
    catalog.mkdir()
    p = R.launch_params("code-index", port=8004,
                        catalog_dir=str(catalog), state_dir=str(state))
    assert p["env"]["MCP_HTTP_PORT"] == "8004"
    assert p["env"]["CODE_INDEX_HOME"] == "/data/code-index-home"
    # каталог кодовой базы и home-том смонтированы
    joined = " ".join(p["volumes"])
    assert f"{catalog}:/repos/src" in joined
    assert "/data/code-index-home" in joined
    # сгенерирован daemon.toml с путём внутри контейнера
    daemon = state / "daemon.toml"
    assert daemon.exists()
    assert "/repos/src" in daemon.read_text(encoding="utf-8")


def test_naparnic_host_network_on_linux(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    p = R.launch_params("1c-naparnic", port=8003, token="T")
    assert p["network"] == "host"


def test_naparnic_no_host_network_on_windows(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "win32")
    p = R.launch_params("1c-naparnic", port=8003, token="T")
    assert p["network"] is None


def test_code_index_no_host_network(tmp_path, monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    catalog = tmp_path / "c"; catalog.mkdir()
    p = R.launch_params("code-index", port=8004,
                        catalog_dir=str(catalog), state_dir=str(tmp_path / "s"))
    assert p["network"] is None


def test_platform_requires_platform_path():
    with pytest.raises(ValueError, match="платформ"):
        R.launch_params("1c-platform", port=8002)
    p = R.launch_params("1c-platform", port=8002, platform_path="/opt/1cv8/x")
    assert p["env"]["MCP_BSL_CONTEXT_PORT"] == "8002"
    assert p["env"]["ONEC_PLATFORM_PATH"] == "/opt/1cv8/x"
    assert any("/opt/1cv8/x:/opt/1cv8/x:ro" in v for v in p["volumes"])
    assert p["internal_port"] == 8002
