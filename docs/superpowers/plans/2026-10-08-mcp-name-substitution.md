# MCP Name Substitution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When creating a project, substitute each selected MCP's actual server name in place of the template's hardcoded placeholder names across `template/.claude`.

**Architecture:** Add `mcp_name_overrides(selections)` to `env/mcp_catalog.py` (sharing a `_server_name` helper with `build_mcp_json` so override names always match `.mcp.json` keys). `env/content.py::deploy_content` runs a single text-replacement pass over the deployed `project/.claude` when `update=False` and overrides exist.

**Tech Stack:** Python 3, pytest. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-08-mcp-name-substitution-design.md`.
- All commands run from the `app/` directory.
- Placeholders are the default `mcp_name` of each MCP type in `env/mcp_types.py`: `bsl-ls`→`bsl_ls`, `1c-platform`→`1c_platform`, `1c-naparnic`→`1c_naparnic`, `code-index`→`code_index`.
- Substitution runs **only** on create (`update=False`), never on env update.
- Keep underscore naming convention; do not edit template files or type defaults.
- A selected MCP whose actual name equals its placeholder, or whose type is unknown / has no default `mcp_name`, produces no override.
- Replacement is plain `str.replace(placeholder, actual)` — verified safe (every placeholder occurrence in `template/` is a genuine MCP name reference).
- Commit style: Russian conventional-commit subject + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` footer. Commit to local `master`.

---

### Task 1: `mcp_name_overrides` + shared `_server_name` in mcp_catalog

**Files:**
- Modify: `app/src/agentmon/env/mcp_catalog.py` (refactor `build_mcp_json`, lines 71-91; add helpers)
- Test: `app/tests/env/test_mcp_catalog_from_connection.py`

**Interfaces:**
- Consumes: `McpSelection` (`env/config_schema.py`: fields `id`, `enabled`, `mode`, `endpoint`, `connection`); `env/mcp_types.get_type(key)` → `McpType` with `.defaults: dict`; existing module-level `_parse_connection(fragment, sel_id) -> (name, value)`.
- Produces:
  - `_server_name(sel) -> str` — the `.mcp.json` server key for a selection.
  - `mcp_name_overrides(selections) -> dict[str, str]` — `{placeholder: actual}` for enabled selections where the type has a default `mcp_name` and the actual name differs.

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_mcp_catalog_from_connection.py`:

```python
from agentmon.env.mcp_catalog import mcp_name_overrides


def test_overrides_renamed_mcp():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {"bsl_ls": "bsl_checker"}


