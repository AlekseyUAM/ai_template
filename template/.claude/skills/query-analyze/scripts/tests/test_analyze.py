import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_query import split_extracted

SCRIPT = Path(__file__).resolve().parents[1] / "analyze_query.py"
HAVE_NODE = shutil.which("node") is not None


def test_split_extracted_blocks():
    text = ("# a.bsl:10\nВЫБРАТЬ 1\n--- 8< ---\n"
            "# b.bsl:20\nВЫБРАТЬ 2")
    assert split_extracted(text) == [
        ("a.bsl:10", "ВЫБРАТЬ 1"),
        ("b.bsl:20", "ВЫБРАТЬ 2"),
    ]


def test_split_plain_query_kept_whole():
    assert split_extracted("ВЫБРАТЬ 1") == [(None, "ВЫБРАТЬ 1")]


def test_split_empty_input():
    assert split_extracted("") == []


@pytest.mark.skipif(not HAVE_NODE, reason="нужен node для разбора через бандл")
def test_extracted_blocks_are_analyzed_separately():
    text = ("# f.bsl:1\nВЫБРАТЬ 1\n--- 8< ---\n"
            "# f.bsl:5\nВЫБРАТЬ 2\n")
    proc = subprocess.run([sys.executable, str(SCRIPT), "-"],
                          input=text, text=True, encoding="utf-8",
                          capture_output=True)
    output = proc.stdout + proc.stderr
    assert "query-not-parseable" not in output
    assert "# f.bsl:1" in output
    assert "# f.bsl:5" in output
