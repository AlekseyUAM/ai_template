# Хук code-index-guard в template — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в template самодостаточный Python-хук (stdlib), который перенаправляет нативные `Read`/`Grep`/`Glob`/`Bash`/`PowerShell` по индексированным каталогам в инструменты code-index и не даёт дед-эндов на неотдаваемых файлах.

**Architecture:** Пакет `template/.claude/hooks/code_index_guard_lib/` — порт upstream `code-index-guard` v1.15.4 (Rust) по модулям: конфиг, пути, `index.db`, shell-разбор, решения Bash/PowerShell, Read/Grep/Glob, CLI. Конфиг с корнями генерирует `deploy_content` из карточек MCP (`catalog_dir` + `project_name`); тогда же в `settings.json` добавляется `PreToolUse`-блок.

**Tech Stack:** Python 3.10+ (только stdlib: `json`, `os`, `re`, `sqlite3`, `sys`, `pathlib`), pytest, приложение `agentmon`.

**Spec:** `docs/superpowers/specs/2026-11-12-code-index-guard-template-design.md`

## Global Constraints

- Только stdlib Python 3.10+; никаких pip-пакетов, бинарей и сетевых вызовов в хуке.
- Источник порта: `deps/code-index-mcp/crates/code-index-guard/src/main.rs` (v1.15.4, commit `fd3199f204183179aad2d39873a0341d5849ddae`). В docstring точки входа — MIT-атрибуция.
- Контракт: stdin JSON `{tool_name, tool_input, cwd}`; stdout — решение `deny`/`allow` либо ничего; **exit всегда 0**; любое исключение → пустой stdout.
- Префикс имён MCP по умолчанию `mcp__code_index__`; конфиг-ключ `mcp_prefix`, CLI `--mcp-prefix` переопределяет.
- Все тексты отказов — на русском, с точными именами инструментов code-index.
- Регистр путей: Windows/macOS — без учёта, Linux — с учётом. Имена команд и ключи — без учёта везде.
- При сомнении хук **воздерживается** (пустой stdout): false-negative безвреден, false-positive — дед-энд.
- Тесты запускаются из корня репозитория: `.venv/bin/python -m pytest app/tests/env/<файл> -q`.
- Коммиты — локально в `main`, без push.
- Тесты хука живут в `app/tests/env/` и импортируют template-файлы по пути (как `test_bsl_nudge.py`).

## File Structure

```
template/.claude/hooks/
  code_index_guard.py                    # точка входа, exec по пути
  code_index_guard_lib/
    __init__.py                          # пустой
    config.py                            # GuardConfig, parse TOML-подобного, indexed_paths
    context.py                           # GuardContext
    tools.py                             # set_prefix/tool
    paths.py                             # fold/normalize/match/glob
    index_db.py                         # serveability, freshness, exclusions
    shell.py                             # heredoc/here-string, split_chain, cd, vars
    redirect.py                          # общий redirect в code-index
    decisions.py                         # Read/Grep/Glob
    bash.py                              # Bash
    powershell.py                        # PowerShell
    cli.py                               # stdin/stdout, dispatch, main
  code-index-guard.toml.example          # образец конфига
app/tests/env/
  test_code_index_guard_config.py
  test_code_index_guard_paths.py
  test_code_index_guard_index_db.py
  test_code_index_guard_read_grep_glob.py
  test_code_index_guard_shell.py
  test_code_index_guard_bash.py
  test_code_index_guard_powershell.py
  test_code_index_guard_cli.py
  test_code_index_guard_probes.py
  guard_fixtures.py                       # общие фикстуры (репо + index.db)
app/src/agentmon/env/
  config_schema.py                        # + catalog_dir/project_name
  project_api.py                          # заполнение новых полей
  content.py                              # генерация конфига + инъекция хука
  mcp_catalog.py                          # (без изменений; используем mcp_name_overrides)
```

---

### Task 1: Каркас пакета, конфиг, точка входа

