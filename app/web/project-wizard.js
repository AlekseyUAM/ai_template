// Данные MCP: [{id, name, purpose}]
let mcpData = [];
// Выбранные MCP ids (порядок сохраняется)
let mcpSelectedIds = [];

const agentRoles = ["analyst", "architect", "developer-tests", "developer", "reviewer", "technical-writer"];
const agentLabels = {
  analyst: "Аналитик",
  architect: "Архитектор",
  "developer-tests": "Разработчик тестов",
  developer: "Разработчик",
  reviewer: "Ревьюер",
  "technical-writer": "Технический писатель",
};

// Модели/усилие по умолчанию для каждого агента.
// Короткий алиас (haiku/sonnet/opus) → используется последняя модель уровня;
// можно указать и полный id (например, более старую версию: claude-sonnet-4-5).
const agentDefaults = {
  analyst: { model: "claude-opus-4-7", effort: "high" },
  architect: { model: "opus", effort: "high" },
  "developer-tests": { model: "claude-sonnet-4-5", effort: "high" },
  developer: { model: "sonnet", effort: "high" },
  reviewer: { model: "claude-opus-4-7", effort: "high" },
  "technical-writer": { model: "claude-sonnet-4-5", effort: "medium" },
};

// Режим обновления окружения (?id=PID): при сабмите вызываем update-env.
let updateProjectId = null;

// ─── Инициализация (одностраничная форма, без шагов) ─────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  await loadMcp();
  renderAgents();
  setupPlatformAutoVersion();
  setupNameValidation();
  await checkUrlParams();
  loadRequirements();

  // Переключение полей по выбору бэкенда (local / ssh / docker)
  const backendSel = document.getElementById("backend");
  const sshFields = document.getElementById("sshFields");
  const dockerFields = document.getElementById("dockerFields");
  function syncBackend() {
    const v = backendSel.value;
    sshFields.hidden = v !== "ssh";
    dockerFields.hidden = v !== "docker";
    // При переключении на docker предзаполняем пустые поля path и platformDir
    // разумными дефолтами для контейнера. Делаем это только здесь (при смене
    // бэкенда), не при каждом вводе, чтобы не затирать уже введённые значения.
    if (v === "docker") {
      const pathInput = document.getElementById("path");
      const platformDirInput = document.getElementById("platformDir");
      if (!pathInput.value) pathInput.value = "/workspace";
      if (!platformDirInput.value) platformDirInput.value = "/opt/1cv8/current";
    }
  }
  backendSel.addEventListener("change", syncBackend);
  backendSel.addEventListener("change", refreshDistrField);
  document.getElementById("platformVersion")
    ?.addEventListener("change", refreshDistrField);
  syncBackend();
});

// ─── Скачивание расширения юнит-тестов ───────────────────────────────────────

// Отдаёт ЮнитТесты.cfe без ухода со страницы: временный <a download>.
// Файл лежит в статике (app/web/assets); имя с кириллицей кодируем для URL.
function downloadTestExtension() {
  const a = document.createElement("a");
  a.href = "/static/assets/" + encodeURIComponent("ЮнитТесты.cfe");
  a.download = "ЮнитТесты.cfe";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// ─── Живая проверка имени ────────────────────────────────────────────────────

function setupNameValidation() {
  const nameInput = document.getElementById("name");
  nameInput.addEventListener("blur", () => { validateNameField(); });
  nameInput.addEventListener("input", () => {
    document.getElementById("nameError").textContent = "";
  });
}

async function validateNameField() {
  const name = document.getElementById("name").value;
  const errElem = document.getElementById("nameError");
  if (!name) {
    setError("nameError", "Имя обязательно");
    return false;
  }
  try {
    const r = await fetch("/api/env/projects/validate-name", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await r.json();
    if (!data.ok) {
      setError("nameError", data.error || "Некорректное имя");
      return false;
    }
    errElem.textContent = "";
    return true;
  } catch (e) {
    setError("nameError", `Ошибка проверки: ${e.message}`);
    return false;
  }
}

// ─── Требования ───────────────────────────────────────────────────────────────

async function loadRequirements() {
  const container = document.getElementById("requirements");
  if (!container || container.dataset.loaded === "1") return;
  container.dataset.loaded = "1";
  container.textContent = "Проверка требований...";
  try {
    const r = await fetch("/api/env/projects/requirements");
    const data = await r.json();
    const reqs = data.requirements || [];
    container.innerHTML = "<strong>Требования:</strong><br>" + reqs.map(req =>
      `${req.ok ? "✓" : "✗"} ${escapeHtml(req.name)} — ${escapeHtml(req.detail)}`
    ).join("<br>");
  } catch (e) {
    container.textContent = `Не удалось проверить требования: ${e.message}`;
  }
}

// ─── Вспомогательная функция: conn-объект или null ───────────────────────────

function readConn() {
  const backend = document.getElementById("backend").value;
  if (backend === "ssh") {
    return {
      host: document.getElementById("sshHost").value.trim(),
      port: parseInt(document.getElementById("sshPort").value, 10) || 22,
      user: document.getElementById("sshUser").value.trim() || null,
      key_path: document.getElementById("sshKeyPath").value.trim() || null,
    };
  }
  if (backend === "docker") {
    const conn = {};
    const image = document.getElementById("dockerImage").value.trim();
    if (image) conn.image = image;
    const host = document.getElementById("dockerDaemonHost").value.trim();
    if (host) {
      conn.host = host;
      const user = document.getElementById("dockerDaemonUser").value.trim();
      if (user) conn.user = user;
      const port = parseInt(document.getElementById("dockerDaemonPort").value, 10);
      if (port) conn.port = port;
    }
    // {} допустим: image и host необязательны; бэкенд возьмёт дефолт из образа-тулкита
    return conn;
  }
  return null;
}

// ─── Проверка наличия docker-образа (check-image) ────────────────────────────

async function refreshDistrField() {
  const backend = document.getElementById("backend").value;
  const distrFields = document.getElementById("distrFields");
  const platformVersion =
    (document.getElementById("platformVersion")?.value || "").trim();
  if (backend !== "docker" || !platformVersion) {
    distrFields.style.display = "none";
    return;
  }
  try {
    const resp = await fetch("/api/env/projects/check-image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform_version: platformVersion,
        backend: backend,
        conn: readConn(),
      }),
    });
    const data = await resp.json();
    // образа нет → поле обязательно и видимо; есть → прячем
    distrFields.style.display = data.exists ? "none" : "block";
    document.getElementById("distrPath").required = !data.exists;
  } catch (e) {
    // при ошибке проверки показываем поле (безопаснее требовать дистрибутив)
    distrFields.style.display = "block";
  }
}

