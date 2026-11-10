from types import SimpleNamespace

from agentmon.env import mcp_sources
from agentmon.env.mcp_docker_recipes import BuildSpec


SPEC = BuildSpec(
    dockerfile="deps/repo/docker/Dockerfile",
    context="deps/repo",
    repo_dir="deps/repo",
    repo_url="https://github.com/example/repo.git",
)


def test_clone_cmd_none_without_source(tmp_path):
    assert mcp_sources.clone_cmd(None, tmp_path) is None
    assert mcp_sources.clone_cmd(BuildSpec("d", "c"), tmp_path) is None


def test_clone_cmd_requires_both_fields(tmp_path):
    only_dir = BuildSpec("d", "c", repo_dir="deps/repo")
    only_url = BuildSpec("d", "c", repo_url="https://github.com/example/repo.git")
    assert mcp_sources.clone_cmd(only_dir, tmp_path) is None
    assert mcp_sources.clone_cmd(only_url, tmp_path) is None


def test_clone_cmd_none_if_dir_exists(tmp_path):
    (tmp_path / "deps" / "repo").mkdir(parents=True)
    assert mcp_sources.clone_cmd(SPEC, tmp_path) is None


def test_clone_cmd_builds_git_clone(tmp_path):
    cmd = mcp_sources.clone_cmd(SPEC, tmp_path)
    assert cmd == [
        "git", "clone", "--depth", "1",
        "https://github.com/example/repo.git",
        str(tmp_path / "deps" / "repo"),
    ]


def test_clone_skips_when_present(tmp_path):
    (tmp_path / "deps" / "repo").mkdir(parents=True)
    called = []

    def fake_run(cmd, **kw):
        called.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res == {"ok": True, "cloned": False, "log": ""}
    assert called == []


def test_clone_runs_git_and_reports_success(tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="Cloning into 'repo'...\n",
                               stderr="")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is True
    assert res["cloned"] is True
    assert seen["cmd"] == mcp_sources.clone_cmd(SPEC, tmp_path)
    assert "$ git clone --depth 1" in res["log"]
    assert "Cloning into" in res["log"]


def test_clone_reports_git_failure(tmp_path):
    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=128, stdout="",
                               stderr="fatal: repository not found\n")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is False
    assert res["cloned"] is True
    assert "fatal: repository not found" in res["log"]


def test_clone_catches_missing_git(tmp_path):
    def fake_run(cmd, **kw):
        raise FileNotFoundError("git not found")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is False
    assert "git not found" in res["log"]


PINNED = BuildSpec(
    dockerfile="deps/repo/docker/Dockerfile",
    context="deps/repo",
    repo_dir="deps/repo",
    repo_url="https://github.com/example/repo.git",
    repo_sha="a" * 40,
)


def test_clone_checks_out_pinned_sha(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            (tmp_path / "deps" / "repo").mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    res = mcp_sources.clone(PINNED, tmp_path, run=fake_run)
    assert res["ok"] is True
    checkout = calls[1]
    assert checkout[:2] == ["git", "-C"]
    assert checkout[-2:] == ["--detach", "a" * 40]


def test_clone_removes_dest_on_checkout_failure(tmp_path):
    def fake_run(cmd, **kw):
        if cmd[:2] == ["git", "clone"]:
            (tmp_path / "deps" / "repo").mkdir(parents=True, exist_ok=True)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="unknown revision")

    res = mcp_sources.clone(PINNED, tmp_path, run=fake_run)
    assert res["ok"] is False
    assert not (tmp_path / "deps" / "repo").exists()
