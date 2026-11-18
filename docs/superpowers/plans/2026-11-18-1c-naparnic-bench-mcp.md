# MCP 1c_naparnic в benchmark-окружении — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подключать общий MCP `1c_naparnic` к benchmark-проекту по адресу из `test.env` и направлять агента в `ask_1c_ai` при ошибках компиляции/сигнатур через условный блок `@if 1c_naparnic`.

**Architecture:** Benchmark-setup читает необязательный `MCP_1C_NAPARNIC_URL`, строит MCP-план `1c-naparnic` (http-connection, без запуска контейнера) и проверяет адрес HTTP-запросом в preflight. Рендерер шаблонов получает декларативную карту «условие → виды MCP»; блоки `@if 1c_naparnic` в `mcp-usage` вырезаются или остаются по составу включённых MCP проекта.

**Tech Stack:** Python 3.14, pytest 9.1.1, существующие модули `agentmon.env.bench_setup`, `agentmon.env.content`.

**Spec:** `docs/superpowers/specs/2026-11-18-1c-naparnic-bench-mcp-design.md`

## Global Constraints

- Все тесты запускаются из корня репозитория: `.venv/bin/python -m pytest <пути> -q`.
- Работаем в `main`; коммиты только локальные, **без push**.
- Тексты — на русском, в стиле окружающего кода.
- `benchmark/test.env` (gitignored, содержит секреты) **не менять**.
- Точные имена: env-ключ `MCP_1C_NAPARNIC_URL`, условие шаблона `1c_naparnic`, `standard_key="1c-naparnic"`, `mcp_name="1c_naparnic"`.
- Сервер необязателен: ключ не задан → нет MCP в `.mcp.json` и нет блока в навыке.
- Проверка доступности — HTTP (не TCP); контейнер setup не запускает.
- TDD: сначала падающий тест, затем минимальная реализация, затем прогон.

---

### Task 1: Benchmark-setup подключает 1c_naparnic

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py` (`OPTIONAL_KEYS`, `BenchConfig`, `load_config`, `build_mcp_plans`, `preflight`, `run_setup`)
- Modify: `app/tests/env/test_bench_setup.py`
- Modify: `benchmark/example.test.env`
- Modify: `benchmark/setup_benchmark.py` (итоговая сводка)

**Interfaces:**
- Consumes: существующие `McpPlan`, `_connection_http`, `_url_host_port`, `default_http_ok`, `write_env`/`make_repo_root` из тестов.
- Produces: `BenchConfig.one_c_naparnic_url: str | None`; MCP-план с `standard_key="1c-naparnic"`, `mcp_name="1c_naparnic"`; `preflight(..., http_ok=default_http_ok)`.

- [ ] **Step 1: Добавить падающие тесты разбора конфига**

В `app/tests/env/test_bench_setup.py` после `test_load_config_optional_1c_md_and_code_index_overrides` (перед `import json`) добавить:

```python
def test_load_config_optional_1c_naparnic(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    assert cfg.one_c_naparnic_url is None
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    assert cfg.one_c_naparnic_url == "http://localhost:8003/mcp"


def test_load_config_rejects_bad_1c_naparnic_url(tmp_path):
    with pytest.raises(SetupError, match="MCP_1C_NAPARNIC_URL"):
        load_config(
            write_env(tmp_path, MCP_1C_NAPARNIC_URL="localhost:8003/mcp"),
            repo_root=tmp_path)
```

- [ ] **Step 2: Добавить падающие тесты плана и preflight**

После `test_preflight_rejects_unreachable_shared_mcp` добавить:

```python
def test_preflight_checks_naparnic_http(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    calls = []
    preflight(cfg, repo_root=make_repo_root(tmp_path),
              store=make_store(tmp_path), registry=make_registry(tmp_path),
              tcp_ok=lambda url: True,
              http_ok=lambda url: calls.append(url) or True)
    assert calls == ["http://localhost:8003/mcp"]


def test_preflight_rejects_unreachable_naparnic(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path)
    with pytest.raises(SetupError, match="MCP_1C_NAPARNIC_URL"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True,
                  http_ok=lambda url: False)
```

После `test_build_mcp_plans_with_1c_md` добавить:

```python
def test_build_mcp_plans_with_1c_naparnic(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_NAPARNIC_URL="http://ai.local:8003/mcp"),
        repo_root=tmp_path,
    )
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "1c_naparnic", "code_index"]
    naparnic = plans[2]
    assert naparnic.standard_key == "1c-naparnic"
    assert naparnic.kind == "docker"
    assert naparnic.url == "ai.local"
    assert naparnic.port == 8003
    assert json.loads("{" + naparnic.connection_json + "}") == {
        "1c_naparnic": {
            "type": "http",
            "url": "http://ai.local:8003/mcp",
        }
    }
    servers = build_mcp_json(build_env_config(cfg, plans).mcp)["mcpServers"]
    assert servers["1c_naparnic"] == {
        "type": "http", "url": "http://ai.local:8003/mcp"}