// ─── Проверка доступа к базе ───────────────────────────────────────────────────

async function checkDb() {
  const logElem = document.getElementById("dbLog");
  logElem.className = "log-output";
  logElem.style.display = "block";
  logElem.style.color = "";

  const platformDir = document.getElementById("platformDir").value.trim();
  if (!platformDir) {
    logElem.textContent = "Сначала заполните поле «Путь к платформе».";
    logElem.style.color = "var(--danger)";
    return;
  }
  logElem.textContent = "Проверка доступа к базе...";
  try {
    const r = await fetch("/api/env/projects/check-db", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform_dir: document.getElementById("platformDir").value,
        db_connection: document.getElementById("dbConnection").value,
        user: document.getElementById("dbUser").value || "",
        password: document.getElementById("dbPassword").value || "",
        backend: document.getElementById("backend").value,
        conn: readConn(),
      }),
    });
    const data = await r.json();
    logElem.innerHTML = `${data.ok ? "✓ Доступ есть" : "✗ Нет доступа"}<br>` +
      escapeHtml(data.log || "").replace(/\n/g, "<br>");
    logElem.style.color = data.ok ? "var(--success)" : "var(--danger)";
  } catch (e) {
    logElem.textContent = `✗ Ошибка: ${e.message}`;
    logElem.style.color = "var(--danger)";
  }
}

// ─── Авто-версия платформы из пути ───────────────────────────────────────────

function setupPlatformAutoVersion() {
  const dirInput = document.getElementById("platformDir");
  const verInput = document.getElementById("platformVersion");
  function tryFillVersion() {
    const m = dirInput.value.match(/(\d+\.\d+\.\d+(?:\.\d+)?)/);
    if (m) {
      verInput.value = m[1];
    }
  }
  dirInput.addEventListener("input", tryFillVersion);
  dirInput.addEventListener("change", tryFillVersion);
}

// ─── MCP ─────────────────────────────────────────────────────────────────────

async function loadMcp() {
  try {
    const r = await fetch("/api/mcp");
    const data = await r.json();
    mcpData = (data.mcp || []).map(m => ({
      id: String(m.id != null ? m.id : m.name),
      name: m.name || m.id,
      purpose: m.purpose || "",
    }));
    renderMcpPicker();
  } catch (e) {
    // тихо: справочник недоступен — picker будет пустым, хинт покажется
    mcpData = [];
    renderMcpPicker();
  }
}

