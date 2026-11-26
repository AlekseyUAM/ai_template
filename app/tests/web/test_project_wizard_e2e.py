"""E2E: создание проекта из tmp/project.md через мастер /project-wizard.

Запуск (нужны живой AgentMon, установленный Chromium и работоспособная
платформа 1С — мастер реально выполняет установку окружения):

    .venv/bin/python -m playwright install chromium   # один раз
    AGENTMON_E2E=1 .venv/bin/python -m pytest \\
        app/tests/web/test_project_wizard_e2e.py -m e2e -q

Без AGENTMON_E2E=1 модуль скипается: обычный pytest не создаёт проектов и
не требует браузера.

Создание настоящее (venv, выгрузки cf/cfe, инструменты), поэтому тест идёт
минуты: ожидание журнала ограничено AGENTMON_E2E_CREATE_TIMEOUT секундами
(по умолчанию 1800). При сбое установки AgentMon откатывает запись проекта,
но каталог на диске остаётся заполненным — перед повторным прогоном его
нужно очистить. На уже созданном проекте тест скипается; для повторяемого
прогона задайте оба: AGENTMON_E2E_PROJECT_NAME и AGENTMON_E2E_PROJECT_PATH
(каталог должен быть пустым).

Проверяется:
1. tmp/project.md парсится в поля мастера (бэкенд, пути, БД, MCP по именам,
   code index, галочки выгрузок); прочие параметры остаются по умолчанию.
2. Тело POST /api/env/projects/create/stream, которое собирает мастер, совпадает
   с данными файла; пути code index предзаполняются от каталога проекта.
3. Журнал создания заканчивается «✓ Проект создан».
4. Проект и привязанные MCP видны в API и на странице «Проекты»; окружение на
   диске: .claude/VERSION, .mcp.json, .1c-devbase.json, git, выгрузка src/cf.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest

if os.environ.get("AGENTMON_E2E") != "1":
    pytest.skip("e2e: включите AGENTMON_E2E=1", allow_module_level=True)

pytestmark = pytest.mark.e2e

sync_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PROJECT_MD = ROOT / "tmp" / "project.md"
BASE_URL = os.environ.get("AGENTMON_URL", "http://127.0.0.1:8765").rstrip("/")
TIMEOUT_MS = 15000
CREATE_TIMEOUT = float(os.environ.get("AGENTMON_E2E_CREATE_TIMEOUT", "1800"))
# Финальные маркеры журнала создания: успех — «✓ Проект создан»,
# сбой — строка, начинающаяся с «✗» (шаговые строки идут как «[шаг] ...»).
_FAIL_MARK = re.compile(r"^✗", re.MULTILINE)


# ── клиент живого AgentMon ────────────────────────────────────────────────────


class Api:
    """Минимальный HTTP-клиент; токен — из AGENTMON_TOKEN, если он задан."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def request(self, method: str, path: str, body=None, **params):
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        token = os.environ.get("AGENTMON_TOKEN")
        if token:
            req.add_header("X-Agentmon-Token", token)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise AssertionError(
                f"{method} {path} → HTTP {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else {}

    def get(self, path: str, **params):
        return self.request("GET", path, **params)

    def post(self, path: str, body=None):
        return self.request("POST", path, body if body is not None else {})


def _ui_url(path: str) -> str:
    """URL страницы; при заданном AGENTMON_TOKEN отдаём его auth.js в ?token=."""
    token = os.environ.get("AGENTMON_TOKEN")
    if not token:
        return BASE_URL + path
    sep = "&" if "?" in path else "?"
    return BASE_URL + path + sep + "token=" + quote(token)


# ── разбор tmp/project.md ─────────────────────────────────────────────────────

_BACKEND_ALIASES = {
    "локально": "local",
    "local": "local",
    "удалённо (ssh)": "ssh",
    "ssh": "ssh",
    "в docker-контейнере": "docker",
    "docker": "docker",
}
_REQUIRED_KEYS = ("Бэкенд", "ИмяПроекта", "КаталогПроекта", "Идентификатор",
                  "Email", "ПутьКПлатформе", "ВерсияПлатформы",
                  "СтрокаПодключения", "Пользователь")


def _yes(value: str) -> bool:
    return value.strip().lower() in ("да", "yes", "true", "1")


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_project_md(path: Path) -> dict:
    """Поля мастера из файла вида `Ключ=Значение`."""
    assert path.is_file(), f"нет файла с данными проекта: {path}"
    text = path.read_text(encoding="utf-8")

    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip()

    missing = [key for key in _REQUIRED_KEYS if not fields.get(key)]
    assert not missing, f"в {path} не заданы обязательные поля: {missing}"

    backend = _BACKEND_ALIASES.get(fields["Бэкенд"].strip().lower())
    assert backend, (f"неизвестный бэкенд {fields['Бэкенд']!r}; "
                     f"ожидается один из {sorted(_BACKEND_ALIASES)}")

    name_override = (os.environ.get("AGENTMON_E2E_PROJECT_NAME") or "").strip()
    path_override = (os.environ.get("AGENTMON_E2E_PROJECT_PATH") or "").strip()
    assert bool(name_override) == bool(path_override), (
        "задайте оба параметра или ни одного: "
        "AGENTMON_E2E_PROJECT_NAME и AGENTMON_E2E_PROJECT_PATH")

    return {
        "backend": backend,
        "name": name_override or fields["ИмяПроекта"],
        "path": path_override or fields["КаталогПроекта"],
        "identifier": fields["Идентификатор"],
        "email": fields["Email"],
        "platform_dir": fields["ПутьКПлатформе"],
        "platform_version": fields["ВерсияПлатформы"],
        "db_connection": fields["СтрокаПодключения"],
        "db_user": fields["Пользователь"],
        "db_password": fields.get("Пароль", ""),
        "code_index": _yes(fields.get("code_index", "")),
        "mcp_names": _split_list(fields.get("MCP", "")),
        "dump_cf": _yes(fields.get("ВыгрузитьCF", "")),
        "dump_cfe": _yes(fields.get("ВыгрузитьCFE", "")),
    }


def _code_index_paths(project_path: str) -> tuple[str, str]:
    """Пути code index, которые предзаполняет мастер (local, POSIX)."""
    base = project_path.replace("\\", "/").rstrip("/")
    return f"{base}/src/cf", f"{base}-code-index"


def _template_version() -> str:
    version = ROOT / "template" / ".claude" / "VERSION"
    return version.read_text(encoding="utf-8").strip()


def _expected_devbase_connection(db_connection: str) -> dict | None:
    """Ожидаемая секция connection в .1c-devbase.json (только серверная база)."""
    pairs: dict[str, str] = {}
    for part in db_connection.split(";"):
        key, sep, value = part.partition("=")
        if sep:
            pairs[key.strip().lower()] = value.strip()
    if "srvr" in pairs or "ref" in pairs:
        return {"type": "server", "server": pairs.get("srvr", ""),
                "base": pairs.get("ref", "")}
    return None


def _server_key(card: dict) -> str:
    """Ключ сервера в .mcp.json: имя из фрагмента connection карточки MCP."""
    entry = json.loads("{" + (card.get("connection_json") or "") + "}")
    assert isinstance(entry, dict) and len(entry) == 1, card
    return next(iter(entry))


# ── фикстуры ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def api() -> Api:
    client = Api(BASE_URL)
    try:
        client.get("/api/env/projects")
    except Exception as exc:  # noqa: BLE001 — нужен читаемый фейл
        pytest.fail(f"AgentMon недоступен на {BASE_URL}: {exc}")
    return client


@pytest.fixture(scope="module")
def browser():
    headed = os.environ.get("AGENTMON_E2E_HEADED") == "1"
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    yield page
    page.close()


# ── шаги сценария ─────────────────────────────────────────────────────────────


def _existing_project(api: Api, spec: dict) -> dict | None:
    for project in api.get("/api/env/projects").get("projects", []):
        if (project.get("name") == spec["name"]
                or project.get("path") == spec["path"]):
            return project
    return None


def _resolve_mcps(api: Api, names: list[str]) -> list[dict]:
    """Карточки справочника MCP по именам из файла (порядок сохраняется)."""
    catalog = api.get("/api/mcp").get("mcp", [])
    by_name = {(row.get("name") or "").strip(): row for row in catalog}
    missing = [name for name in names if name not in by_name]
    assert not missing, (
        f"MCP не найдены в справочнике: {missing}; "
        f"доступны: {sorted(by_name)}")
    return [by_name[name] for name in names]


def _wait_wizard_ready(page) -> None:
    # Справочник MCP грузится асинхронно (loadMcp → renderMcpPicker).
    page.wait_for_function(
        """() => {
            const add = document.getElementById('mcpAddBtn');
            const hint = document.getElementById('mcpHint');
            return (add && add.style.display !== 'none')
                || (hint && hint.style.display === '');
        }""")
    assert page.locator("#mcpAddBtn").is_visible(), (
        "справочник MCP пуст — добавьте серверы на странице «MCP-серверы»")


def _fill_wizard(page, spec: dict, cards: list[dict]) -> dict:
    """Заполняет мастер по данным файла; возвращает нетронутые «по умолчанию»."""
    page.goto(_ui_url("/project-wizard"))
    _wait_wizard_ready(page)

    page.select_option("#backend", value=spec["backend"])
    page.fill("#name", spec["name"])
    page.fill("#path", spec["path"])
    page.fill("#identifier", spec["identifier"])
    page.fill("#email", spec["email"])
    # Путь к платформе сам подставляет версию, но фиксируем значение из файла.
    page.fill("#platformDir", spec["platform_dir"])
    page.fill("#platformVersion", spec["platform_version"])
    page.fill("#dbConnection", spec["db_connection"])
    page.fill("#dbUser", spec["db_user"])
    page.fill("#dbPassword", spec["db_password"])
    page.locator("#codeIndexEnabled").set_checked(spec["code_index"])
    page.locator("#dumpCf").set_checked(spec["dump_cf"])
    page.locator("#dumpCfe").set_checked(spec["dump_cfe"])

    expected_inputs = {
        "#backend": spec["backend"],
        "#name": spec["name"],
        "#path": spec["path"],
        "#identifier": spec["identifier"],
        "#email": spec["email"],
        "#platformDir": spec["platform_dir"],
        "#platformVersion": spec["platform_version"],
        "#dbConnection": spec["db_connection"],
        "#dbUser": spec["db_user"],
        "#dbPassword": spec["db_password"],
    }
    for selector, value in expected_inputs.items():
        assert page.input_value(selector) == value, (
            f"{selector}: {page.input_value(selector)!r} != {value!r}")
    assert page.is_checked("#codeIndexEnabled") == spec["code_index"]
    assert page.is_checked("#dumpCf") == spec["dump_cf"]
    assert page.is_checked("#dumpCfe") == spec["dump_cfe"]

    if spec["code_index"]:
        expect(page.locator("#codeIndexFields")).to_be_visible()
        catalog_dir, ci_dir = _code_index_paths(spec["path"])
        assert page.input_value("#codeIndexCatalogDir") == catalog_dir, (
            "мастер не предзаполнил каталог кодовой базы")
        assert page.input_value("#codeIndexDir") == ci_dir, (
            "мастер не предзаполнил каталог code_index")

    for card in cards:
        page.click("#mcpAddBtn")
        pick = page.locator("#mcpPick")
        expect(pick).to_be_visible()
        pick.select_option(value=str(card["id"]))
        expect(pick).to_be_hidden()
    expect(page.locator("#mcpSelected .mcp-selected-item")).to_have_count(
        len(cards))
    selected = page.locator("#mcpSelected").inner_text()
    for name in spec["mcp_names"]:
        assert name in selected, (
            f"MCP {name!r} не показан среди выбранных: {selected!r}")

    # «Остальные параметры — по умолчанию»: не трогаем, но проверяем, что
    # мастер отправит именно то состояние, которое видит пользователь.
    return {
        "install_tools": page.is_checked("#installTools"),
        "git_init": page.is_checked("#gitInit"),
    }


def _assert_create_body(body: dict, spec: dict, cards: list[dict],
                        defaults: dict) -> None:
    expected = {
        "name": spec["name"],
        "path": spec["path"],
        "identifier": spec["identifier"],
        "email": spec["email"],
        "platform_dir": spec["platform_dir"],
        "platform_version": spec["platform_version"],
        "db_connection": spec["db_connection"],
        "user": spec["db_user"],
        "password": spec["db_password"],
        "backend": spec["backend"],
        "web_publication": "",
        "license_server": None,
        "update": False,
    }
    for field, value in expected.items():
        assert body.get(field) == value, (
            f"поле {field}: {body.get(field)!r} != {value!r}")
    # Мастер шлёт id из справочника строками (String(m.id)).
    assert body.get("mcp_ids") == [str(card["id"]) for card in cards], (
        body.get("mcp_ids"))
    ci = body.get("code_index") or {}
    assert ci.get("enabled") is spec["code_index"], ci
    if spec["code_index"]:
        catalog_dir, ci_dir = _code_index_paths(spec["path"])
        assert ci.get("catalog_dir") == catalog_dir, ci
        assert ci.get("code_index_dir") == ci_dir, ci
    assert body.get("dump_cf") is spec["dump_cf"]
    assert body.get("dump_cfe") is spec["dump_cfe"]
    assert body.get("install_tools") is defaults["install_tools"]
    assert body.get("git_init") is defaults["git_init"]
    # local: readConn() возвращает null, conn в тело не попадает.
    assert "conn" not in body, body.get("conn")


def _wait_create_finished(page) -> str:
    """Ждёт финального маркера журнала; при ошибке падает с хвостом журнала."""
    log = page.locator("#createLog")
    deadline = time.time() + CREATE_TIMEOUT
    text = ""
    while time.time() < deadline:
        text = log.inner_text()
        if "✓ Проект создан" in text:
            return text
        if _FAIL_MARK.search(text):
            raise AssertionError(
                "создание проекта завершилось ошибкой:\n" + text[-4000:])
        page.wait_for_timeout(500)
    raise AssertionError(
        f"журнал создания не завершился за {CREATE_TIMEOUT:.0f} с:\n"
        + text[-4000:])


def _assert_project_api(api: Api, spec: dict) -> dict:
    projects = api.get("/api/env/projects").get("projects", [])
    matches = [p for p in projects if p.get("name") == spec["name"]]
    assert matches, (
        f"проект {spec['name']!r} не появился в API; "
        f"доступны: {[p.get('name') for p in projects]}")
    project = matches[0]
    assert project.get("path") == spec["path"]
    assert (project.get("identifier") or "") == spec["identifier"]
    assert (project.get("email") or "") == spec["email"]
    assert project.get("platform_dir") == spec["platform_dir"]
    assert project.get("platform_version") == spec["platform_version"]
    assert project.get("db_connection") == spec["db_connection"]
    assert project.get("db_kind") == "server", project.get("db_kind")
    assert (project.get("env_version") or "").strip() == _template_version(), (
        project.get("env_version"))
    return project


def _assert_project_links(api: Api, pid: int, spec: dict,
                          cards: list[dict]) -> dict | None:
    """Выбранные MCP и карточка code index привязаны к проекту."""
    detail = api.get(f"/api/env/projects/{pid}")["project"]
    linked = {int(x) for x in detail.get("mcp_ids") or []}
    catalog = {int(row["id"]): row for row in api.get("/api/mcp").get("mcp", [])}

    for card in cards:
        assert int(card["id"]) in linked, (
            f"MCP {card['name']!r} (id={card['id']}) не привязан к проекту; "
            f"привязаны: {sorted(linked)}")

    if not spec["code_index"]:
        return None
    ci_cards = [
        row for mid, row in catalog.items()
        if mid in linked
        and row.get("standard_key") == "code-index"
        and (row.get("project_name") or "") == spec["name"]
    ]
    assert ci_cards, (
        f"к проекту не привязан code-index MCP (привязаны: {sorted(linked)})")
    card = ci_cards[0]
    catalog_dir, ci_dir = _code_index_paths(spec["path"])
    assert Path(card["catalog_dir"]).resolve() == Path(catalog_dir).resolve(), (
        card["catalog_dir"])
    assert Path(card["code_index_dir"]).resolve() == Path(ci_dir).resolve(), (
        card["code_index_dir"])
    return card


def _assert_project_files(spec: dict, cards: list[dict],
                          ci_card: dict | None) -> None:
    base = Path(spec["path"])
    assert (base / ".claude" / "VERSION").read_text(
        encoding="utf-8").strip() == _template_version()
    for rel in (".claude/settings.json", ".git/HEAD", ".mcp.json",
                ".1c-devbase.json", "CLAUDE.md", "README.md",
                "setup-venv.py"):
        assert (base / rel).is_file(), f"нет {base / rel}"

    devbase = json.loads((base / ".1c-devbase.json").read_text(encoding="utf-8"))
    expected_conn = _expected_devbase_connection(spec["db_connection"])
    if expected_conn is not None:
        assert devbase.get("connection") == expected_conn, devbase.get("connection")
    assert devbase.get("user") == spec["db_user"]
    assert devbase.get("password") == spec["db_password"]
    assert devbase.get("cf_dir") == "src/cf"
    assert devbase.get("cfe_dir") == "src/cfe"

    servers = json.loads(
        (base / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}
    expected_servers = {_server_key(card) for card in cards}
    if ci_card is not None:
        expected_servers.add(_server_key(ci_card))
    missing = expected_servers - set(servers)
    assert not missing, (
        f"в .mcp.json нет серверов {sorted(missing)}: {sorted(servers)}")
    ref = (expected_conn or {}).get("base")
    if ref:
        # MCP «метаданные http» из файла смотрит на базу проекта.
        assert ref in json.dumps(servers, ensure_ascii=False), servers

    dumped = [p for p in (base / "src" / "cf").rglob("*")
              if p.is_file() and p.name != ".gitkeep"]
    assert dumped, f"каталог выгрузки {base / 'src' / 'cf'} пуст"


# ── тест ──────────────────────────────────────────────────────────────────────


def test_project_from_md_via_wizard(api: Api, page) -> None:
    spec = parse_project_md(PROJECT_MD)
    assert spec["backend"] == "local", (
        f"мастер-тест рассчитан на Бэкенд=Локально, в файле: {spec['backend']}")

    existing = _existing_project(api, spec)
    if existing is not None:
        pytest.skip(
            f"проект уже создан: id={existing.get('id')}, "
            f"{existing.get('name')} ({existing.get('path')}). "
            "Удалите его или задайте оба параметра "
            "AGENTMON_E2E_PROJECT_NAME / AGENTMON_E2E_PROJECT_PATH")

    cards = _resolve_mcps(api, spec["mcp_names"])
    log_text = ""
    try:
        defaults = _fill_wizard(page, spec, cards)
        with page.expect_request(
                lambda req: req.method == "POST"
                and req.url.endswith("/api/env/projects/create/stream"),
                timeout=TIMEOUT_MS) as request_info:
            page.click("#createBtn")
        body = json.loads(request_info.value.post_data or "{}")
        _assert_create_body(body, spec, cards, defaults)

        log_text = _wait_create_finished(page)
        print("\n[e2e] журнал создания (хвост):\n"
              + "\n".join(log_text.splitlines()[-8:]))

        project = _assert_project_api(api, spec)
        ci_card = _assert_project_links(api, project["id"], spec, cards)
        _assert_project_files(spec, cards, ci_card)

        page.goto(_ui_url("/projects"))
        expect(page.locator("#projectsTable")).to_contain_text(spec["name"])
    except Exception:
        shot = ROOT / "tmp" / f"e2e-project-wizard-{int(time.time())}.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
            print(f"\n[e2e] скриншот падения: {shot}")
        except Exception:  # noqa: BLE001
            pass
        if log_text:
            print("\n[e2e] журнал создания (хвост):\n"
                  + "\n".join(log_text.splitlines()[-20:]))
        raise