def test_build_mcp_plans_order_with_both_optional(tmp_path):
    cfg = load_config(
        write_env(tmp_path,
                  MCP_1C_MD_URL="http://localhost/bench/hs/mcp",
                  MCP_1C_NAPARNIC_URL="http://localhost:8003/mcp"),
        repo_root=tmp_path,
    )
    assert [plan.mcp_name for plan in build_mcp_plans(cfg)] == [
        "bsl_ls", "1c_platform", "1c-md", "1c_naparnic", "code_index"]
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_bench_setup.py -q
```

Expected: FAIL — `BenchConfig` без `one_c_naparnic_url`, `preflight` не принимает `http_ok`, плана `1c_naparnic` нет.

- [ ] **Step 4: Реализовать чтение ключа**

В `app/src/agentmon/env/bench_setup.py` заменить `OPTIONAL_KEYS`:

```python
OPTIONAL_KEYS = (
    "MCP_1C_MD_URL", "MCP_1C_NAPARNIC_URL", "BENCH_DT_PATH",
    "MCP_CODE_INDEX_HOST", "CODE_INDEX_WAIT_MINUTES",
)
```

В `BenchConfig` после `one_c_md_url: str | None` добавить:

```python
    one_c_naparnic_url: str | None
```

В `load_config` расширить цикл проверки URL:

```python
    for key in ("MCP_BSL_LS_URL", "MCP_1C_PLATFORM_URL", "MCP_1C_MD_URL",
                "MCP_1C_NAPARNIC_URL"):
```

В `return BenchConfig(...)` после `one_c_md_url=...` добавить:

```python
        one_c_naparnic_url=(
            data.get("MCP_1C_NAPARNIC_URL") or "").strip() or None,
```

- [ ] **Step 5: Реализовать MCP-план**

В `build_mcp_plans` после блока `if cfg.one_c_md_url:` и **до** `plans.append(McpPlan(standard_key="code-index", ...))` вставить:

```python
    if cfg.one_c_naparnic_url:
        naparnic_host, naparnic_port = _url_host_port(cfg.one_c_naparnic_url)
        plans.append(McpPlan(
            standard_key="1c-naparnic", mcp_name="1c_naparnic",
            kind="docker",
            connection_json=_connection_http("1c_naparnic",
                                             cfg.one_c_naparnic_url),
            purpose=("Объяснение логики кода, любые вопросы по информационно-"
                     "технологическому сопровождению 1С"),
            url=naparnic_host, port=naparnic_port,
        ))
```

- [ ] **Step 6: Реализовать HTTP-проверку в preflight**

Сигнатуру `preflight` заменить на:

```python
def preflight(cfg: BenchConfig, *, repo_root: Path, store, registry,
              tcp_ok=default_tcp_ok, http_ok=default_http_ok,
              allow_existing: bool = False) -> None:
```

После цикла проверки `MCP_BSL_LS_URL`/`MCP_1C_PLATFORM_URL` добавить:

```python
    if cfg.one_c_naparnic_url and not http_ok(cfg.one_c_naparnic_url):
        raise SetupError(
            "MCP_1C_NAPARNIC_URL: сервер недоступен по адресу "
            f"{cfg.one_c_naparnic_url}")
```

В `run_setup` передать `http_ok` в оба вызова preflight:

```python
        preflight(cfg, repo_root=repo_root, store=store, registry=registry,
                  tcp_ok=tcp_ok, http_ok=http_ok, allow_existing=True)
```

```python
    preflight(cfg, repo_root=repo_root, store=store, registry=registry,
              tcp_ok=tcp_ok, http_ok=http_ok)
```

- [ ] **Step 7: Обновить example.test.env**

В `benchmark/example.test.env` после блока `MCP_1C_MD_URL` добавить:

```dotenv
# URL общего MCP 1С:Напарник; если не задан — сервер не подключается.
# Токен Напарника настроен на стороне сервера, в test.env его нет.
#MCP_1C_NAPARNIC_URL=http://localhost:8003/mcp
```

- [ ] **Step 8: Обновить итоговую сводку CLI**

В `benchmark/setup_benchmark.py` после вывода `1c-md` добавить:

```python
    if cfg.one_c_naparnic_url:
        print(f"  1c_naparnic: {cfg.one_c_naparnic_url}")
```

- [ ] **Step 9: Прогнать тесты**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_bench_setup.py -q
```

Expected: PASS (весь файл).

- [ ] **Step 10: Коммит**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py benchmark/example.test.env benchmark/setup_benchmark.py
git commit -m "feat(bench): MCP 1c_naparnic по адресу из test.env"
```

---

### Task 2: Декларативные условные блоки в content.py

**Files:**
- Modify: `app/src/agentmon/env/content.py` (`_render_conditional_blocks`, `_render_template_texts`, `deploy_content`)
- Modify: `app/tests/env/test_content_conditions.py`

**Interfaces:**
- Consumes: `McpSelection` с `id`/`enabled` (в тестах — `sel(...)`).
- Produces: `_CONDITION_MCP_IDS: dict[str, tuple[str, ...]]`; `conditional_flags(mcp) -> dict[str, bool]`; `_render_conditional_blocks(text, conditions: dict[str, bool], *, filename="")`; `_render_template_texts(..., *, conditions, py_cmd)`.

- [ ] **Step 1: Добавить падающие тесты рендера и флагов**

В `app/tests/env/test_content_conditions.py` после `test_render_conditionals_orphan_endif_raises` добавить:

```python
def test_render_conditionals_naparnic_block():
    text = ("до\n<!-- @if 1c_naparnic -->\n\nвнутри\n"
            "<!-- @endif -->\n\nпосле\n")
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": True}, filename="x.md"
    ) == "до\n\nвнутри\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nпосле\n"


def test_conditional_flags_by_enabled_mcp():
    assert content.conditional_flags([]) == {
        "1c-md": False, "1c_naparnic": False}
    assert content.conditional_flags([sel("1c-md")])["1c-md"] is True
    assert content.conditional_flags([sel("1c-md-queries")])["1c-md"] is True
    assert content.conditional_flags([sel("1c-naparnic")]) == {
        "1c-md": False, "1c_naparnic": True}
    assert content.conditional_flags(
        [sel("1c-naparnic", enabled=False)])["1c_naparnic"] is False
```

- [ ] **Step 2: Перевести прямые вызовы рендера на mapping**

В том же файле заменить шесть вызовов `content._render_conditional_blocks(text, True/False, ...)`:

```python
def test_render_conditionals_keeps_block_when_true():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nвнутри\n\nпосле\n"


def test_render_conditionals_drops_block_when_false():
    text = "до\n<!-- @if 1c-md -->\n\nвнутри\n<!-- @endif -->\n\nпосле\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": False}, filename="x.md"
    ) == "до\n\nпосле\n"


