import sys
from pathlib import Path
from agentmon import run_wrapper


def test_run_writes_exit_code(tmp_path):
    ef = tmp_path / "e"
    rc = run_wrapper.run(str(ef), [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert rc == 3 and ef.read_text().strip() == "3"


def test_main_parses_separator(tmp_path):
    ef = tmp_path / "e"
    try:
        run_wrapper.main([str(ef), "--", sys.executable, "-c", "import sys; sys.exit(0)"])
    except SystemExit as e:
        assert e.code == 0
    assert ef.read_text().strip() == "0"
