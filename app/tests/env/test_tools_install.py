import pytest
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.env import tools_install


def cfg(tmp_path):
    return EnvConfig(schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786", db_kind="file",
        db_connection="/b", web_publication="", mcp=[], agents=[])


class FakeRun:
    def __init__(self, rc=0, err=""):
        self.calls = []; self._rc = rc; self._err = err
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        class R: pass
        R.returncode = self._rc; R.stderr = self._err
        return R


def test_installs_cli_and_deps(tmp_path):
    fake = FakeRun()
    tools_install.install_tools(cfg(tmp_path), run=fake)
    assert len(fake.calls) == 2
    assert any("1c-batch" in str(c) for c in fake.calls)
    assert any("lxml" in c for c in fake.calls)


def test_raises_on_pip_failure(tmp_path):
    with pytest.raises(RuntimeError):
        tools_install.install_tools(cfg(tmp_path), run=FakeRun(rc=1, err="pip fail"))