def test_render_conditionals_inline_rows():
    text = "| a |\n<!-- @if 1c-md -->\n| b |\n<!-- @endif -->\n| c |\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": False}, filename="x.md"
    ) == "| a |\n| b |\n| c |\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": False, "1c_naparnic": False}, filename="x.md"
    ) == "| a |\n| c |\n"


def test_render_conditionals_without_markers_unchanged():
    text = "обычный текст\n"
    assert content._render_conditional_blocks(
        text, {"1c-md": True, "1c_naparnic": True}, filename="x.md") == text


def test_render_conditionals_unclosed_marker_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "<!-- @if 1c-md -->\nтекст\n",
            {"1c-md": True, "1c_naparnic": True}, filename="x.md")


def test_render_conditionals_orphan_endif_raises():
    with pytest.raises(ValueError, match="x.md"):
        content._render_conditional_blocks(
            "текст\n<!-- @endif -->\n",
            {"1c-md": True, "1c_naparnic": True}, filename="x.md")
```

В `test_template_markers_are_balanced` заменить вызовы:

```python
def test_template_markers_are_balanced():
    for path in content.CONTENT_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        content._render_conditional_blocks(
            text, {"1c-md": True, "1c_naparnic": True}, filename=str(path))
        content._render_conditional_blocks(
            text, {"1c-md": False, "1c_naparnic": False}, filename=str(path))
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py -q
```

Expected: FAIL — `conditional_flags` не существует, рендер не принимает mapping (TypeError).

- [ ] **Step 4: Заменить рендерер условий**

В `app/src/agentmon/env/content.py` заменить функцию `_render_conditional_blocks` целиком на карту, хелпер и рендер:

```python
# Условие шаблона → id MCP-выборов, включающих блок. Новый сервер: добавьте
# строку сюда и поставьте в шаблоне маркер <!-- @if <условие> -->.
_CONDITION_MCP_IDS = {
    "1c-md": ("1c-md", "1c-md-queries"),
    "1c_naparnic": ("1c-naparnic",),
}


def conditional_flags(mcp) -> dict[str, bool]:
    """Какие условные блоки включать — по включённым MCP проекта."""
    enabled = {getattr(sel, "id", None) for sel in mcp
               if getattr(sel, "enabled", False)}
    return {cond: any(mid in enabled for mid in ids)
            for cond, ids in _CONDITION_MCP_IDS.items()}


def _render_conditional_blocks(text: str, conditions: dict[str, bool], *,
                               filename: str = "") -> str:
    """Оставляет/вырезает условные блоки шаблона по составу MCP проекта.

    `conditions` — карта условие→включено (см. conditional_flags).
    Незакрытый, вложенный или лишний маркер — ValueError: маркеры не должны
    попасть в развёрнутый проект.
    """

    def repl(match: re.Match) -> str:
        cond = match.group("cond")
        if cond not in conditions:
            raise ValueError(
                f"неизвестное условие {cond!r} в {filename or '<текст>'}")
        return match.group("body") if conditions[cond] else ""

    rendered = _CONDITIONAL_BLOCK.sub(repl, text)
    if "<!-- @if " in rendered or "<!-- @endif -->" in rendered:
        raise ValueError(
            f"несбалансированный условный блок в {filename or '<текст>'}: "
            "@if/@endif должны быть парными и не вложенными")
    return rendered
```

- [ ] **Step 5: Передать mapping через `_render_template_texts`**

Сигнатуру заменить на:

```python
def _render_template_texts(prov, claude_dir, overrides, *,
                           conditions: dict[str, bool], py_cmd: str) -> None:
```

Вызов рендера заменить на:

```python
        new = _render_conditional_blocks(
            text, conditions, filename=rel.as_posix())
```

В docstring функции `has_1c_md` упоминание заменить на `conditions` (смысл: флаги условий проекта).

- [ ] **Step 6: Считать флаги в `deploy_content`**

В `deploy_content` заменить блок:

```python
    has_1c_md = any(
        getattr(sel, "enabled", False)
        and sel.id in ("1c-md", "1c-md-queries")
        for sel in config.mcp
    )