function renderMcpPicker() {
  const pick = document.getElementById("mcpPick");
  const hint = document.getElementById("mcpHint");
  const addBtn = document.getElementById("mcpAddBtn");
  pick.innerHTML = "";
  pick.style.display = "none";

  if (mcpData.length === 0) {
    // справочник пуст — добавлять нечего
    hint.style.display = "";
    addBtn.style.display = "none";
    renderMcpSelected();
    return;
  }

  hint.style.display = "none";
  addBtn.style.display = "";
  const ph = document.createElement("option");
  ph.value = ""; ph.textContent = "— выберите MCP —";
  pick.appendChild(ph);
  for (const m of mcpData) {
    if (mcpSelectedIds.includes(m.id)) continue;   // уже добавлен
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.name + (m.purpose ? ` — ${m.purpose}` : "");
    pick.appendChild(opt);
  }
  renderMcpSelected();
}

// Клик «Добавить» → показать выпадающий список для выбора.
function showMcpPicker() {
  const pick = document.getElementById("mcpPick");
  if (pick.options.length <= 1) {
    alert("Все серверы из справочника уже добавлены");
    return;
  }
  pick.style.display = "";
  pick.value = "";
  pick.focus();
}

// Выбор в выпадающем списке → добавить в список выбранных.
function addMcpFromPicker() {
  const pick = document.getElementById("mcpPick");
  const id = pick.value;
  if (!id || mcpSelectedIds.includes(id)) {
    pick.style.display = "none";
    return;
  }
  mcpSelectedIds.push(id);
  renderMcpPicker();   // перерисовать (исключить добавленный) + список
}

function removeMcp(id) {
  mcpSelectedIds = mcpSelectedIds.filter(x => x !== id);
  renderMcpPicker();
}

function renderMcpSelected() {
  const container = document.getElementById("mcpSelected");
  container.innerHTML = "";
  if (mcpSelectedIds.length === 0) {
    container.innerHTML = `<div class="mcp-list-empty">Пока ничего не выбрано</div>`;
    return;
  }
  for (const id of mcpSelectedIds) {
    const m = mcpData.find(x => x.id === id);
    const label = m ? (m.name + (m.purpose ? ` — ${m.purpose}` : "")) : id;
    const row = document.createElement("div");
    row.className = "mcp-selected-item";
    const span = document.createElement("span");
    span.textContent = label;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.title = "Убрать";
    btn.textContent = "✕";
    btn.addEventListener("click", () => removeMcp(id));
    row.appendChild(span);
    row.appendChild(btn);
    container.appendChild(row);
  }
}

// ─── Агенты ──────────────────────────────────────────────────────────────────

function renderAgents() {
  const container = document.getElementById("agentsGrid");
  container.innerHTML = "";

  for (const role of agentRoles) {
    const def = agentDefaults[role] || { model: "sonnet", effort: "medium" };
    const effortOpts = [
      { value: "low", label: "Low" },
      { value: "medium", label: "Medium" },
      { value: "high", label: "High" },
    ].map(o =>
      `<option value="${o.value}"${o.value === def.effort ? " selected" : ""}>${o.label}</option>`
    ).join("");

    const card = document.createElement("div");
    card.className = "agent-card";
    card.innerHTML = `
      <h3>${agentLabels[role]}</h3>
      <label>
        <span class="label-text">Model</span>
        <input type="text" data-agent-model="${role}" value="${def.model}">
      </label>
      <label>
        <span class="label-text">Effort</span>
        <select data-agent-effort="${role}">${effortOpts}</select>
      </label>
    `;
    container.appendChild(card);
  }
}

// ─── Создать проект ───────────────────────────────────────────────────────────

async function createProject() {
  // Режим обновления окружения проекта
  if (updateProjectId !== null) {
    return updateEnv();
  }
  const body = {
    name: document.getElementById("name").value,
    path: document.getElementById("path").value,
    identifier: document.getElementById("identifier").value,
    email: document.getElementById("email").value,
    platform_dir: document.getElementById("platformDir").value,
    platform_version: document.getElementById("platformVersion").value,
    db_connection: document.getElementById("dbConnection").value,
    user: document.getElementById("dbUser").value || "",
    password: document.getElementById("dbPassword").value || "",
    web_publication: document.getElementById("webPublication").value || "",
    backend: document.getElementById("backend").value,
    license_server: document.getElementById("licenseServer").value || null,
    mcp_ids: [...mcpSelectedIds],
    agents: agentRoles.map(role => ({
      agent: role,
      model: document.querySelector(`input[data-agent-model="${role}"]`).value,
      effort: document.querySelector(`select[data-agent-effort="${role}"]`).value,
    })),
    dump_cf: document.getElementById("dumpCf").checked,
    dump_cfe: document.getElementById("dumpCfe").checked,
    install_tools: document.getElementById("installTools").checked,
    git_init: document.getElementById("gitInit").checked,
    update: false,
  };
  body.distr_path = (document.getElementById("distrPath")?.value || "").trim();
  const conn = readConn();
  if (conn) body.conn = conn;

  const logElem = document.getElementById("createLog");
  logElem.className = "log-output";
  logElem.style.display = "block";
  logElem.style.color = "";
  logElem.textContent = "";

  const createBtn = document.getElementById("createBtn");
  createBtn.disabled = true;
  try {
    // Живой стриминг лога установки — видно каждый шаг по мере выполнения.
    const r = await fetch("/api/env/projects/create/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok || !r.body) {
      let detail = r.statusText;
      try { detail = (await r.json()).detail || detail; } catch (e) {}
      logElem.textContent = `✗ Ошибка: ${detail}`;
      logElem.style.color = "var(--danger)";
      return;
    }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      logElem.textContent += decoder.decode(value, { stream: true });
      logElem.scrollTop = logElem.scrollHeight;
    }
  } catch (e) {
    logElem.textContent += `\n✗ Ошибка: ${e.message}`;
    logElem.style.color = "var(--danger)";
  } finally {
    createBtn.disabled = false;
  }
}

