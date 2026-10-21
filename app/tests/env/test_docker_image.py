"""Тесты модуля сборки docker-образа агента (docker_image.py).

Реальный Docker не вызывается: subprocess.run подменяется фейком.
"""
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
