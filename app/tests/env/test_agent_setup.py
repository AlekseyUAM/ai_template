import json
from pathlib import Path

import pytest

from agentmon.env import agent_setup
from agentmon.env.agent_setup import AgentSetupError
from env.fakes_code_index import FakeProvisioner


def _repo(tmp_path):
    d = tmp_path / "deploy" / "claude"
    d.mkdir(parents=True)
    (d / "claude-ds.sh").write_text(
        "#!/usr/bin/env sh\r\necho ds\r\n", encoding="utf-8")
    (d / "claude-local.sh").write_text(
        "#!/usr/bin/env sh\necho local\n", encoding="utf-8")
    return tmp_path


def test_container_command_replaces_host_path():
    assert agent_setup.container_command(
        '"/opt/My Tools/claude" --flag') == "claude --flag"


def test_container_command_keeps_wrapper_and_args():
    assert agent_setup.container_command("claude-ds --x") == "claude-ds --x"


def test_container_command_unknown_unchanged():
    assert agent_setup.container_command("my-agent --x") == "my-agent --x"


def test_prepare_claude_is_noop():
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude --x",
                        repo_root=Path("/nowhere"))
    assert prov.writes == {} and prov.runs == []


def test_prepare_claude_ds_copies_wrapper_and_key(tmp_path):
    repo = _repo(tmp_path)
    key = tmp_path / "key"
    key.write_text("secret\n", encoding="utf-8")
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                        key_path=key, environ={})
    wrapper = prov.writes["/usr/local/bin/claude-ds"]
    assert "\r" not in wrapper
    assert prov.writes["/root/.config/deepseek/key"] == "secret\n"
    assert any(r["argv"] == ["chmod", "0755", "/usr/local/bin/claude-ds"]
               for r in prov.runs)
    assert any(r["argv"] == ["chmod", "0600", "/root/.config/deepseek/key"]
               for r in prov.runs)


def test_prepare_claude_ds_uses_env_token(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                        key_path=tmp_path / "missing",
                        environ={"DEEPSEEK_API_KEY": "tok"})
    assert prov.writes["/root/.config/deepseek/key"] == "tok\n"


def test_prepare_claude_ds_without_key_raises(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    with pytest.raises(AgentSetupError, match="ключ DeepSeek"):
        agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                            key_path=tmp_path / "missing", environ={})


def test_prepare_claude_local_writes_strata_settings(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    seen = {}

    def fetch(cmd):
        seen["cmd"] = cmd
        return {"ANTHROPIC_MODEL": "m"}

    agent_setup.prepare(
        prov, "/workspace", "claude-local", repo_root=repo,
        fetch_strata=fetch, build_settings=lambda env: {"env": env})
    assert seen["cmd"] == "strata"
    text = prov.writes["/workspace/.claude/settings.local.json"]
    assert json.loads(text) == {"env": {"ANTHROPIC_MODEL": "m"}}
    assert "/usr/local/bin/claude-local" in prov.writes


def test_prepare_unknown_command_raises():
    prov = FakeProvisioner()
    with pytest.raises(AgentSetupError, match="поддерживаются"):
        agent_setup.prepare(prov, "/workspace", "other",
                            repo_root=Path("/nowhere"))