// ─── Обновление версии окружения (?id=) ─────────────────────────────────────

async function updateEnv() {
  const body = {
    dump_cf: document.getElementById("dumpCf").checked,
    dump_cfe: document.getElementById("dumpCfe").checked,
    install_tools: document.getElementById("installTools").checked,
  };

  const logElem = document.getElementById("createLog");
  logElem.className = "log-output";
  logElem.style.display = "block";
  logElem.style.color = "";
  logElem.textContent = "Обновление окружения...";

  const createBtn = document.getElementById("createBtn");
  if (createBtn) createBtn.disabled = true;
  try {
    const r = await fetch(`/api/env/projects/${updateProjectId}/update-env`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (r.status !== 200) {
      const err = await r.json().catch(() => ({}));
      logElem.textContent = `✗ Ошибка: ${err.detail || r.status}`;
      logElem.style.color = "var(--danger)";
      return;
    }

    const data = await r.json();
    let html = `<strong>✓ Окружение обновлено!</strong>\n\nВерсия окружения: ${escapeHtml(data.project.env_version)}\n\nСобытия:\n`;
    for (const evt of (data.events || [])) {
      html += `\n[${escapeHtml(evt.step)}] ${escapeHtml(evt.status)}${evt.detail ? " " + escapeHtml(evt.detail) : ""}`;
    }
    logElem.innerHTML = html.replace(/\n/g, "<br>");
    logElem.style.color = "var(--success)";
  } catch (e) {
    logElem.textContent = `✗ Ошибка: ${e.message}`;
    logElem.style.color = "var(--danger)";
  } finally {
    if (createBtn) createBtn.disabled = false;
  }
}

// ─── Предзаполнение по ?id= ────────────────────────────────────────────────

async function checkUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) return;

  try {
    const r = await fetch(`/api/env/projects/${id}`);
    if (r.status !== 200) return;
    const data = await r.json();
    const p = data.project;
    updateProjectId = id;

    document.getElementById("name").value = p.name || "";
    document.getElementById("path").value = p.path || "";
    document.getElementById("identifier").value = p.identifier || "";
    document.getElementById("email").value = p.email || "";
    document.getElementById("platformDir").value = p.platform_dir || "";
    document.getElementById("platformVersion").value = p.platform_version || "";
    document.getElementById("dbConnection").value = p.db_connection || "";
    document.getElementById("webPublication").value = p.web_publication || "";
    document.getElementById("name").readOnly = true;
    document.getElementById("path").readOnly = true;

    // Best-effort prefill for backend/licenseServer (ssh update-env is a follow-up)
    if (p.backend) document.getElementById("backend").value = p.backend;
    if (p.license_server) document.getElementById("licenseServer").value = p.license_server;

    // Предзаполнить ранее выбранные MCP проекта
    mcpSelectedIds = (p.mcp_ids || []).map(x => String(x));
    renderMcpSelected();

    document.getElementById("createBtn").textContent = "Обновить";

    // При обновлении версии окружения выгрузки cf/cfe и git init не выполняются —
    // прячем эти опции, чтобы не вводить в заблуждение.
    for (const itemId of ["dumpCfItem", "dumpCfeItem", "gitInitItem"]) {
      const el = document.getElementById(itemId);
      if (el) el.style.display = "none";
    }
  } catch (e) {
    console.error("Ошибка загрузки проекта:", e);
  }
}

function setError(elementId, message) {
  const elem = document.getElementById(elementId);
  elem.textContent = message;
  elem.style.color = "var(--danger)";
  elem.style.fontSize = "0.875rem";
  elem.style.marginTop = "4px";
}

function setSuccess(elementId, message) {
  const elem = document.getElementById(elementId);
  elem.textContent = message;
  elem.style.color = "var(--success)";
  elem.style.fontSize = "0.875rem";
  elem.style.marginTop = "4px";
}