```

на:

```python
    conditions = conditional_flags(config.mcp)
    has_1c_md = conditions["1c-md"]
```

Вызов в конце заменить на:

```python
    _render_template_texts(prov, claude, subs, conditions=conditions,
                           py_cmd=_py_cmd(prov, project_dir))
```

- [ ] **Step 7: Прогнать тесты контента**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py app/tests/env/test_content_deploy.py app/tests/env/test_content.py app/tests/env/test_content_files.py -q
```

Expected: PASS.

- [ ] **Step 8: Коммит**

```bash
git add app/src/agentmon/env/content.py app/tests/env/test_content_conditions.py
git commit -m "refactor(template): декларативные условия @if по видам MCP"
```

---

### Task 3: Блоки `@if 1c_naparnic` в навыке mcp-usage

**Files:**
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`
- Modify: `app/tests/env/test_content_conditions.py`

**Interfaces:**
- Consumes: `conditional_flags` и mapping-рендер из Task 2; `sel("1c-naparnic")` в тестах.
- Produces: при включённом `1c-naparnic` в развёрнутом `mcp-usage` есть `ask_1c_ai` и `mcp__1c_naparnic__*`; при выключенном/отсутствующем — нет.

- [ ] **Step 1: Добавить падающие тесты деплоя**

В `app/tests/env/test_content_conditions.py` после `test_deploy_disabled_1c_md_has_no_validate_query` добавить:

```python
# --- деплой: 1c_naparnic ---

def test_deploy_1c_naparnic_adds_ask_1c_ai_to_mcp_usage(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("1c-naparnic")]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "ask_1c_ai" in text
    assert "mcp__1c_naparnic__*" in text
    assert "<!-- @if " not in text and "<!-- @endif -->" not in text


def test_deploy_without_1c_naparnic_has_no_ask_1c_ai(tmp_path):
    content.deploy_content(
        LocalProvisioner(), cfg(tmp_path, [sel("bsl-ls")]), update=False)
    assert "ask_1c_ai" not in skill_text(tmp_path, "mcp-usage")


def test_deploy_disabled_1c_naparnic_has_no_ask_1c_ai(tmp_path):
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-naparnic", enabled=False)]), update=False)
    assert "ask_1c_ai" not in skill_text(tmp_path, "mcp-usage")


def test_renamed_1c_naparnic_server_name_substituted(tmp_path):
    conn = '"my_ai": {"type": "http", "url": "http://localhost:8003/mcp"}'
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-naparnic", connection=conn)]), update=False)
    text = skill_text(tmp_path, "mcp-usage")
    assert "mcp__my_ai__*" in text
    assert "mcp__1c_naparnic__*" not in text


def test_no_conditional_markers_leak_with_1c_naparnic(tmp_path):
    content.deploy_content(
        LocalProvisioner(),
        cfg(tmp_path, [sel("1c-md"), sel("1c-naparnic")]), update=False)
    for path in (Path(tmp_path) / ".claude").rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "<!-- @if " not in text, path
        assert "<!-- @endif -->" not in text, path
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py -q
```

Expected: FAIL — в `mcp-usage` нет `ask_1c_ai` и `mcp__1c_naparnic__*`.

- [ ] **Step 3: Добавить строку в таблицу навыка**

В `template/.claude/skills/mcp-usage/SKILL.md` после блока `<!-- @if 1c-md --> … <!-- @endif -->` со строкой `validate_query` и перед строкой `| Статический анализ BSL…` вставить:

```markdown
<!-- @if 1c_naparnic -->
| Ошибка компиляции BSL или непонятная сигнатура метода | `1c_naparnic` | `ask_1c_ai` |
<!-- @endif -->
```

- [ ] **Step 4: Добавить золотое правило**

После правила 5 (`5. **Граница индекса.** … grep`.) и перед пустой строкой с `**Точные имена инструментов**` вставить:

```markdown
<!-- @if 1c_naparnic -->
6. При **любой** ошибке компиляции BSL или непонятной сигнатуре метода — сразу
   `ask_1c_ai`, параллельно с `bsl_ls check` и `1c_platform`; не угадывай по
   памяти.
