import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import config, paths  # noqa: E402


def _write(tmp_path, text):
    p = tmp_path / "code-index-guard.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_parses_mcp_prefix_and_local(tmp_path, monkeypatch):
    p = _write(tmp_path, '''
# комментарий
mcp_prefix = "mcp__ci__"

[[local]]
path = "C:\\\\proj\\\\src\\\\cf"
alias = "proj"
''')
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(p))
    cfg = config.load_guard_config()
    assert cfg.mcp_prefix == "mcp__ci__"
    assert cfg.local == [("C:\\proj\\src\\cf", "proj")]


def test_default_alias_is_last_segment(tmp_path, monkeypatch):
    p = _write(tmp_path, '[[local]]\npath = "C:/Projects/My App"\n')
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(p))
    cfg = config.load_guard_config()
    assert cfg.local == [("C:/Projects/My App", "my_app")]


def test_missing_config_is_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(tmp_path / "nope.toml"))
    cfg = config.load_guard_config()
    assert cfg.local == []
    assert cfg.mcp_prefix == config.DEFAULT_MCP_PREFIX
    assert config.indexed_paths(cfg) == []


def test_daemon_toml_priority_and_dedup(tmp_path, monkeypatch):
    daemon = tmp_path / "daemon.toml"
    daemon.write_text('[[paths]]\npath = "C:/r"\nalias = "from-daemon"\n',
                      encoding="utf-8")
    p = _write(tmp_path, f'''
daemon_toml = "{daemon.as_posix()}"
[[local]]
path = "C:/r"
alias = "from-local"
[[local]]
path = "C:/other"
alias = "other"
''')
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(p))
    cfg = config.load_guard_config()
    got = config.indexed_paths(cfg, case_insensitive=False)
    assert got == [("C:/r", "from-daemon"), ("C:/other", "other")]


def test_env_daemon_toml_overrides_config(tmp_path, monkeypatch):
    daemon = tmp_path / "env-daemon.toml"
    daemon.write_text('[[paths]]\npath = "C:/env"\nalias = "env"\n',
                      encoding="utf-8")
    p = _write(tmp_path, '[[local]]\npath = "C:/local"\nalias = "local"\n')
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(p))
    monkeypatch.setenv("CODE_INDEX_DAEMON_TOML", str(daemon))
    got = config.indexed_paths(config.load_guard_config(), case_insensitive=False)
    assert got == [("C:/env", "env"), ("C:/local", "local")]


def test_norm_prefix_slashes_and_case():
    assert paths.norm_prefix("C:\\Repo\\", case_insensitive=False) == "C:/Repo"
    assert paths.norm_prefix("C:\\Repo\\", case_insensitive=True) == "c:/repo"


def test_bad_toml_does_not_crash(tmp_path, monkeypatch):
    p = _write(tmp_path, "mcp_prefix = \n[[local]]\npath =\n")
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(p))
    cfg = config.load_guard_config()
    assert cfg.mcp_prefix == config.DEFAULT_MCP_PREFIX
    assert cfg.local == []
