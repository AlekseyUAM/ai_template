from agentmon.env import mcp_docker


class FakeRun:
    def __init__(self, rc=0, out="", err=""):
        self.calls = []; self._rc, self._out, self._err = rc, out, err
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        class R: pass
        R.returncode=self._rc; R.stdout=self._out; R.stderr=self._err
        return R


def test_launch_builds_command():
    fake = FakeRun(out="abc123\n")
    res = mcp_docker.launch("code-index", "img:latest", 8815, run=fake)
    assert res["ok"] and "abc123" in res["log"]
    cmd = fake.calls[0]
    assert "run" in cmd and "127.0.0.1:8815:8815" in cmd and "img:latest" in cmd


def test_launch_with_token():
    fake = FakeRun()
    mcp_docker.launch("1c-naparnic", "img", 8814, token_env="NAPARNIC_TOKEN",
                      token="secret", run=fake)
    joined = " ".join(fake.calls[0])
    assert "-e" in fake.calls[0] and "NAPARNIC_TOKEN=secret" in joined


def test_launch_failure_reports_log():
    fake = FakeRun(rc=1, err="нет образа")
    res = mcp_docker.launch("x", "img", 8811, run=fake)
    assert res["ok"] is False and "нет образа" in res["log"]


def test_stop_command():
    fake = FakeRun()
    mcp_docker.stop("x", run=fake)
    assert fake.calls[0][:3] == ["docker", "rm", "-f"]


def test_launch_maps_host_to_internal_port():
    fake = FakeRun(out="cid")
    mcp_docker.launch("srv", "img", 9100, internal_port=8080, run=fake)
    assert "127.0.0.1:9100:8080" in fake.calls[0]


def test_launch_env_and_volumes():
    fake = FakeRun()
    mcp_docker.launch("srv", "img", 9100, internal_port=9100,
                      env={"FOO": "bar"}, volumes=["/host:/cont:ro"], run=fake)
    joined = " ".join(fake.calls[0])
    assert "-e" in fake.calls[0] and "FOO=bar" in joined
    assert "-v" in fake.calls[0] and "/host:/cont:ro" in joined


def test_launch_cmd_host_network_drops_port():
    cmd = mcp_docker.launch_cmd("n", "img", 8003, internal_port=8003,
                                network="host")
    assert "--network=host" in cmd
    assert "-p" not in cmd  # при host-сети публикация портов не нужна


def test_launch_cmd_bridge_keeps_port():
    cmd = mcp_docker.launch_cmd("n", "img", 8003, internal_port=8003)
    assert "-p" in cmd and not any(a.startswith("--network") for a in cmd)


def test_image_exists_true_when_id_returned():
    assert mcp_docker.image_exists("img:tag", run=FakeRun(out="abc\n")) is True


def test_image_exists_false_when_empty():
    assert mcp_docker.image_exists("img:tag", run=FakeRun(out="")) is False


def test_launch_cmd_builder():
    cmd = mcp_docker.launch_cmd("n", "img", 9100, internal_port=8080,
                                env={"A": "b"}, volumes=["/x:/y"])
    joined = " ".join(cmd)
    assert "127.0.0.1:9100:8080" in cmd
    assert "A=b" in joined and "/x:/y" in cmd and cmd[-1] == "img"


def test_launch_cmd_has_restart_policy():
    # все контейнеры поднимаются с restart=unless-stopped
    cmd = mcp_docker.launch_cmd("n", "img", 8003, internal_port=8003)
    assert "--restart" in cmd
    i = cmd.index("--restart")
    assert cmd[i + 1] == "unless-stopped"


def test_launch_applies_restart_policy():
    fake = FakeRun(out="cid")
    mcp_docker.launch("srv", "img", 9100, run=fake)
    joined = " ".join(fake.calls[0])
    assert "--restart unless-stopped" in joined


def test_build_cmd_builder():
    cmd = mcp_docker.build_cmd("t:local", "df", "ctx", build_args={"K": "V"})
    assert cmd[:2] == ["docker", "build"]
    assert "t:local" in cmd and cmd[-1] == "ctx" and "K=V" in " ".join(cmd)


def test_build_cmd_network_host_on_linux(monkeypatch):
    monkeypatch.setattr(mcp_docker.sys, "platform", "linux")
    cmd = mcp_docker.build_cmd("t", "df", "ctx")
    assert "--network=host" in cmd


def test_build_cmd_no_host_network_on_windows(monkeypatch):
    monkeypatch.setattr(mcp_docker.sys, "platform", "win32")
    cmd = mcp_docker.build_cmd("t", "df", "ctx")
    assert not any(a.startswith("--network") for a in cmd)


def test_iter_output_streams_lines_then_rc():
    class FakeProc:
        def __init__(self):
            self.stdout = iter(["line1\n", "line2\n"])
            self.returncode = 0
        def wait(self):
            pass
    out = list(mcp_docker.iter_output(["x"], popen=lambda cmd, **k: FakeProc()))
    assert out[0] == "line1" and out[1] == "line2"
    assert mcp_docker.is_rc(out[-1]) == 0


def test_iter_output_nonzero_rc():
    class FakeProc:
        def __init__(self):
            self.stdout = iter(["boom\n"])
            self.returncode = 2
        def wait(self):
            pass
    out = list(mcp_docker.iter_output(["x"], popen=lambda cmd, **k: FakeProc()))
    assert mcp_docker.is_rc(out[-1]) == 2


def test_build_command():
    fake = FakeRun(out="ok")
    res = mcp_docker.build("tag:local", "a/Dockerfile", "ctx",
                           build_args={"K": "V"}, run=fake)
    cmd = fake.calls[0]
    assert cmd[:2] == ["docker", "build"]
    assert "-t" in cmd and "tag:local" in cmd
    assert "-f" in cmd and "a/Dockerfile" in cmd
    assert "--build-arg" in cmd and "K=V" in cmd
    assert cmd[-1] == "ctx"
    assert res["ok"] is True
