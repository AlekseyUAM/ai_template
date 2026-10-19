import pytest
from unittest.mock import patch
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.backends import RunResult
from agentmon.env import tools_install


def cfg(tmp_path):
    return EnvConfig(schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786", db_kind="file",
        db_connection="/b", web_publication="", mcp=[], agents=[])


class FakeProv:
    """Подставной провайдер для тестов install_tools."""

    def __init__(self, results=None):
        self.calls: list[list[str]] = []
        self._results = results or []
        self._idx = 0

    def venv_python(self, project_dir: str) -> str:
        return f"{project_dir}/.venv/bin/python"

    def run(self, cmd, cwd=None, timeout=None) -> RunResult:
        self.calls.append(cmd)
        if self._idx < len(self._results):
            result = self._results[self._idx]
        else:
            result = RunResult(0)
        self._idx += 1
        return result


def test_installs_cli_and_deps(tmp_path):
    """Оба pip-вызова идут через prov.run с python из venv цели."""
    prov = FakeProv()
    tools_install.install_tools(cfg(tmp_path), prov=prov)

    assert len(prov.calls) == 2
    # Первый вызов: pip install scripts (содержит 1c-batch)
    assert prov.calls[0][0] == str(tmp_path / ".venv" / "bin" / "python")
    assert any("1c-batch" in arg for arg in prov.calls[0])
    # Второй вызов: pip install lxml Pillow psutil
    assert prov.calls[1][0] == str(tmp_path / ".venv" / "bin" / "python")
    assert "lxml" in prov.calls[1]


def test_uses_venv_python_not_sys_executable(tmp_path):
    """Интерпретатор берётся из venv цели, а не из sys.executable."""
    import sys
    prov = FakeProv()
    tools_install.install_tools(cfg(tmp_path), prov=prov)
    for cmd in prov.calls:
        assert cmd[0] != sys.executable, "install_tools не должен использовать sys.executable"


def test_scripts_path_uses_project_dir(tmp_path):
    """Путь к scripts формируется через project_dir без pathlib (POSIX-совместим)."""
    prov = FakeProv()
    tools_install.install_tools(cfg(tmp_path), prov=prov)
    expected_scripts = f"{tmp_path}/.claude/skills/1c-batch/scripts"
    assert expected_scripts in prov.calls[0]


def test_raises_on_first_pip_failure(tmp_path):
    """rc != 0 на первой команде → RuntimeError со stderr."""
    prov = FakeProv(results=[RunResult(1, stderr="pip fail first")])
    with pytest.raises(RuntimeError, match="pip fail first"):
        tools_install.install_tools(cfg(tmp_path), prov=prov)
    assert len(prov.calls) == 1  # вторая команда не выполняется


def test_raises_on_second_pip_failure(tmp_path):
    """rc != 0 на второй команде → RuntimeError со stderr."""
    prov = FakeProv(results=[RunResult(0), RunResult(1, stderr="pip fail second")])
    with pytest.raises(RuntimeError, match="pip fail second"):
        tools_install.install_tools(cfg(tmp_path), prov=prov)


def test_raises_with_fallback_message_when_no_stderr(tmp_path):
    """Пустой stderr → RuntimeError с дефолтным сообщением."""
    prov = FakeProv(results=[RunResult(1, stderr="")])
    with pytest.raises(RuntimeError, match="установка инструментов не удалась"):
        tools_install.install_tools(cfg(tmp_path), prov=prov)


def test_default_prov_uses_local_provisioner(tmp_path):
    """prov=None создаёт LocalProvisioner и строит команды через него."""
    from agentmon.backends.local import LocalProvisioner

    recorded: list[list[str]] = []

    def fake_run(self, cmd, cwd=None, timeout=None) -> RunResult:
        recorded.append(cmd)
        return RunResult(0)

    with patch.object(LocalProvisioner, "run", fake_run):
        tools_install.install_tools(cfg(tmp_path))

    assert len(recorded) == 2
    # Убедиться, что использует venv цели, а не произвольный python
    local_prov = LocalProvisioner()
    expected_py = local_prov.venv_python(str(tmp_path))
    assert recorded[0][0] == expected_py
