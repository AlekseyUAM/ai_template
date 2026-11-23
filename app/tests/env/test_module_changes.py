"""module_changes: empty changed modules must not trigger check-modules."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools"
sys.path.insert(0, str(TOOLS))

from module_changes import has_nonempty_changed_bsl  # noqa: E402

BOM = b"\xef\xbb\xbf"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    module = tmp_path / "src" / "cf" / "CommonModules" / "А" / "Ext" / "Module.bsl"
    module.parent.mkdir(parents=True)
    module.write_text("Процедура Тест() КонецПроцедуры", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return tmp_path


requires_git = pytest.mark.skipif(shutil.which("git") is None,
                                  reason="git is not installed")


@requires_git
def test_empty_new_module_is_not_counted(tmp_path):
    root = _repo(tmp_path)
    empty = root / "src" / "cf" / "CommonModules" / "Б" / "Ext" / "Module.bsl"
    empty.parent.mkdir(parents=True)
    empty.write_bytes(BOM + b"\n")
    assert has_nonempty_changed_bsl(root) is False


@requires_git
def test_nonempty_new_module_is_counted(tmp_path):
    root = _repo(tmp_path)
    module = root / "src" / "cf" / "CommonModules" / "Б" / "Ext" / "Module.bsl"
    module.parent.mkdir(parents=True)
    module.write_bytes(BOM + "Процедура Тест() КонецПроцедуры".encode("utf-8"))
    assert has_nonempty_changed_bsl(root) is True


@requires_git
def test_modified_nonempty_module_is_counted(tmp_path):
    root = _repo(tmp_path)
    module = root / "src" / "cf" / "CommonModules" / "А" / "Ext" / "Module.bsl"
    module.write_text("Процедура Тест() КонецПроцедуры\nПроцедура Ещё() КонецПроцедуры",
                      encoding="utf-8")
    assert has_nonempty_changed_bsl(root) is True


@requires_git
def test_extension_module_not_counted_for_main_config(tmp_path):
    """Непустой модуль расширения не требует main-config check-modules."""
    root = _repo(tmp_path)
    ext = (root / "src" / "cfe" / "ЮнитТесты" / "CommonModules" / "Тест"
           / "Ext" / "Module.bsl")
    ext.parent.mkdir(parents=True)
    ext.write_text("Процедура Тест() КонецПроцедуры", encoding="utf-8")
    assert has_nonempty_changed_bsl(root, "src/cf") is False
    assert has_nonempty_changed_bsl(root) is True


@requires_git
def test_clean_repo_is_false(tmp_path):
    root = _repo(tmp_path)
    assert has_nonempty_changed_bsl(root) is False


def test_not_a_repository_is_unknown(tmp_path):
    assert has_nonempty_changed_bsl(tmp_path) is None
