import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import cli, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_prefix():
    """cli.run выставляет процесс-глобальный tools._prefix — не протекаем."""
    saved = tools._prefix
    yield
    tools._prefix = saved


def _subst(obj, root):
    if isinstance(obj, str):
        return obj.replace("{ROOT}", str(root))
    if isinstance(obj, dict):
        return {k: _subst(v, root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst(v, root) for v in obj]
    return obj


def _verdict(root, case):
    payload = {"tool_name": case["tool"], "tool_input": case.get("input", {}),
               "cwd": str(root)}
    if "cmd" in case:
        payload["tool_input"] = {"command": case["cmd"]}
    d = cli.run(payload, make_ctx(root))
    if d is None:
        return "пропуск"
    return "РАЗРЕШЕНО" if d.allow else "ОТКАЗ"


CASES = [
    {"n": "grep по индексированному файлу", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "grep -n main src/main.rs"},
    {"n": "grep -rn по каталогу", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "grep -rn main src/"},
    {"n": "grep без пути из корня репо", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "grep -rn main"},
    {"n": "find по проекту", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "find src -name '*.rs'"},
    {"n": "ls каталога", "want": "ОТКАЗ", "tool": "Bash", "cmd": "ls src/"},
    {"n": "Grep-инструмент", "want": "ОТКАЗ", "tool": "Grep",
     "input": {"pattern": "main", "glob": "**/*.rs"}},
    {"n": "Glob-инструмент", "want": "ОТКАЗ", "tool": "Glob",
     "input": {"pattern": "src/**/*.rs"}},
    {"n": "Read целиком", "want": "ОТКАЗ", "tool": "Read",
     "input": {"file_path": "{ROOT}/Cargo.toml"}},
    {"n": "ритуальный Read(1,1)", "want": "РАЗРЕШЕНО", "tool": "Read",
     "input": {"file_path": "{ROOT}/Cargo.toml", "offset": 1, "limit": 1}},
    {"n": "cat индексированного", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "cat src/main.rs"},
    {"n": "head индексированного", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "head -5 Cargo.toml"},
    {"n": "Get-Content индексированного", "want": "ОТКАЗ", "tool": "PowerShell",
     "cmd": "Get-Content src/main.rs"},
    {"n": "Select-String", "want": "ОТКАЗ", "tool": "PowerShell",
     "cmd": "Select-String -Path src/main.rs -Pattern main"},
    # Bash-парсер не знает Get-Content: None → cli.run повторяет разбор как
    # PowerShell (фолбэк для Windows-харнесса). Пропажа фолбэка = «пропуск».
    {"n": "Get-Content под tool=Bash (фолбэк)", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "Get-Content src/main.rs"},
    {"n": "Select-String под tool=Bash (фолбэк)", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "Select-String -Path src/main.rs -Pattern main"},
    {"n": "grep ПОСЛЕ трубы", "want": "пропуск", "tool": "Bash",
     "cmd": "pytest -q 2>&1 | grep -E passed"},
    {"n": "git grep", "want": "пропуск", "tool": "Bash",
     "cmd": "git grep -n main -- src/"},
    {"n": "grep по неиндексированному файлу", "want": "пропуск", "tool": "Bash",
     "cmd": "grep -c name Cargo.lock"},
    {"n": "grep по target/", "want": "пропуск", "tool": "Bash",
     "cmd": "grep -rn x target/release"},
    {"n": "tail неиндексированного", "want": "пропуск", "tool": "Bash",
     "cmd": "tail -3 Cargo.lock"},
    {"n": "ls существующего файла", "want": "пропуск", "tool": "Bash",
     "cmd": "ls -la {ROOT}/Cargo.toml"},
    {"n": "grep по дотфайлу", "want": "пропуск", "tool": "Grep",
     "input": {"pattern": "target", "glob": ".gitignore"}},
    {"n": "Glob по бинарному расширению", "want": "пропуск", "tool": "Glob",
     "input": {"pattern": "**/*.epf"}},
    {"n": "heredoc с текстом команд", "want": "пропуск", "tool": "Bash",
     "cmd": "git commit -F - <<'MSG'\nls src/\nMSG\n"},
    {"n": "cd repo && grep", "want": "ОТКАЗ", "tool": "Bash",
     "cmd": "cd {ROOT} && grep -rn main src/"},
    {"n": "каталог вне индекса", "want": "пропуск", "tool": "Bash",
     "cmd": "grep -n x /tmp/none"},
]


@pytest.mark.parametrize("case", CASES, ids=[c["n"] for c in CASES])
def test_probe(tmp_path, case):
    root = build_repo(tmp_path)
    case = _subst(case, root)
    assert _verdict(root, case) == case["want"]