def test_overrides_default_name_gives_no_entry():
    sel = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_unknown_type_skipped():
    # вид "custom" существует, но без дефолтного mcp_name → пропуск
    sel = [McpSelection(
        id="custom", enabled=True, mode="managed",
        connection='"foo": {"type":"http","url":"http://x/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_absent_type_skipped():
    sel = [McpSelection(id="does-not-exist", enabled=True, mode="managed")]
    assert mcp_name_overrides(sel) == {}


def test_overrides_disabled_skipped():
    sel = [McpSelection(
        id="bsl-ls", enabled=False, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://x/mcp"}',
    )]
    assert mcp_name_overrides(sel) == {}


def test_overrides_without_connection_uses_id():
    # нет connection → актуальное имя = sel.id (standard_key вида)
    sel = [McpSelection(id="code-index", enabled=True, mode="managed")]
    assert mcp_name_overrides(sel) == {"code_index": "code-index"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/env/test_mcp_catalog_from_connection.py -v`
Expected: the six new tests ERROR/FAIL with `ImportError: cannot import name 'mcp_name_overrides'`.

- [ ] **Step 3: Refactor `build_mcp_json` to use a shared `_server_name` and add `mcp_name_overrides`**

In `app/src/agentmon/env/mcp_catalog.py`, replace the existing `build_mcp_json` function (currently lines 71-91):

```python
def build_mcp_json(selections, catalog=CATALOG) -> dict:
    servers: dict[str, dict] = {}
    for sel in selections:
        if not sel.enabled:
            continue
        connection = getattr(sel, "connection", None)
        if connection:
            name, value = _parse_connection(connection, sel.id)
            servers[name] = value
            continue
        if sel.id not in catalog:
            raise ValueError(f"неизвестный MCP-сервер: {sel.id}")
        spec = catalog[sel.id]
        if sel.mode == "external":
            servers[sel.id] = _external_entry(sel.endpoint or "")
        elif spec.transport == "http":
            servers[sel.id] = {"url": f"http://127.0.0.1:{spec.default_port}"}
        else:  # managed stdio
            servers[sel.id] = {"command": "docker",
                               "args": ["exec", "-i", sel.id]}
    return {"mcpServers": servers}
```

with:

```python
def _server_name(sel) -> str:
    """Ключ сервера в .mcp.json для выбранного MCP.

    С connection — имя берётся из фрагмента справочника; иначе — sel.id
    (standard_key вида или имя карточки). Единый источник истины для
    build_mcp_json и mcp_name_overrides.
    """
    connection = getattr(sel, "connection", None)
    if connection:
        name, _ = _parse_connection(connection, sel.id)
        return name
    return sel.id


def build_mcp_json(selections, catalog=CATALOG) -> dict:
    servers: dict[str, dict] = {}
    for sel in selections:
        if not sel.enabled:
            continue
        name = _server_name(sel)
        connection = getattr(sel, "connection", None)
        if connection:
            _, value = _parse_connection(connection, sel.id)
            servers[name] = value
            continue
        if sel.id not in catalog:
            raise ValueError(f"неизвестный MCP-сервер: {sel.id}")
        spec = catalog[sel.id]
        if sel.mode == "external":
            servers[name] = _external_entry(sel.endpoint or "")
        elif spec.transport == "http":
            servers[name] = {"url": f"http://127.0.0.1:{spec.default_port}"}
        else:  # managed stdio: команда docker exec по container id (sel.id)
            servers[name] = {"command": "docker",
                             "args": ["exec", "-i", sel.id]}
    return {"mcpServers": servers}


def mcp_name_overrides(selections) -> dict[str, str]:
    """{плейсхолдер: актуальное_имя} для включённых выбранных MCP.

    Плейсхолдер — дефолтный mcp_name вида (env/mcp_types). Пропускаем виды без
    дефолтного имени, неизвестные виды и случаи, где актуальное имя совпадает
    с плейсхолдером.
    """
    from .mcp_types import get_type   # локальный импорт — без цикла модулей
    overrides: dict[str, str] = {}
    for sel in selections:
        if not getattr(sel, "enabled", False):
            continue
        try:
            placeholder = get_type(sel.id).defaults.get("mcp_name")
        except KeyError:
            placeholder = None
        if not placeholder:
            continue
        actual = _server_name(sel)
        if actual and actual != placeholder:
            overrides[placeholder] = actual
    return overrides
```

- [ ] **Step 4: Run the full mcp_catalog test set to verify pass + no regressions**

Run: `python -m pytest tests/env/test_mcp_catalog_from_connection.py tests/env/test_mcp_catalog.py tests/env/test_mcp_catalog_ext.py -v`
Expected: PASS (new tests green; existing build_mcp_json tests still green).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/mcp_catalog.py app/tests/env/test_mcp_catalog_from_connection.py
git commit -m "feat(mcp): карта подстановки актуальных имён MCP (mcp_name_overrides)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Apply substitution in deploy_content

**Files:**
- Modify: `app/src/agentmon/env/content.py` (add import, `_apply_mcp_names`, call in `deploy_content`)
- Test: `app/tests/env/test_content_deploy.py`

**Interfaces:**
- Consumes: `mcp_name_overrides` from Task 1; `config.mcp: list[McpSelection]`; existing `deploy_content(config, *, update)`.
- Produces: no new public surface; adds private `_apply_mcp_names(claude_dir: Path, overrides: dict) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_content_deploy.py` (note existing imports at top: `EnvConfig, AgentModel, SCHEMA_VERSION` and `content`; `cfg(tmp_path, agents)` helper returns a config with `mcp=[]`):

```python
from agentmon.env.config_schema import McpSelection


def _bsl_renamed():
    return [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_checker": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]


def test_deploy_substitutes_selected_mcp_name(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(config, update=False)
    c = tmp_path / ".claude"

    dev = (c / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_checker__" in dev
    assert "mcp__bsl_ls__" not in dev

    settings = (c / "settings.json").read_text(encoding="utf-8")
    assert "mcp__bsl_checker" in settings
    assert "mcp__bsl_ls" not in settings

    skill = (c / "skills" / "mcp-usage" / "SKILL.md").read_text(encoding="utf-8")
    assert "bsl_checker" in skill
    assert "bsl_ls" not in skill


def test_deploy_leaves_unselected_placeholder(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()   # code-index НЕ выбран
    content.deploy_content(config, update=False)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__code_index__" in dev


def test_deploy_update_skips_mcp_substitution(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = _bsl_renamed()
    content.deploy_content(config, update=True)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_ls__" in dev
    assert "bsl_checker" not in dev


def test_deploy_no_overrides_when_default_name(tmp_path):
    config = cfg(tmp_path, [])
    config.mcp = [McpSelection(
        id="bsl-ls", enabled=True, mode="managed",
        connection='"bsl_ls": {"type":"http","url":"http://localhost:8001/mcp"}',
    )]
    content.deploy_content(config, update=False)
    dev = (tmp_path / ".claude" / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "mcp__bsl_ls__" in dev
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/env/test_content_deploy.py -k "substitut or placeholder or update_skips or no_overrides" -v`
Expected: `test_deploy_substitutes_selected_mcp_name` and `test_deploy_leaves_unselected_placeholder` FAIL (placeholder still present / renamed name absent). `test_deploy_update_skips_mcp_substitution` and `test_deploy_no_overrides_when_default_name` happen to PASS already (no substitution exists yet) — that is expected; they guard behavior for later steps.

- [ ] **Step 3: Add the substitution helper and call it in deploy_content**

In `app/src/agentmon/env/content.py`, add the import near the top (after the existing `from .scaffold import write_preserving`):

```python
from .mcp_catalog import mcp_name_overrides
```

Add this helper above `deploy_content`:

```python
def _apply_mcp_names(claude_dir: Path, overrides: dict) -> None:
    """Подставляет актуальные имена MCP вместо плейсхолдеров шаблона.

    Проходит по всем текстовым файлам .claude и заменяет каждое имя-плейсхолдер
    на актуальное. Бинарные/нечитаемые файлы и __pycache__ пропускаются.
    """
    for path in sorted(claude_dir.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            path.write_text(new, encoding="utf-8")
```

Replace the tail of `deploy_content` — currently:

```python
    if not update:
        write_preserving(project / "README.md",
                         f"## {config.project_name}\n", update=update)
```

with:

```python
    if not update:
        write_preserving(project / "README.md",
                         f"## {config.project_name}\n", update=update)
        # Подстановка актуальных имён выбранных MCP вместо плейсхолдеров шаблона —
        # только при создании (на обновлении окружения имена не трогаем).
        overrides = mcp_name_overrides(config.mcp)
        if overrides:
            _apply_mcp_names(claude, overrides)
```

- [ ] **Step 4: Run the content tests to verify pass + no regressions**

Run: `python -m pytest tests/env/test_content_deploy.py -v`
Expected: PASS (all four new tests green; the eight pre-existing deploy tests still green).

- [ ] **Step 5: Run the full env suite to confirm no regressions**

Run: `python -m pytest tests/env -q`
Expected: PASS (no failures).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/content.py app/tests/env/test_content_deploy.py
git commit -m "feat(env): подстановка актуальных имён MCP в .claude при создании проекта

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the executor

- Do not modify any file under `template/` — the placeholders stay as the canonical defaults.
- `config.mcp` holds `McpSelection` objects; in production `_prepare_install` builds them with `id = standard_key or name` and `connection = connection_json`, so `sel.id` is the MCP type key for reference entries.
- If `python -m pytest` is not on PATH, use `pytest` directly; both run from `app/`.
