"""Тесты модуля сборки docker-образа агента (docker_image.py).

Реальный Docker не вызывается: subprocess.run подменяется фейком.
"""
import pytest

from agentmon.env import docker_image as di


class FakeRun:
    """Имитатор subprocess.run: один ответ на все вызовы, запоминает argv."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return self


# ── image_tag ────────────────────────────────────────────────────────────────

def test_image_tag_simple():
    assert di.image_tag("8.3.27.1786") == "ai1c-agent:8.3.27.1786"


def test_image_tag_sanitizes_spaces_and_case():
    assert di.image_tag("  8.3.27 X ") == "ai1c-agent:8.3.27x"


def test_image_tag_empty_falls_back_to_latest():
    assert di.image_tag("") == "ai1c-agent:latest"
    assert di.image_tag("   ") == "ai1c-agent:latest"


# ── image_exists ─────────────────────────────────────────────────────────────

def test_image_exists_true_when_id_printed():
    fake = FakeRun(returncode=0, stdout="deadbeef\n")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is True
    assert fake.calls[0] == ["docker", "images", "-q", "ai1c-agent:8.3.27"]


def test_image_exists_false_when_empty_output():
    fake = FakeRun(returncode=0, stdout="\n")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is False


def test_image_exists_false_when_rc_nonzero():
    fake = FakeRun(returncode=1, stdout="")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is False


def test_image_exists_inserts_docker_host():
    fake = FakeRun(returncode=0, stdout="id\n")
    di.image_exists("ai1c-agent:8.3.27", docker_host="ssh://u@h", run=fake)
    assert fake.calls[0] == [
        "docker", "-H", "ssh://u@h", "images", "-q", "ai1c-agent:8.3.27",
    ]


# ── build_agent_image ────────────────────────────────────────────────────────

class FakeProc:
    """Имитатор Popen: отдаёт заранее заданные строки stdout и код возврата."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode


class FakePopen:
    """Callable уровня subprocess.Popen: запоминает argv, возвращает FakeProc."""

    def __init__(self, lines, returncode=0):
        self._lines = lines
        self._returncode = returncode
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return FakeProc(self._lines, self._returncode)


def _make_distr(tmp_path):
    p = tmp_path / "server64_8_3_27.zip"
    p.write_bytes(b"PK\x03\x04 fake zip")
    return str(p)


def test_build_rejects_missing_distr(tmp_path):
    gen = di.build_agent_image(str(tmp_path / "нет.zip"), "8.3.27",
                               popen=FakePopen([]))
    with pytest.raises(ValueError):
        list(gen)


def test_build_rejects_non_zip(tmp_path):
    bad = tmp_path / "distr.tar"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        list(di.build_agent_image(str(bad), "8.3.27", popen=FakePopen([])))


def test_build_streams_lines_and_builds_tag(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["Step 1/5\n", "Successfully built\n"], returncode=0)
    lines = list(di.build_agent_image(distr, "8.3.27", popen=fake))
    assert lines == ["Step 1/5\n", "Successfully built\n"]
    argv = fake.calls[0]
    assert argv[0] == "docker"
    assert "build" in argv
    assert "--progress=plain" in argv   # лог построчно, без ANSI-перерисовки
    assert "-t" in argv and "ai1c-agent:8.3.27" in argv
    assert "-f" in argv and str(di.DOCKERFILE_PATH) in argv


def test_build_inserts_docker_host(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["ok\n"], returncode=0)
    list(di.build_agent_image(distr, "8.3.27", docker_host="ssh://u@h", popen=fake))
    argv = fake.calls[0]
    assert argv[:3] == ["docker", "-H", "ssh://u@h"]


def test_build_raises_on_nonzero_rc(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["boom\n"], returncode=1)
    with pytest.raises(RuntimeError):
        list(di.build_agent_image(distr, "8.3.27", popen=fake))


# ── ретраи на транзиентных сетевых ошибках ───────────────────────────────────

class FakePopenSeq:
    """Popen, отдающий разные (lines, rc) по очереди вызовов.

    Если результаты исчерпаны — повторяет последний (для «всегда падает»).
    """

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        lines, rc = self._results[min(len(self.calls) - 1, len(self._results) - 1)]
        return FakeProc(lines, rc)


def test_build_retries_on_transient_then_succeeds(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopenSeq([
        (["#2 load metadata\n", "dial tcp: i/o timeout\n"], 1),  # транзиентно
        (["Successfully built\n"], 0),                           # успех
    ])
    slept = []
    lines = list(di.build_agent_image(distr, "8.3.27", popen=fake,
                                      sleep=lambda d: slept.append(d)))
    assert len(fake.calls) == 2                       # была повторная сборка
    assert any("повтор" in ln for ln in lines)
    assert slept == [5]                               # один бэкофф (5*1)


def test_build_retries_exhausted_raises(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopenSeq([(["EOF\n"], 1)])             # всегда транзиентный провал
    with pytest.raises(RuntimeError):
        list(di.build_agent_image(distr, "8.3.27", popen=fake, retries=3,
                                  sleep=lambda d: None))
    assert len(fake.calls) == 3                       # ровно retries попыток


def test_build_no_retry_on_nontransient(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopenSeq([(["syntax error in Dockerfile\n"], 1)])
    with pytest.raises(RuntimeError):
        list(di.build_agent_image(distr, "8.3.27", popen=fake, retries=5,
                                  sleep=lambda d: None))
    assert len(fake.calls) == 1                       # без повторов