<!-- @endif -->
```

- [ ] **Step 5: Добавить точное имя инструментов**

После строки `- \`mcp__code_index__*\`; в code-index **нет** \`get_member\` / \`get_members\`;` и перед строкой `- инструмента \`Memory\` нет…` вставить:

```markdown
<!-- @if 1c_naparnic -->
- `mcp__1c_naparnic__*` — **подчёркивание**, не `1c-naparnic`; основной
  инструмент — `ask_1c_ai`.
<!-- @endif -->
```

- [ ] **Step 6: Добавить секцию о сервере**

Заменить фрагмент после блока `1c-md` (от `<!-- @endif -->` до `---` перед `## \`bsl_ls\``) на:

```markdown
<!-- @endif -->

<!-- @if 1c_naparnic -->

---

## `1c_naparnic` — вопросы по 1С (внешний ИИ-ассистент)

MCP-обёртка над 1С:Напарником. Сервер общий, ходит во внешний сервис
`code.1c.ai` (нужен интернет); токен настроен на стороне сервера.

- **`ask_1c_ai`** — вопрос по 1С: ошибки компиляции, непонятные сигнатуры
  методов, поведение платформы и БСП.
- **`explain_1c_syntax`** — объяснение конструкции языка.

**Политика:** при любой ошибке компиляции или ошибке сигнатуры вызывай
`ask_1c_ai` **сразу**, параллельно с `bsl_ls check` и `1c_platform`; не
угадывай по памяти. При расхождении ответа с локальными инструментами решай в
пользу проверяемого источника: версия платформы — из `1c_platform`, код — из
`code_index`.

**Конфиденциальность:** запрос и фрагменты кода уходят во внешний сервис 1С —
не отправляй секреты, пароли и персональные данные без необходимости. Ошибка
авторизации означает неверный/просроченный токен на сервере Напарника.

`check_1c_code` не используется — для проверки кода применяй `bsl_ls`.

<!-- @endif -->

---
```

- [ ] **Step 7: Добавить рецепт**

После блока `<!-- @if 1c-md -->` с рецептом «Проверить синтаксис запроса» и перед рецептом «Проверить написанный код» вставить:

```markdown
<!-- @if 1c_naparnic -->
- **«Ошибка компиляции или сигнатуры»** → `bsl_ls check` + сразу `ask_1c_ai`;
  для проверки самого кода — `bsl_ls`, для объяснения — `ask_1c_ai`.
<!-- @endif -->
```

- [ ] **Step 8: Прогнать тесты контента**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py app/tests/env/test_content_deploy.py app/tests/env/test_content.py app/tests/env/test_content_files.py -q
```

Expected: PASS.

- [ ] **Step 9: Проверить, что маркеры в шаблоне сбалансированы при обоих состояниях**

Run:

```bash
.venv/bin/python -m pytest app/tests/env/test_content_conditions.py::test_template_markers_are_balanced -q
```

Expected: PASS (оба флага true и оба false).

- [ ] **Step 10: Коммит**

```bash
git add template/.claude/skills/mcp-usage/SKILL.md app/tests/env/test_content_conditions.py
git commit -m "feat(template): ask_1c_ai при ошибках компиляции и сигнатур"
```

---

## Финальная проверка

- [ ] **Все затронутые тесты:**

```bash
.venv/bin/python -m pytest app/tests/env/test_bench_setup.py app/tests/env/test_content_conditions.py app/tests/env/test_content_deploy.py app/tests/env/test_content.py app/tests/env/test_content_files.py -q
```

Expected: PASS.

- [ ] **Проверить, что в рабочем дереве нет незакоммиченных изменений:**

```bash
git status --short
```

Expected: пусто (кроме игнорируемых файлов).
