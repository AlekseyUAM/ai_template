"""Regression tests for argv assembly in the CLI.

They cover specific bugs found during a manual run:
- `-Extension` must not be duplicated in one 1C call (1C fails with
  «Ошибка в параметрах командной строки» when there are two `-Extension`)
- The argv of `dump-epf`/`build-epf` must not raise NameError because of `_quote`
- Literal quotes in argv are forbidden (CLAUDE.md)
"""

import pytest
from click.testing import CliRunner

from onec_batch import cli as cli_module
from onec_batch.config import Config


@pytest.fixture
def captured_args(monkeypatch):
    """Patch run_batch - return captured extra_args instead of launching 1C."""
    captured: dict[str, list[str]] = {}

    def fake_run_batch(cfg, command_name, args):
        captured["command"] = command_name
        captured["args"] = args
        return 0

    def fake_load_config():
        return Config(
            platform_path=__file__,
            connection_type="server",
            server="host:1541",
            base="ref",
            user="Админ",
        )

    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_load_config", fake_load_config)
    return captured


def _invoke(args: list[str]):
    result = CliRunner().invoke(cli_module.cli, args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result


def test_load_extension_no_duplicate_extension_flag(captured_args):
    """Regression: -Extension must appear exactly once.

    In the failing variant it was `... -Extension X ... /UpdateDBCfg -Extension X` -
    1C failed with «Ошибка в параметрах командной строки».
    """
    _invoke(["load-extension", "src/cfe/foo", "--name", "foo"])
    assert captured_args["args"].count("-Extension") == 1
    assert "/UpdateDBCfg" in captured_args["args"]


def test_load_extension_skip_db_update_no_update_flag(captured_args):
    _invoke(["load-extension", "src/cfe/foo", "--name", "foo", "--skip-db-update"])
    assert "/UpdateDBCfg" not in captured_args["args"]
    assert captured_args["args"].count("-Extension") == 1


def test_load_config_with_extension_no_duplicate_flag(captured_args):
    """Regression: the same bug was also in load-config with --extension."""
    _invoke(["load-config", "src/cf", "--extension", "foo"])
    assert captured_args["args"].count("-Extension") == 1
    assert "/UpdateDBCfg" in captured_args["args"]


def test_load_config_without_extension(captured_args):
    _invoke(["load-config", "src/cf"])
    assert "-Extension" not in captured_args["args"]


def test_dump_epf_no_literal_quotes(captured_args):
    """Regression: _quote() used to be called - NameError on any run.

    Also checks the CLAUDE.md invariant: argv must not contain values
    wrapped in literal quotes.
    """
    _invoke(["dump-epf", "src/epf/Foo.xml", "build/Foo.epf"])
    args = captured_args["args"]
    assert "build/Foo.epf" in args  # value is present as is
    assert '"build/Foo.epf"' not in args  # no literal quotes
    for a in args:
        assert not (a.startswith('"') and a.endswith('"')), f"Литеральные кавычки в argv: {a!r}"


def test_build_epf_no_literal_quotes(captured_args):
    _invoke(["build-epf", "src/epf/Foo.xml", "build/Foo.epf"])
    args = captured_args["args"]
    assert "build/Foo.epf" in args
    for a in args:
        assert not (a.startswith('"') and a.endswith('"')), f"Литеральные кавычки в argv: {a!r}"


def test_load_extension_argv_order(captured_args):
    """Canonical order from docs/analysis-bat-scripts.md:65."""
    _invoke(["load-extension", "src/cfe/foo", "--name", "foo"])
    args = captured_args["args"]
    assert args == [
        "/LoadConfigFromFiles", "src/cfe/foo",
        "-Extension", "foo",
        "-updateConfigDumpInfo",
        "/UpdateDBCfg",
    ]