**Files:**
- Create: `template/.claude/hooks/code_index_guard.py`
- Create: `template/.claude/hooks/code_index_guard_lib/__init__.py`
- Create: `template/.claude/hooks/code_index_guard_lib/paths.py` (только `fold_path`, `default_case_insensitive`, `norm_prefix`)
- Create: `template/.claude/hooks/code_index_guard_lib/config.py`
- Create: `template/.claude/hooks/code_index_guard_lib/context.py`
- Create: `template/.claude/hooks/code_index_guard_lib/tools.py`
- Create: `template/.claude/hooks/code_index_guard_lib/cli.py` (минимальный: без решений)
- Create: `template/.claude/hooks/code-index-guard.toml.example`
- Test: `app/tests/env/test_code_index_guard_config.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `GuardConfig(daemon_toml, local, mcp_prefix)`, `load_guard_config()`, `indexed_paths(cfg, *, case_insensitive=None) -> list[tuple[str, str]]`, `GuardContext(config, paths, case_insensitive)`, `tools.set_prefix(str)`, `tools.tool(name) -> str`, `cli.main(argv=None)`, `paths.fold_path(s, case_insensitive=None)`, `paths.norm_prefix(p, case_insensitive=None)`.

- [ ] **Step 1: Написать падающие тесты конфига**

Создать `app/tests/env/test_code_index_guard_config.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_config.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'code_index_guard_lib'`.

- [ ] **Step 3: Создать каркас пакета и реализовать конфиг**

`template/.claude/hooks/code_index_guard.py`:

```python
#!/usr/bin/env python
"""PreToolUse-хук code-index-guard (Python-порт).

Источник: Regsorm/code-index-mcp, crates/code-index-guard, v1.15.4
(commit fd3199f204183179aad2d39873a0341d5849ddae), лицензия MIT.
Перенаправляет нативные Read/Grep/Glob/Bash/PowerShell по индексированным
каталогам в инструменты code-index. При сомнении воздерживается.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_index_guard_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
```

`template/.claude/hooks/code_index_guard_lib/__init__.py` — пустой файл.

`template/.claude/hooks/code_index_guard_lib/paths.py`:

```python
"""Нормализация и сравнение путей (порт code-index-guard)."""
import os
import sys


def default_case_insensitive() -> bool:
    """Windows и macOS сравнивают пути без учёта регистра, Linux — с учётом."""
    return os.name == "nt" or sys.platform == "darwin"


def fold_path(s: str, case_insensitive: bool | None = None) -> str:
    ci = default_case_insensitive() if case_insensitive is None else case_insensitive
    return s.lower() if ci else s


def norm_prefix(p: str, case_insensitive: bool | None = None) -> str:
    """Префикс репозитория: прямые слэши, без хвостового, регистр по правилу."""
    return fold_path(p.replace("\\", "/").rstrip("/"), case_insensitive)
```

`template/.claude/hooks/code_index_guard_lib/config.py` — полный порт
`main.rs:1230-1306` (`GuardConfig`, `guard_config_path`, `load_guard_config`,
`daemon_toml_path`, `indexed_paths`, `norm_prefix`), плюс парсеры
`main.rs:1556-1651` (`parse_path_blocks`, `kv`, `unescape_toml`,
`parse_top_level_string`). Адаптации:

```python
DEFAULT_MCP_PREFIX = "mcp__code_index__"


@dataclass
class GuardConfig:
    daemon_toml: str | None = None
    local: list[tuple[str, str]] = field(default_factory=list)
    mcp_prefix: str = DEFAULT_MCP_PREFIX


def guard_config_path() -> Path:
    env = os.environ.get("CODE_INDEX_GUARD_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "code-index-guard.toml"


def load_guard_config() -> GuardConfig:
    path = guard_config_path()
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    return GuardConfig(
        daemon_toml=parse_top_level_string(content, "daemon_toml"),
        local=parse_path_blocks(content, "[[local]]"),
        mcp_prefix=parse_top_level_string(content, "mcp_prefix") or DEFAULT_MCP_PREFIX,
    )


def daemon_toml_path(cfg: GuardConfig) -> str | None:
    return os.environ.get("CODE_INDEX_DAEMON_TOML") or cfg.daemon_toml


def indexed_paths(cfg: GuardConfig, *, case_insensitive: bool | None = None
                  ) -> list[tuple[str, str]]:
    v: list[tuple[str, str]] = []
    seen: set[str] = set()
    path = daemon_toml_path(cfg)
    if path:
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError:
            content = ""
        for p, a in parse_path_blocks(content, "[[paths]]"):
            norm = norm_prefix(p, case_insensitive)
            if norm and norm not in seen:
                seen.add(norm)
                v.append((norm, a))
    for p, a in cfg.local:
        norm = norm_prefix(p, case_insensitive)
        if norm and norm not in seen:
            seen.add(norm)
            v.append((norm, a))
    return v
```

`parse_path_blocks` переносит логику один-в-один: секции по `header`,
строки `path`/`alias`, alias по умолчанию — последний сегмент пути в нижнем
регистре с пробелами → `_`. `kv` возвращает значение basic-string с
разэкранированием `\\`, `\"`, `\/`. Комментарии игнорируются, потому что
строка должна начинаться с самого ключа.

`template/.claude/hooks/code_index_guard_lib/context.py`:

```python
"""Контекст одного запуска хука."""
from dataclasses import dataclass

from .config import GuardConfig


@dataclass(frozen=True)
class GuardContext:
    config: GuardConfig
    paths: list[tuple[str, str]]
    case_insensitive: bool
```

`template/.claude/hooks/code_index_guard_lib/tools.py`:

```python
"""Имена инструментов code-index так, как их видит модель."""
DEFAULT_PREFIX = "mcp__code_index__"
_prefix = DEFAULT_PREFIX


def set_prefix(prefix: str | None) -> None:
    global _prefix
    _prefix = prefix or DEFAULT_PREFIX


def tool(name: str) -> str:
    return f"{_prefix}{name}"
```

`template/.claude/hooks/code_index_guard_lib/cli.py` (пока без решений):

```python
"""CLI-контракт хука. Решения подключаются в Task 8."""
import json
import sys

from .config import indexed_paths, load_guard_config
from .context import GuardContext
from . import tools


def build_context() -> GuardContext:
    from .paths import default_case_insensitive
    ci = default_case_insensitive()
    cfg = load_guard_config()
    return GuardContext(cfg, indexed_paths(cfg, case_insensitive=ci), ci)


def parse_args(argv):
    list_roots = False
    prefix = None
    i = 0
    while i < len(argv):
        if argv[i] == "--list-roots":
            list_roots = True
        elif argv[i] == "--mcp-prefix" and i + 1 < len(argv):
            i += 1
            prefix = argv[i]
        i += 1
    return list_roots, prefix


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    list_roots, prefix = parse_args(args)
    try:
        ctx = build_context()
        tools.set_prefix(prefix or ctx.config.mcp_prefix)
        if list_roots:
            return  # режим v1 не реализован: пустой stdout
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        # dispatch появится в Task 8; сейчас хук ничего не решает
    except Exception:
        return
```

`template/.claude/hooks/code-index-guard.toml.example`:

```toml
# Конфиг хука code-index-guard (Python-порт).
# В развёрнутом проекте файл генерируется автоматически при создании/обновлении
# окружения; этот образец — для ручного развёртывания template.
#
# mcp_prefix — как называются инструменты сервера code-index в этой сессии.
# [[local]] — индексированные репозитории: path + alias (alias = repo= в вызовах).

mcp_prefix = "mcp__code_index__"

# [[local]]
# path = "C:/proj/src/cf"
# alias = "proj"

# Вместо [[local]] можно указать daemon.toml индексатора:
# daemon_toml = "C:/tools/code-index/daemon.toml"
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_config.py -q`

Expected: PASS (7 tests).

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/hooks/code_index_guard.py \
        template/.claude/hooks/code_index_guard_lib \
        template/.claude/hooks/code-index-guard.toml.example \
        app/tests/env/test_code_index_guard_config.py
git commit -m "feat(hooks): каркас code_index_guard и разбор конфига"
```

---

### Task 2: Нормализация и матчинг путей

**Files:**
- Modify: `template/.claude/hooks/code_index_guard_lib/paths.py`
- Test: `app/tests/env/test_code_index_guard_paths.py`

**Interfaces:**
- Consumes: `paths.fold_path`, `paths.norm_prefix`.
- Produces: `paths.strip_prefix_ci(s, prefix) -> str | None`, `paths.normalize_dir(path) -> str`, `paths.normalize_msys_drives(s) -> str`, `paths.match_indexed(raw, paths, *, case_insensitive=None) -> tuple[str, str, str] | None`, `paths.glob_match(pattern, text) -> bool`.

- [ ] **Step 1: Написать падающие тесты**

`app/tests/env/test_code_index_guard_paths.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import paths  # noqa: E402


def test_match_longest_prefix_wins():
    roots = [("c:/proj", "proj"), ("c:/proj/core", "core")]
    got = paths.match_indexed("C:/proj/core/src/a.bsl", roots,
                              case_insensitive=True)
    assert got == ("core", "src/a.bsl", "C:/proj/core")


def test_match_exact_root_has_empty_rel():
    got = paths.match_indexed("C:/proj", [("c:/proj", "p")],
                              case_insensitive=True)
    assert got == ("p", "", "C:/proj")


def test_match_requires_path_boundary():
    roots = [("c:/proj", "p")]
    assert paths.match_indexed("C:/projects/x", roots, case_insensitive=True) is None


def test_match_case_sensitive_on_linux():
    roots = [("c:/proj", "p")]
    assert paths.match_indexed("C:/Proj/x", roots, case_insensitive=False) is None
    assert paths.match_indexed("C:/Proj/x", roots, case_insensitive=True) is not None


def test_msys_drive_and_backslashes():
    roots = [("c:/proj", "p")]
    got = paths.match_indexed("/c/proj/src/a.bsl", roots, case_insensitive=True)
    assert got == ("p", "src/a.bsl", "c:/proj")
    got = paths.match_indexed("C:\\proj\\src\\a.bsl", roots, case_insensitive=True)
    assert got == ("p", "src/a.bsl", "C:/proj")


def test_normalize_dir_collapses_dotdot_without_escaping_root():
    assert paths.normalize_dir("C:/a/b/../c/./d/") == "C:/a/c/d"
    assert paths.normalize_dir("/a/../../b") == "/b"
    assert paths.normalize_dir("a/b/..") == "a"


def test_msys_conversion_only_at_boundary():
    assert paths.normalize_msys_drives("/c/tmp/x") == "c:/tmp/x"
    assert paths.normalize_msys_drives("x/c/tmp") == "x/c/tmp"


def test_glob_match_simple():
    assert paths.glob_match("*_run_*.json", "tests/abc_run_2026.json")
    assert paths.glob_match("*_run_*.json", "abc_run_x.json")
    assert not paths.glob_match("*_run_*.json", "abc.json")
    assert paths.glob_match("exact.txt", "exact.txt")
    assert not paths.glob_match("exact.txt", "exact.txt.bak")


def test_strip_prefix_ci():
    assert paths.strip_prefix_ci("-Path foo", "-path ") == "foo"
    assert paths.strip_prefix_ci("foo", "-path ") is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_paths.py -q`

Expected: FAIL — `AttributeError: module ... has no attribute 'match_indexed'`.

- [ ] **Step 3: Реализовать порт**

Перенести из `main.rs`:

- `strip_prefix_ci` — 104-108;
- `normalize_dir` — 729-755 (сегменты `..` не поднимаются выше корня `c:` или `/`);
- `normalize_msys_drives` — 1505-1527 (граница пути: начало или не-алфанумерик);
- `match_indexed` — 1530-1554 (длинные префиксы первыми, `rel` без ведущего
  `/`, `root` в исходном регистре; сравнение по `fold_path`);
- `glob_match` — 1471-1499 (только `*`).

Сигнатуры — как в блоке Interfaces; везде, где есть сравнение путей, параметр
`case_insensitive: bool | None = None` пробрасывается в `fold_path`.

- [ ] **Step 4: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_paths.py -q`

Expected: PASS (9 tests).

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/paths.py \
        app/tests/env/test_code_index_guard_paths.py
git commit -m "feat(hooks): нормализация и матчинг индексированных путей"
```

---

### Task 3: Проверка членства в index.db и исключения

**Files:**
- Create: `template/.claude/hooks/code_index_guard_lib/index_db.py`
- Create: `app/tests/env/guard_fixtures.py`
- Test: `app/tests/env/test_code_index_guard_index_db.py`

**Interfaces:**
- Consumes: `paths.fold_path`, `paths.glob_match`.
- Produces: `index_db.file_mtime_secs(path) -> int | None`, `index_db.serveability(db, rel, *, case_insensitive=None) -> tuple[bool, int | None] | None`, `index_db.read_is_blockable(root, rel, *, case_insensitive=None) -> bool`, `index_db.excluded_from_index(root, rel, *, case_insensitive=None) -> bool`; фикстуры `guard_fixtures.build_repo(tmp_path, *, v4=False, stale=False, oversize=False)` → `Path`, `guard_fixtures.make_ctx(root, *, alias="repo")` → `GuardContext`.

- [ ] **Step 1: Написать падающие тесты**

`app/tests/env/test_code_index_guard_index_db.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import index_db  # noqa: E402
from env.guard_fixtures import build_repo  # noqa: E402


def test_text_contents_v5_is_serveable(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.toml", case_insensitive=False) == (True, 1700000000)


def test_text_files_v4_is_serveable(tmp_path):
    root = build_repo(tmp_path, v4=True)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.toml", case_insensitive=False) == (True, 1700000000)


def test_oversize_is_not_serveable(tmp_path):
    root = build_repo(tmp_path, oversize=True)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "src/main.rs", case_insensitive=False) == (False, 1700000000)


def test_bare_row_is_not_serveable(tmp_path):
    # Строка в files без text_contents и file_contents — «голая»: MCP не отдаст,
    # но mtime у неё есть (upstream возвращает Some(mtime)).
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "Cargo.lock", case_insensitive=False) == (False, 1700000000)


def test_unknown_file_is_not_serveable(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.serveability(str(root / ".code-index" / "index.db"),
                                 "missing.txt", case_insensitive=False) == (False, None)


def test_read_is_blockable_requires_db(tmp_path):
    root = build_repo(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert index_db.read_is_blockable(str(empty), "Cargo.toml", case_insensitive=False) is False


def test_read_is_blockable_true_for_indexed_file(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.read_is_blockable(str(root), "Cargo.toml", case_insensitive=False) is True


def test_read_is_blockable_false_when_disk_is_newer(tmp_path):
    root = build_repo(tmp_path, stale=True)
    assert index_db.read_is_blockable(str(root), "Cargo.toml", case_insensitive=False) is False


def test_excluded_builtin_segments(tmp_path):
    root = build_repo(tmp_path)
    assert index_db.excluded_from_index(str(root), "target/release/x", case_insensitive=False)
    assert index_db.excluded_from_index(str(root), ".git/config", case_insensitive=False)
    assert not index_db.excluded_from_index(str(root), "src/main.rs", case_insensitive=False)


def test_excluded_project_config_and_unindexed_file(tmp_path):
    root = build_repo(tmp_path)
    cfg = root / ".code-index" / "config.json"
    cfg.write_text('{"exclude_dirs": ["out"], '
                   '"exclude_file_patterns": ["*_run_*.json"]}', encoding="utf-8")
    assert index_db.excluded_from_index(str(root), "out/x.bsl", case_insensitive=False)
    assert index_db.excluded_from_index(str(root), "tests/a_run_1.json", case_insensitive=False)
    # существующий, но отсутствующий в индексе файл — неиндексируемый
    assert index_db.excluded_from_index(str(root), "Cargo.lock", case_insensitive=False)
```

`app/tests/env/guard_fixtures.py`:

```python
"""Общие фикстуры для тестов code-index-guard: временное репо и index.db."""
import os
import sqlite3
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib.config import GuardConfig, indexed_paths  # noqa: E402
from code_index_guard_lib.context import GuardContext  # noqa: E402
from code_index_guard_lib.paths import default_case_insensitive  # noqa: E402

MTIME = 1700000000

_FILES = {
    "src/main.rs": ("code", "fn main() {}\n"),
    "Cargo.toml": ("text", "[package]\nname = \"demo\"\n"),
    "README.md": ("text", "# demo\n"),
    "Cargo.lock": ("plain", "version = 3\n"),
    ".gitignore": ("plain", "target/\n"),
    "target/release/demo": ("plain", "binary\n"),
}


def build_repo(tmp_path: Path, *, v4: bool = False, stale: bool = False,
               oversize: bool = False) -> Path:
    root = tmp_path / "repo"
    for rel, (_kind, text) in _FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        # mtime на диске должен совпадать с files.mtime индекса, иначе
        # read_is_blockable решит, что индекс отстал.
        os.utime(p, (MTIME, MTIME))
    db = root / ".code-index" / "index.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, mtime INTEGER)")
    if v4:
        conn.execute("CREATE TABLE text_files (file_id INTEGER)")
    else:
        conn.execute("CREATE TABLE text_contents (file_id INTEGER)")
    conn.execute("CREATE TABLE file_contents (file_id INTEGER, oversize INTEGER)")
    ids = {}
    for i, (rel, (kind, _text)) in enumerate(_FILES.items(), start=1):
        conn.execute("INSERT INTO files (id, path, mtime) VALUES (?, ?, ?)",
                     (i, rel, MTIME))
        ids[rel] = i
    if v4:
        conn.execute("INSERT INTO text_files (file_id) VALUES (?)", (ids["Cargo.toml"],))
        conn.execute("INSERT INTO text_files (file_id) VALUES (?)", (ids["README.md"],))
    else:
        conn.execute("INSERT INTO text_contents (file_id) VALUES (?)", (ids["Cargo.toml"],))
        conn.execute("INSERT INTO text_contents (file_id) VALUES (?)", (ids["README.md"],))
    conn.execute("INSERT INTO file_contents (file_id, oversize) VALUES (?, ?)",
                 (ids["src/main.rs"], 1 if oversize else 0))
    conn.commit()
    conn.close()
    if stale:
        p = root / "Cargo.toml"
        p.write_text("[package]\nname = \"changed\"\n", encoding="utf-8")
        os.utime(p, (MTIME + 100, MTIME + 100))
    return root


def make_ctx(root: Path, *, alias: str = "repo") -> GuardContext:
    ci = default_case_insensitive()
    cfg = GuardConfig(local=[(str(root), alias)], mcp_prefix="mcp__code_index__")
    return GuardContext(cfg, indexed_paths(cfg, case_insensitive=ci), ci)
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_index_db.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'code_index_guard_lib.index_db'`.

- [ ] **Step 3: Реализовать `index_db.py`**

Порт `main.rs:371-480` + `1412-1468`. Обязательные детали:

- `serveability`: `import sqlite3` внутри функции; `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`;
  наличие `text_contents` через `sqlite_master`; SQL с `COLLATE NOCASE` только
  при `case_insensitive`; результат `(serveable, mtime)`; SQL/OS-ошибка → `None`
  и предупреждение в `stderr` с префиксом `[code-index-guard]`.
- `read_is_blockable`: `db = Path(root) / ".code-index" / "index.db"`; нет файла
  → `False`; `serveability` → `None`/`False` → `False`; иначе `disk_mtime >
  idx_mtime` → `False`.
- `excluded_from_index`: сегменты пути; `NEVER_INDEXED = {".git",
  "node_modules", ".code-index", "target", "__pycache__", ".venv"}`; для
  конкретного существующего файла без `*`/`?` — `not read_is_blockable` →
  `True`; затем `.code-index/config.json`: `exclude_dirs` по сегменту и
  `exclude_file_patterns` через `glob_match` по каждому сегменту.

- [ ] **Step 4: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_index_db.py -q`

Expected: PASS (9 tests).

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/index_db.py \
        app/tests/env/guard_fixtures.py \
        app/tests/env/test_code_index_guard_index_db.py
git commit -m "feat(hooks): проверка членства в index.db и исключения"
```

---

### Task 4: Решения Read / Grep / Glob

**Files:**
- Create: `template/.claude/hooks/code_index_guard_lib/decisions.py`
- Modify: `template/.claude/hooks/code_index_guard_lib/cli.py` (добавить `decide_read/grep/glob` в dispatch для этих трёх инструментов)
- Test: `app/tests/env/test_code_index_guard_read_grep_glob.py`

**Interfaces:**
- Consumes: `GuardContext`, `paths.match_indexed`, `index_db.read_is_blockable`, `index_db.excluded_from_index`, `tools.tool`.
- Produces: `decisions.Decision(allow: bool, reason: str | None)`; `decisions.decide_read(tool_input, ctx) -> Decision | None`; `decisions.decide_grep(tool_input, cwd, ctx)`; `decisions.decide_glob(tool_input, cwd, ctx)`.

- [ ] **Step 1: Падающие тесты**

`app/tests/env/test_code_index_guard_read_grep_glob.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import decisions, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402

BIN = ("grep_code", "grep_text", "read_file", "list_files",
       "get_function", "get_file_summary", "stat_file", "get_stats")


def _ctx(root):
    tools.set_prefix("mcp__code_index__")
    return make_ctx(root)


def test_read_indexed_file_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_read({"file_path": str(root / "Cargo.toml")}, _ctx(root))
    assert d is not None and d.allow is False
    for name in ("read_file", "get_function", "get_file_summary"):
        assert f"mcp__code_index__{name}" in d.reason


def test_read_ritual_single_line_is_allowed(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_read(
        {"file_path": str(root / "Cargo.toml"), "offset": 1, "limit": 1}, _ctx(root))
    assert d is not None and d.allow is True


def test_read_non_indexed_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_read({"file_path": str(root / "Cargo.lock")}, _ctx(root)) is None


def test_read_oversize_is_skipped(tmp_path):
    root = build_repo(tmp_path, oversize=True)
    assert decisions.decide_read({"file_path": str(root / "src/main.rs")}, _ctx(root)) is None


def test_read_stale_index_is_skipped(tmp_path):
    root = build_repo(tmp_path, stale=True)
    assert decisions.decide_read({"file_path": str(root / "Cargo.toml")}, _ctx(root)) is None


def test_read_outside_root_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_read(
        {"file_path": str(tmp_path / "other.txt")}, _ctx(root)) is None


def test_grep_in_indexed_repo_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_grep({"pattern": "x"}, str(root), _ctx(root))
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason
    assert "mcp__code_index__grep_text" in d.reason


def test_grep_explicit_missing_path_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_grep(
        {"pattern": "x", "path": str(root / "nope")}, str(root), _ctx(root)) is None


def test_grep_excluded_glob_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_grep(
        {"pattern": "target", "glob": ".gitignore"}, str(root), _ctx(root)) is None


def test_glob_in_indexed_repo_is_denied(tmp_path):
    root = build_repo(tmp_path)
    d = decisions.decide_glob({"pattern": "src/**/*.rs"}, str(root), _ctx(root))
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason


def test_glob_binary_pattern_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert decisions.decide_glob({"pattern": "**/*.epf"}, str(root), _ctx(root)) is None


def test_glob_outside_root_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    assert decisions.decide_glob({"pattern": "**/*.rs"}, str(other), _ctx(root)) is None
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_read_grep_glob.py -q`

Expected: FAIL — `ImportError: cannot import name 'decisions'`.

- [ ] **Step 3: Реализовать `decisions.py`**

Порт `main.rs:329-364` (`decide_read`), `487-514` (`decide_grep`),
`516-551` (`decide_glob`) и константы `BINARY_EXT` (51-54).

```python
from dataclasses import dataclass

from . import index_db, paths, tools


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str | None = None


BINARY_EXT = (".epf", ".erf", ".cf", ".cfe", ".png", ".jpg", ".jpeg", ".gif",
              ".ico", ".bmp", ".zip", ".7z", ".gz", ".rar", ".exe", ".dll",
              ".bin", ".pdf", ".mxl", ".grs")
```

Правила — один-в-один:

- `decide_read`: пустой `file_path` → `None`; `match_indexed` → `None`, если вне
  корней; `limit == 1` и `offset in (None, 0, 1)` → `Decision(True)`; иначе
  `read_is_blockable(root, rel, case_insensitive=ctx.case_insensitive)`; если
  `False` → `None`; иначе deny с текстом из upstream (заменить имена
  инструментов на `tools.tool(...)` и сохранить `Read(file_path=..., offset=1,
  limit=1)` в подсказке).
- `decide_grep`: `path` непустой и не существует на диске → `None`; иначе
  матчинг `path` либо `cwd`; `excluded_from_index(root, rel)` или исключение по
  `glob` → `None`; иначе deny в `grep_code`/`grep_text`.
- `decide_glob`: бинарное расширение в `pattern` (lowercase) → `None`;
  кандидаты `[path, pattern]` + `cwd`, только если `path` пуст; первый
  матч; исключения по `rel` и по `pattern`; deny в `list_files`.

- [ ] **Step 4: Подключить в CLI**

В `cli.main` после разбора payload:

```python
from . import decisions
tool = payload.get("tool_name")
ti = payload.get("tool_input") or {}
cwd = payload.get("cwd")
d = None
tools.set_prefix(prefix or ctx.config.mcp_prefix)
if tool == "Read":
    d = decisions.decide_read(ti, ctx)
elif tool == "Grep":
    d = decisions.decide_grep(ti, cwd, ctx)
elif tool == "Glob":
    d = decisions.decide_glob(ti, cwd, ctx)
if d is not None:
    emit(d)
```

`emit`:

```python
def emit(decision) -> None:
    hs = {"hookEventName": "PreToolUse",
          "permissionDecision": "allow" if decision.allow else "deny"}
    if decision.reason:
        hs["permissionDecisionReason"] = decision.reason
    print(json.dumps({"hookSpecificOutput": hs}, ensure_ascii=False))
```

- [ ] **Step 5: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_read_grep_glob.py -q`

Expected: PASS (12 tests).

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/decisions.py \
        template/.claude/hooks/code_index_guard_lib/cli.py \
        app/tests/env/test_code_index_guard_read_grep_glob.py
git commit -m "feat(hooks): решения Read/Grep/Glob"
```

---

### Task 5: Разбор shell-цепочек

**Files:**
- Create: `template/.claude/hooks/code_index_guard_lib/shell.py`
- Test: `app/tests/env/test_code_index_guard_shell.py`

**Interfaces:**
- Consumes: `paths.normalize_dir`, `paths.fold_path`.
- Produces: `strip_heredocs(cmd)`, `heredoc_tag(line)`, `strip_here_strings(cmd)`, `split_chain(cmd) -> list[str]`, `parse_assignment(part, ps=False) -> tuple[str, str] | None`, `dir_change(part, base, home) -> str | None` (None — не смена каталога; `""` — каталог неизвестен), `home_dir() -> str | None`, `expand_vars(text, vars) -> str`, `has_explicit_path(lower) -> bool`, `cmd_contains_indexed_prefix(lower, prefix) -> bool`, `ls_targets_are_files(link, base) -> bool`.

- [ ] **Step 1: Падающие тесты**

`app/tests/env/test_code_index_guard_shell.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import paths, shell  # noqa: E402


def test_split_chain_quotes_and_pipe_cutoff():
    assert shell.split_chain("cd /r && grep -n 'a|b' x") == ["cd /r ", " grep -n 'a|b' x"]
    assert shell.split_chain("a; b\nc") == ["a", " b", "c"]
    assert shell.split_chain("git log | grep x") == ["git log "]


def test_heredoc_body_is_data():
    cmd = "git commit -F - <<'MSG'\nfix\nls -la\nMSG\n"
    assert shell.strip_heredocs(cmd) == "git commit -F - <<'MSG'"
    assert shell.heredoc_tag("python - <<PY") == "PY"
    assert shell.heredoc_tag("a <<< b") is None


def test_here_string_body_is_data():
    cmd = "git commit -m @'\nSelect-String x\n'@"
    assert "Select-String" not in shell.strip_here_strings(cmd)


def test_parse_assignment():
    assert shell.parse_assignment('root="/c/tmp"') == ("root", "/c/tmp")
    assert shell.parse_assignment("$root = 'C:/tmp'", ps=True) == ("root", "C:/tmp")
    assert shell.parse_assignment("a b=c") is None
    assert shell.parse_assignment("root=$HOME") is None


def test_dir_change():
    assert shell.dir_change("cd src", "C:/r", None) == "C:/r/src"
    assert shell.dir_change("cd ..", "C:/r/a", None) == "C:/r"
    assert shell.dir_change("cd ../other", "C:/r/a", None) == "C:/r/other"
    assert shell.dir_change("cd ~/p", "C:/r", "C:/Users/u") == "C:/Users/u/p"
    assert shell.dir_change("cd -", "C:/r", None) == ""
    assert shell.dir_change("popd", "C:/r", None) == ""
    assert shell.dir_change("sl", "C:/r", None) == "C:/r"
    assert shell.dir_change("ls", "C:/r", None) is None


def test_expand_vars_longest_first():
    assert shell.expand_vars("ls $a $abc", {"a": "/x", "abc": "/y"}) == "ls /x /y"


def test_explicit_path_and_prefix_boundary():
    assert shell.has_explicit_path("ls ~/.claude")
    assert shell.has_explicit_path("ls /tmp")
    assert not shell.has_explicit_path("ls src")
    assert shell.cmd_contains_indexed_prefix(
        paths.normalize_msys_drives("cd /c/repo && ls"), "c:/repo")
    assert not shell.cmd_contains_indexed_prefix(
        paths.normalize_msys_drives("ls /c/repo2"), "c:/repo")


def test_ls_targets_are_files(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert shell.ls_targets_are_files(f"ls -la {f}", str(tmp_path))
    assert not shell.ls_targets_are_files(f"ls -la {tmp_path}", str(tmp_path))
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_shell.py -q`

Expected: FAIL — `ImportError: cannot import name 'shell'`.

- [ ] **Step 3: Перенести функции**

Точные источники: `main.rs:1313-1400` (heredoc + split), `1137-1157`
(here-string), `621-648` (assignment), `658-725` (dir_change), `759-785`
(home/expand), `1192-1216` (explicit path/prefix), `1163-1186`
(ls_targets_are_files). Логику не упрощать: тесты кодируют различения
upstream. В `split_chain` сохранить обрыв на одиночной `|` и учёт кавычек.
В `dir_change` результат `""` — «каталог неизвестен»; `None` — звено не
является сменой каталога.

- [ ] **Step 4: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_shell.py -q`

Expected: PASS (8 tests).

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/shell.py \
        app/tests/env/test_code_index_guard_shell.py
git commit -m "feat(hooks): разбор shell-цепочек"
```

---

### Task 6: Решения Bash

**Files:**
- Create: `template/.claude/hooks/code_index_guard_lib/redirect.py`
- Create: `template/.claude/hooks/code_index_guard_lib/bash.py`
- Modify: `template/.claude/hooks/code_index_guard_lib/cli.py` (добавить `Bash`)
- Test: `app/tests/env/test_code_index_guard_bash.py`

**Interfaces:**
- Consumes: `shell.*`, `paths.*`, `index_db.read_is_blockable`, `decisions.Decision`, `decisions.BINARY_EXT`, `tools.tool`, `GuardContext`.
- Produces: `redirect.redirect_for_link(link, base, tool_label, ctx) -> Decision | None`, `bash.decide_bash(tool_input, cwd, ctx) -> Decision | None`.

- [ ] **Step 1: Падающие тесты**

`app/tests/env/test_code_index_guard_bash.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import bash, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


def _root(tmp_path, **kw):
    tools.set_prefix("mcp__code_index__")
    return build_repo(tmp_path, **kw)


def _decide(root, cmd, cwd=None):
    return bash.decide_bash({"command": cmd}, str(cwd or root), make_ctx(root))


def test_grep_on_indexed_file_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "grep -n main src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason


def test_cd_then_grep_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, f"cd {root} && grep -rn main src/")
    assert d is not None and d.allow is False


def test_grep_after_pipe_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "pytest -q 2>&1 | grep -E passed") is None


def test_git_grep_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git grep -n main -- src/") is None


def test_heredoc_with_commands_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git commit -F - <<'MSG'\nls src/\nMSG\n") is None


def test_grep_non_indexed_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -c name Cargo.lock") is None


def test_grep_excluded_dir_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -rn x target/release") is None


def test_cat_indexed_file_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "cat src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__read_file" in d.reason


def test_tail_non_indexed_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "tail -3 Cargo.lock") is None


def test_ls_existing_file_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, f"ls -la {root}/Cargo.toml") is None


def test_ls_directory_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "ls -R src")
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason


def test_binary_target_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "grep -n x src/data.epf") is None


def test_variable_outside_repo_skipped(tmp_path):
    root = _root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert _decide(root, f'root="{outside}"; ls "$root"') is None


def test_bare_ls_from_indexed_cwd_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "ls -la")
    assert d is not None and d.allow is False
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_bash.py -q`

Expected: FAIL — `ImportError: cannot import name 'bash'`.

- [ ] **Step 3: Реализовать `redirect.py` и `bash.py`**

`redirect_for_link` — порт `main.rs:790-858`:

- нераскрытые `$`/`` ` `` → `None`;
- бинарное расширение в звене → `None`;
- поиск самого длинного матчащего префикса через
  `shell.cmd_contains_indexed_prefix`;
- cwd-fallback только если `not shell.has_explicit_path(link)`;
- исключения по каждому слову звена (абсолютный путь проверяется от его
  собственного корня);
- deny с `grep_code`/`grep_text`/`read_file`/`list_files`/`get_stats`.

`decide_bash` — порт `main.rs:553-613`; `decide_bash_file_read` — порт
`865-960`. Порядок как в upstream: сначала пер-файловое чтение
(`cat`/`head`/`tail`), затем поиск звена по всей цепочке после
`strip_heredocs`, с учётом присваиваний и смены каталога; звенья `git ...`
пропускаются; `ls` по существующим файлам — пропуск; первое найденное звено
`grep`/`rg`/`find`/`ls` → `redirect_for_link`.

- [ ] **Step 4: Подключить в CLI**

```python
elif tool == "Bash":
    d = bash.decide_bash(ti, cwd, ctx)
```

- [ ] **Step 5: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_bash.py -q`

Expected: PASS (14 tests).

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/redirect.py \
        template/.claude/hooks/code_index_guard_lib/bash.py \
        template/.claude/hooks/code_index_guard_lib/cli.py \
        app/tests/env/test_code_index_guard_bash.py
git commit -m "feat(hooks): решения Bash"
```

---

### Task 7: Решения PowerShell

**Files:**
- Create: `template/.claude/hooks/code_index_guard_lib/powershell.py`
- Modify: `template/.claude/hooks/code_index_guard_lib/cli.py` (добавить `PowerShell` и fallback `Bash` → `PowerShell`)
- Test: `app/tests/env/test_code_index_guard_powershell.py`

**Interfaces:**
- Consumes: `shell.*`, `redirect.redirect_for_link`, `decisions.Decision`, `tools.tool`, `GuardContext`.
- Produces: `powershell.decide_powershell(tool_input, cwd, ctx) -> Decision | None`.

- [ ] **Step 1: Падающие тесты**

`app/tests/env/test_code_index_guard_powershell.py`:

```python
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import powershell, tools  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


def _root(tmp_path, **kw):
    tools.set_prefix("mcp__code_index__")
    return build_repo(tmp_path, **kw)


def _decide(root, cmd):
    return powershell.decide_powershell({"command": cmd}, str(root), make_ctx(root))


def test_get_content_indexed_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Get-Content src/main.rs")
    assert d is not None and d.allow is False
    assert "mcp__code_index__read_file" in d.reason


def test_get_content_with_path_and_totalcount(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, f"Get-Content -Path {root}/Cargo.toml -TotalCount 5")
    assert d is not None and d.allow is False
    assert "line_end=5" in d.reason


def test_get_content_non_indexed_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "Get-Content Cargo.lock") is None


def test_select_string_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Select-String -Path src/main.rs -Pattern main")
    assert d is not None and d.allow is False
    assert "mcp__code_index__grep_code" in d.reason


def test_get_childitem_directory_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Get-ChildItem src")
    assert d is not None and d.allow is False
    assert "mcp__code_index__list_files" in d.reason


def test_here_string_body_skipped(tmp_path):
    root = _root(tmp_path)
    cmd = "git commit -m @'\nGet-Content src/main.rs\n'@"
    assert _decide(root, cmd) is None


def test_git_command_skipped(tmp_path):
    root = _root(tmp_path)
    assert _decide(root, "git log -S main -- src/") is None


def test_set_location_changes_base(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "Set-Location src; Select-String -Pattern main")
    assert d is not None and d.allow is False


def test_alias_gc_denied(tmp_path):
    root = _root(tmp_path)
    d = _decide(root, "gc src/main.rs")
    assert d is not None and d.allow is False
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_powershell.py -q`

Expected: FAIL — `ImportError: cannot import name 'powershell'`.

- [ ] **Step 3: Реализовать порт**

Источники: `decide_powershell` — `main.rs:971-1026`; `decide_ps_file_read` —
`1032-1130`; `strip_here_strings` уже в `shell.py`. Сохранить полный набор
параметров: `-Path`, `-LiteralPath`, `-TotalCount`/`-First`/`-Head`,
`-Tail`/`-Last`, `-Raw`/`-Force`/`-NoNewline`, `-Encoding`; неизвестный
параметр → воздержаться. Цепочка звеньев — как в Bash: `Set-Location`/`sl`/
`Push-Location`/`pushd`/`popd`, присваивания `$root = "C:/tmp"`, `git ...`
пропуск, `Select-String`/`sls`/`Get-ChildItem`/`gci`/`ls`/`dir`/`findstr` →
`redirect_for_link`; `ls`/`dir`/`gci`/`Get-ChildItem` по существующим файлам —
пропуск.

- [ ] **Step 4: Подключить в CLI (включая fallback)**

```python
elif tool == "PowerShell":
    d = powershell.decide_powershell(ti, cwd, ctx)
elif tool == "Bash":
    d = bash.decide_bash(ti, cwd, ctx)
    if d is None:
        cmd = ti.get("command") or ""
        d = powershell.decide_powershell(
            {"command": shell.strip_heredocs(cmd)}, cwd, ctx)
```

- [ ] **Step 5: Тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_powershell.py -q`

Expected: PASS (9 tests).

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/powershell.py \
        template/.claude/hooks/code_index_guard_lib/cli.py \
        app/tests/env/test_code_index_guard_powershell.py
git commit -m "feat(hooks): решения PowerShell"
```

---

### Task 8: CLI-контракт и корпус проб

**Files:**
- Modify: `template/.claude/hooks/code_index_guard_lib/cli.py`
- Test: `app/tests/env/test_code_index_guard_cli.py`
- Test: `app/tests/env/test_code_index_guard_probes.py`

**Interfaces:**
- Consumes: `decisions`, `bash`, `powershell`, `tools`, `GuardContext`.
- Produces: `cli.run(payload, ctx) -> Decision | None`, `cli.render(decision) -> str` (чистые функции для тестов), `cli.main` использует их.

- [ ] **Step 1: Падающие тесты CLI**

`app/tests/env/test_code_index_guard_cli.py`:

```python
import io
import json
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import cli  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


def test_read_deny_contract(tmp_path):
    root = build_repo(tmp_path)
    out = cli.render(cli.run(
        {"tool_name": "Read", "tool_input": {"file_path": str(root / "Cargo.toml")}},
        make_ctx(root)))
    data = json.loads(out)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert data["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_allow_has_no_reason(tmp_path):
    root = build_repo(tmp_path)
    out = cli.render(cli.run(
        {"tool_name": "Read",
         "tool_input": {"file_path": str(root / "Cargo.toml"),
                        "offset": 1, "limit": 1}},
        make_ctx(root)))
    hs = json.loads(out)["hookSpecificOutput"]
    assert hs["permissionDecision"] == "allow"
    assert "permissionDecisionReason" not in hs


def test_skip_renders_nothing(tmp_path):
    root = build_repo(tmp_path)
    assert cli.render(cli.run(
        {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "x")}},
        make_ctx(root))) is None


def test_unknown_tool_is_skipped(tmp_path):
    root = build_repo(tmp_path)
    assert cli.run({"tool_name": "Edit", "tool_input": {}}, make_ctx(root)) is None


def test_broken_json_does_not_crash(monkeypatch, tmp_path):
    root = build_repo(tmp_path)
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.main([])
    assert out.getvalue() == ""


def test_config_less_hook_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("CODE_INDEX_GUARD_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"tool_name": "Grep", "tool_input": {"pattern": "x"}, "cwd": str(tmp_path)})))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.main([])
    assert out.getvalue() == ""


def test_mcp_prefix_cli_overrides(tmp_path):
    root = build_repo(tmp_path)
    ctx = make_ctx(root)
    d = cli.run({"tool_name": "Grep", "tool_input": {"pattern": "x"},
                 "cwd": str(root)}, ctx, prefix="mcp__ci__")
    assert "mcp__ci__grep_code" in cli.render(d)
```

- [ ] **Step 2: Тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_guard_cli.py -q`

Expected: FAIL — `AttributeError: module ... has no attribute 'run'`.

- [ ] **Step 3: Реализовать чистые `run`/`render` и переписать `main`**

```python
def run(payload, ctx, prefix=None):
    from . import bash, decisions, powershell, shell, tools
    tools.set_prefix(prefix or ctx.config.mcp_prefix)
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}
    cwd = payload.get("cwd")
    if tool == "Read":
        return decisions.decide_read(ti, ctx)
    if tool == "Grep":
        return decisions.decide_grep(ti, cwd, ctx)
    if tool == "Glob":
        return decisions.decide_glob(ti, cwd, ctx)
    if tool == "PowerShell":
        return powershell.decide_powershell(ti, cwd, ctx)
    if tool == "Bash":
        d = bash.decide_bash(ti, cwd, ctx)
        if d is None:
            cmd = ti.get("command") or ""
            d = powershell.decide_powershell(
                {"command": shell.strip_heredocs(cmd)}, cwd, ctx)
        return d
    return None


def render(decision):
    if decision is None:
        return None
    hs = {"hookEventName": "PreToolUse",
          "permissionDecision": "allow" if decision.allow else "deny"}
    if decision.reason:
        hs["permissionDecisionReason"] = decision.reason
    return json.dumps({"hookSpecificOutput": hs}, ensure_ascii=False)
```

`main`: разобрать args, `ctx = build_context()`, `--list-roots` → return,
прочитать stdin, `json.loads`, `if not isinstance(payload, dict): return`,
`out = render(run(payload, ctx, prefix))`, `if out: print(out)`; всё в
`try/except Exception: return`.

- [ ] **Step 4: Написать корпус проб**

`app/tests/env/test_code_index_guard_probes.py` — параметризованный список
различений (адаптация upstream `tests/probes/probes.json`). Минимум 24 случая:

```python
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from code_index_guard_lib import cli  # noqa: E402
from env.guard_fixtures import build_repo, make_ctx  # noqa: E402


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
```

- [ ] **Step 5: Тесты проходят**

Run:
`.venv/bin/python -m pytest app/tests/env/test_code_index_guard_cli.py app/tests/env/test_code_index_guard_probes.py -q`

Expected: PASS (7 + 24).

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/hooks/code_index_guard_lib/cli.py \
        app/tests/env/test_code_index_guard_cli.py \
        app/tests/env/test_code_index_guard_probes.py
git commit -m "feat(hooks): CLI-диспетчер и корпус проб"
```

---

### Task 9: Интеграция с env-системой

**Files:**
- Modify: `app/src/agentmon/env/config_schema.py`
- Modify: `app/src/agentmon/env/project_api.py:200-215, 428-440`
- Modify: `app/src/agentmon/env/content.py`
- Modify: `app/tests/env/test_content_deploy.py`
- Modify: `app/tests/env/test_config_schema.py`

**Interfaces:**
- Consumes: `content.deploy_content`, `mcp_catalog.mcp_name_overrides`.
- Produces: `McpSelection.catalog_dir`, `McpSelection.project_name`; `content._guard_entries(mcp) -> list[tuple[str, str]]`, `content._guard_config_text(mcp) -> str`, `content._inject_guard_hook(settings_text, py_cmd) -> str`; файл `.claude/hooks/code-index-guard.toml`; `PreToolUse`-блок в `settings.json`.

- [ ] **Step 1: Падающие тесты схемы и деплоя**

В `app/tests/env/test_config_schema.py` добавить:

```python
def test_mcp_selection_guard_fields_roundtrip():
    sel = McpSelection(id="code-index", enabled=True, mode="managed",
                       catalog_dir="/code/cfg", project_name="proj")
    data = {"schema_version": 1, "project_name": "p", "project_dir": "/p",
            "developer_id": "", "developer_email": "", "platform_dir": "",
            "platform_version": "", "db_kind": "file", "db_connection": "",
            "web_publication": "", "mcp": [sel.__dict__], "agents": []}
    cfg = EnvConfig.from_dict(data)
    assert cfg.mcp[0].catalog_dir == "/code/cfg"
    assert cfg.mcp[0].project_name == "proj"
```

В `app/tests/env/test_content_deploy.py` добавить:

```python
def _config(tmp_path, mcp):
    from agentmon.env.config_schema import EnvConfig
    return EnvConfig(
        schema_version=1, project_name="proj", project_dir=str(tmp_path / "p"),
        developer_id="", developer_email="", platform_dir="",
        platform_version="", db_kind="file", db_connection="",
        web_publication="", mcp=mcp, agents=[])


def test_deploy_writes_guard_config_and_hook(tmp_path):
    from agentmon.env.config_schema import McpSelection
    import json
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    cfg = _config(tmp_path, [McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="C:/proj/src/cf", project_name="proj")])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    guard = (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml")
    text = guard.read_text(encoding="utf-8")
    assert 'path = "C:/proj/src/cf"' in text
    assert 'alias = "proj"' in text
    assert 'mcp_prefix = "mcp__code_index__"' in text
    settings = json.loads((tmp_path / "p" / ".claude" / "settings.json")
                          .read_text(encoding="utf-8"))
    cmds = [h["command"] for e in settings["hooks"]["PreToolUse"]
            for h in e["hooks"]]
    assert any("code_index_guard.py" in c for c in cmds)


def test_deploy_without_code_index_has_no_hook(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    cfg = _config(tmp_path, [McpSelection(id="bsl-ls", enabled=True, mode="managed")])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    guard = tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
    assert guard.exists()
    assert "[[local]]" not in guard.read_text(encoding="utf-8")
    settings = (tmp_path / "p" / ".claude" / "settings.json").read_text(encoding="utf-8")
    assert "code_index_guard.py" not in settings


def test_deploy_guard_uses_actual_mcp_name(tmp_path):
    from agentmon.env.config_schema import McpSelection
    from agentmon.env.content import deploy_content
    from agentmon.backends.local import LocalProvisioner
    cfg = _config(tmp_path, [McpSelection(
        id="code-index", enabled=True, mode="managed",
        catalog_dir="C:/proj/src/cf", project_name="proj",
        connection='{"code_index_queries": {"type": "http", "url": "http://x:1/mcp"}}')])
    prov = LocalProvisioner()
    deploy_content(prov, cfg, update=False)
    text = (tmp_path / "p" / ".claude" / "hooks" / "code-index-guard.toml"
            ).read_text(encoding="utf-8")
    assert 'mcp_prefix = "mcp__code_index_queries__"' in text
```

- [ ] **Step 2: Тесты падают**

Run:
`.venv/bin/python -m pytest app/tests/env/test_config_schema.py app/tests/env/test_content_deploy.py -q`

Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'catalog_dir'`.

- [ ] **Step 3: Расширить `McpSelection` и заполнение**

`config_schema.py`:

```python
@dataclass
class McpSelection:
    id: str
    enabled: bool
    mode: str
    endpoint: str | None = None
    secret_env: str | None = None
    connection: str | None = None
    catalog_dir: str | None = None
    project_name: str | None = None
```

В `project_api._create` и `_build_update_config` добавить в оба
`McpSelection(...)`:

```python
catalog_dir=row.get("catalog_dir"),
project_name=row.get("project_name"),
```

- [ ] **Step 4: Реализовать генерацию в `content.py`**

Добавить рядом с `_is_special`:

```python
_GUARD_CFG_REL = Path(".claude/hooks/code-index-guard.toml")


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _default_alias(path: str) -> str:
    last = path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return last.lower().replace(" ", "_")


def _guard_entries(mcp) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for sel in mcp:
        if not getattr(sel, "enabled", False):
            continue
        if sel.id not in ("code-index", "code-index-local"):
            continue
        path = getattr(sel, "catalog_dir", None)
        if not path:
            continue
        alias = getattr(sel, "project_name", None) or _default_alias(path)
        out.append((path, alias))
    return out


def _guard_config_text(mcp) -> str:
    from .mcp_catalog import mcp_name_overrides
    actual = mcp_name_overrides(mcp).get("code_index", "code_index")
    lines = [
        "# Сгенерировано при развёртывании окружения agentmon.",
        "# Ручные правки будут перезаписаны при обновлении окружения.",
        f'mcp_prefix = "mcp__{actual}__"',
        "",
    ]
    for path, alias in _guard_entries(mcp):
        lines += ["[[local]]",
                  f'path = "{_toml_escape(path)}"',
                  f'alias = "{_toml_escape(alias)}"', ""]
    return "\n".join(lines) + "\n"


def _inject_guard_hook(settings_text: str, py_cmd: str) -> str:
    data = json.loads(settings_text)
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre.insert(0, {
        "matcher": "Read|Grep|Glob|Bash|PowerShell",
        "hooks": [{
            "type": "command",
            "command": (f'{py_cmd} "$CLAUDE_PROJECT_DIR/.claude/'
                        'hooks/code_index_guard.py"'),
            "timeout": 10,
        }],
    })
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
```

В `_is_special` добавить:

```python
        or rel == _GUARD_CFG_REL
```

В `deploy_content` после `put_tree`:

```python
    prov.write_text(f"{claude}/hooks/code-index-guard.toml",
                    _guard_config_text(config.mcp))
```

и после подстановок в `settings`:

```python
    if _guard_entries(config.mcp):
        settings = _inject_guard_hook(settings, _py_cmd(prov, project_dir))
```

`_py_cmd` возвращает уже закавыченный путь интерпретатора. Вставка — **после**
`mcp_subs`, иначе `code_index` в имени файла хука будет переименован.

- [ ] **Step 5: Тесты проходят**

Run:
`.venv/bin/python -m pytest app/tests/env/test_config_schema.py app/tests/env/test_content_deploy.py app/tests/env/test_content_conditions.py -q`

Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/config_schema.py \
        app/src/agentmon/env/project_api.py \
        app/src/agentmon/env/content.py \
        app/tests/env/test_config_schema.py \
        app/tests/env/test_content_deploy.py
git commit -m "feat(env): генерация конфига гарда и регистрация хука"
```

---

### Task 10: Документация и финальная проверка

**Files:**
- Modify: `template/README.md`
- Modify: `docs/mcp/code-index-common.md` (если файла нет — создать короткую заметку в `template/README.md` достаточно)

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: описание хука и отката для пользователя.

- [ ] **Step 1: Обновить `template/README.md`**

В списке `hooks/` после `bsl_nudge.py` добавить:

```markdown
- `code_index_guard.py` — PreToolUse-хук: перенаправляет нативные
  Read/Grep/Glob/Bash/PowerShell по индексированным каталогам в инструменты
  `code_index`. Конфиг `code-index-guard.toml` генерируется при развёртывании
  окружения; без него хук инертен. Откат — удалить блок `PreToolUse` из
  `.claude/settings.json`.
```

- [ ] **Step 2: Прогнать все тесты хука и env**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_code_index_guard_*.py \
  app/tests/env/test_config_schema.py app/tests/env/test_content_deploy.py \
  app/tests/env/test_content_conditions.py -q
```

Expected: PASS, ни одного FAIL.

- [ ] **Step 3: Ручной smoke-тест контракта**

Run:

```bash
printf '%s' '{"tool_name":"Grep","tool_input":{"pattern":"x"},"cwd":"/tmp"}' | \
  .venv/bin/python template/.claude/hooks/code_index_guard.py; echo "exit=$?"
```

Expected: пустой stdout, `exit=0` (нет конфига → хук инертен).

- [ ] **Step 4: Финальный коммит**

```bash
git add template/README.md
git commit -m "docs(hooks): описание code-index-guard в template"
```

---

## Self-Review

**1. Покрытие спеки:**

- Python stdlib-хук — Tasks 1–8.
- Read/Grep/Glob/Bash/PowerShell — Tasks 4, 6, 7.
- `index.db` + свежесть + исключения — Task 3.
- Конфиг из карточек MCP, `McpSelection`, `deploy_content`, `settings.json` —
  Task 9.
- Тесты, корпус проб, CLI-контракт — Tasks 1–8, 10.
- Документация и откат — Task 10.
- Не-цели (журнал, `--list-roots`, автопоиск) — не реализуются, `--list-roots`
  принимается и молчит.

**2. Placeholder scan:** незаполненных шагов нет; все тесты и новый код
приведены полностью; механические порты ссылаются на точные диапазоны
`main.rs` в репозитории.

**3. Type consistency:** `GuardConfig`, `GuardContext`, `Decision`,
`indexed_paths`, `read_is_blockable`, `excluded_from_index`, префикс
`tools.tool`, `cli.run/render` — имена и сигнатуры совпадают во всех задачах.
