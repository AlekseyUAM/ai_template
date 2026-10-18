import json
from pathlib import Path

from agentmon.backends.local import LocalProvisioner
from agentmon.env.scaffold import (scaffold_layout, write_json,
                                    write_preserving)


def test_scaffold_layout_creates_all_dirs(tmp_path):
    prov = LocalProvisioner()
    scaffold_layout(prov, str(tmp_path))
    for rel in [".claude/agents", ".claude/skills", ".claude/hooks",
                "src/cf", "src/cfe", "tasks"]:
        assert (tmp_path / rel).is_dir()


def test_write_json_pretty_utf8(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "d.json"
    write_json(prov, str(p), {"ключ": "значение"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"ключ": "значение"}
    assert "значение" in p.read_text(encoding="utf-8")  # ensure_ascii=False


def test_write_preserving_backs_up_on_update(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "f.txt"
    write_preserving(prov, str(p), "старое", update=False)
    write_preserving(prov, str(p), "новое", update=True)
    assert p.read_text(encoding="utf-8") == "новое"
    assert (tmp_path / "f.txt.bak").read_text(encoding="utf-8") == "старое"
