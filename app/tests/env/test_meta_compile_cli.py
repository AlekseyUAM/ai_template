"""meta-compile.py: подсказка Read перед первым Write в созданный модуль."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[3] / "template" / ".claude"
          / "skills" / "meta-compile" / "scripts" / "meta-compile.py")


def test_meta_compile_prints_read_before_write_hint(tmp_path):
    obj_json = tmp_path / "obj.json"
    obj_json.write_text(json.dumps({"type": "CommonModule",
                                    "name": "ТестовыйМодуль"},
                                   ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "src" / "cf"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "-JsonPath", str(obj_json),
         "-OutputDir", str(out_dir)],
        capture_output=True, text=True, encoding="utf-8")

    assert proc.returncode == 0, proc.stderr
    assert "Module:" in proc.stdout
    assert "Модули созданы пустыми" in proc.stdout
    assert "Read" in proc.stdout and "Write" in proc.stdout

    module = (out_dir / "CommonModules" / "ТестовыйМодуль" / "Ext"
              / "Module.bsl")
    assert module.is_file()
    assert module.read_text(encoding="utf-8-sig").strip() == ""
