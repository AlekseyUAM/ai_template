"""Unit tests for argv assembly for 1cv8.

Key invariant: values in the argv list are passed WITHOUT literal quotes.
The OS does the quoting (execvp on POSIX, list2cmdline on Windows). Literal `"`
in argv would break passing the value to 1C.
"""

from onec_batch.config import Config
from onec_batch.runner import build_auth_args, build_base_command, build_connection_args


def test_connection_args_server_uses_slash_separator():
    cfg = Config(connection_type="server", server="localhost:1541", base="demo_base")
    assert build_connection_args(cfg) == ["/S", "localhost:1541/demo_base"]


def test_connection_args_file():
    cfg = Config(connection_type="file", connection_path="/tmp/MyBase")
    assert build_connection_args(cfg) == ["/F", "/tmp/MyBase"]


def test_connection_args_no_literal_quotes():
    """Regression: the value must not start/end with `"`."""
    cfg = Config(connection_type="server", server="srv", base="ref")
    _, value = build_connection_args(cfg)
    assert not value.startswith('"')
    assert not value.endswith('"')


def test_auth_args_user_only():
    cfg = Config(user="Администратор")
    assert build_auth_args(cfg) == ["/N", "Администратор"]


def test_auth_args_user_and_password():
    cfg = Config(user="Администратор", password="секрет")
    assert build_auth_args(cfg) == ["/N", "Администратор", "/P", "секрет"]


def test_auth_args_empty():
    assert build_auth_args(Config()) == []


def test_auth_args_value_with_spaces_passed_raw():
    """Spaces in the value must not be escaped manually - the OS does that."""
    cfg = Config(user="Иван Иванов")
    assert build_auth_args(cfg) == ["/N", "Иван Иванов"]


def test_base_command_layout():
    cfg = Config(
        platform_path="/opt/1cv8/8.3.27.1786/1cv8",
        connection_type="server",
        server="host:1541",
        base="erp",
        user="Админ",
    )
    cmd = build_base_command(cfg, "ENTERPRISE")
    assert cmd == [
        "/opt/1cv8/8.3.27.1786/1cv8",
        "ENTERPRISE",
        "/S",
        "host:1541/erp",
        "/N",
        "Админ",
    ]
