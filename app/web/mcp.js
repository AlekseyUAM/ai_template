document.addEventListener("DOMContentLoaded", initialize);

let allMcps = [];
let mcpTypes = [];

const FIELD_LABELS = {
  name: "Наименование",
  mcp_name: "Имя в .mcp.json",
  purpose: "Назначение",
  url: "URL",
  db_name: "Имя базы",
  port: "Порт",
  token: "Токен",
  catalog_dir: "Каталог кодовой базы",
  platform_path: "Путь к платформе",
  connection: "Подключение",
};

async function initialize() {
  await loadTypes();
  await loadMcp();
  initFormHandlers();
}

async function loadTypes() {
  try {
    const res = await fetch("/api/mcp/types");
    const data = await res.json();
    mcpTypes = data.types || [];
    const sel = document.getElementById("mcp-kind");
    sel.innerHTML = "";
    mcpTypes.forEach((t) => {
      const o = document.createElement("option");
      o.value = t.key;
      o.textContent = t.title;
      sel.appendChild(o);
    });
  } catch (e) {
    console.error("Ошибка загрузки видов MCP:", e.message);
  }
}

async function loadMcp() {
  const tableView = document.getElementById("tableView");
  try {
    const res = await fetch("/api/mcp");
    const data = await res.json();
    allMcps = data.mcp || [];

    if (allMcps.length === 0) {
      tableView.innerHTML = `
        <div class="empty-state">
          <h2>Нет добавленных MCP</h2>
          <p>Добавьте новый MCP, чтобы начать работу</p>
        </div>
      `;
      return;
    }

    // Таблицу перестраиваем целиком: empty-state мог удалить прежнюю разметку.
    const rows = allMcps
      .map(
        (mcp) => `
        <tr onclick="showMcpCard(${mcp.id})">
          <td>${escapeHtml(mcp.name) || "(без названия)"}</td>
          <td>${escapeHtml(mcp.purpose) || "—"}</td>
        </tr>`
      )
      .join("");
    tableView.innerHTML = `
      <table>
        <thead><tr><th>Наименование</th><th>Назначение</th></tr></thead>
        <tbody id="mcpTable">${rows}</tbody>
      </table>`;
  } catch (e) {
    tableView.textContent = `Ошибка загрузки: ${e.message}`;
  }
}

function initFormHandlers() {
  document.getElementById("addBtn").addEventListener("click", () => {
    const form = document.getElementById("add-form");
    // Надёжный тоггл: открываем при любом текущем состоянии (инлайн/CSS).
    const hidden = form.style.display === "none" || form.style.display === "";
    form.style.display = hidden ? "block" : "none";
    if (hidden) resetAddForm();
  });

  document.getElementById("mcp-kind").addEventListener("change", renderTypeFields);

  document.getElementById("add-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await submitAddForm();
  });
}

function currentType() {
  const key = document.getElementById("mcp-kind").value;
  return mcpTypes.find((t) => t.key === key);
}

// Подпись поля: сначала пер-типовое переопределение, затем глобальное, затем ключ.
function labelFor(t, f) {
  return (t && t.field_labels && t.field_labels[f]) || FIELD_LABELS[f] || f;
}

function renderTypeFields() {
  const t = currentType();
  const box = document.getElementById("type-fields");
  const action = document.getElementById("type-action");
  box.innerHTML = "";
  if (action) action.innerHTML = "";
  if (!t) return;
  for (const f of t.fields) {
    box.appendChild(renderField(f, t));
  }
  recomputeConnection();
  // Доп. кнопка действия вида — сохраняет элемент и выполняет действие.
  if (action) {
    if (t.action === "docker") {
      action.innerHTML =
        `<button type="button" onclick="deployFromForm()">Развернуть в Docker локально</button>`;
    } else if (t.action === "cfe") {
      action.innerHTML =
        `<button type="button" onclick="downloadFromForm()">Скачать cfe</button>`;
    }
  }
}

// Скачивает cfe без ухода со страницы/закрытия карточки: временный <a download>.
function downloadCfe(id) {
  const a = document.createElement("a");
  a.href = "/api/mcp/" + id + "/download";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function renderField(f, t) {
  const group = document.createElement("div");
  group.className = "form-group";

  const label = document.createElement("label");
  const req = f === "name" || (t.required || []).includes(f);
  // Обязательные поля — красная звёздочка (span.required), как на других страницах.
  label.innerHTML = labelFor(t, f) + (req ? ' <span class="required"></span>' : "");
  group.appendChild(label);

  let input;
  if (f === "purpose" || f === "connection") {
    input = document.createElement("textarea");
    if (f === "purpose") input.classList.add("purpose-field");
  } else {
    input = document.createElement("input");
    input.type = f === "port" ? "number" : f === "token" ? "password" : "text";
  }
  input.id = "field-" + f;

  const def = t.defaults || {};
  if (f === "connection") {
    input.value = fillTemplate(t);
  } else if (def[f] !== undefined && def[f] !== null) {
    input.value = def[f];
  }

  // Поле «Подключение» формируется автоматически при изменении этих полей.
  if (["mcp_name", "url", "port", "db_name"].includes(f)) {
    input.addEventListener("input", recomputeConnection);
  }

  group.appendChild(input);
  return group;
}

function fieldVal(f) {
  const el = document.getElementById("field-" + f);
  return el ? el.value : undefined;
}

function fillTemplate(t) {
  const def = t.defaults || {};
  const name = fieldVal("mcp_name") || def.mcp_name || "name";
  const url = fieldVal("url") || def.url || "localhost";
  const port = fieldVal("port") || def.port || "";
  const db_name = fieldVal("db_name") || def.db_name || "my_database";
  return (t.connection_template || "")
    .replace(/\{mcp_name\}/g, name)
    .replace(/\{url\}/g, url)
    .replace(/\{port\}/g, port)
    .replace(/\{db_name\}/g, db_name);
}

function recomputeConnection() {
  const t = currentType();
  if (!t) return;
  const conn = document.getElementById("field-connection");
  if (conn) conn.value = fillTemplate(t);
}

// Собирает и сохраняет MCP из формы; возвращает id нового элемента или null.
async function createMcp() {
  const t = currentType();
  if (!t) return null;

  const name = (fieldVal("name") || "").trim();
  if (!name) {
    alert("Укажите наименование MCP");
    return null;
  }
  for (const r of t.required || []) {
    if (!(fieldVal(r) || "").trim()) {
      alert("Заполните обязательное поле: " + labelFor(t, r));
      return null;
    }
  }

  const kind =
    t.action === "cfe" ? "extension" : t.action === "docker" ? "docker" : "custom";
  const body = { name, standard_key: t.key, kind };

  if (t.fields.includes("purpose")) body.purpose = fieldVal("purpose") || "";
  if (t.fields.includes("mcp_name")) body.mcp_name = fieldVal("mcp_name") || null;
  if (t.fields.includes("url")) body.url = fieldVal("url") || null;
  if (t.fields.includes("db_name")) body.db_name = fieldVal("db_name") || null;
  if (t.fields.includes("port")) {
    const p = fieldVal("port");
    if (p) body.port = parseInt(p);
  }
  if (t.fields.includes("token")) body.token_env = fieldVal("token") || null;
  if (t.fields.includes("catalog_dir")) body.catalog_dir = fieldVal("catalog_dir") || null;
  if (t.fields.includes("platform_path")) body.platform_path = fieldVal("platform_path") || null;
  body.connection_json = fieldVal("connection") || null;

  try {
    const res = await fetch("/api/mcp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(`Ошибка добавления: ${data.detail || res.statusText}`);
      return null;
    }
    return (await res.json()).mcp.id;
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
    return null;
  }
}

async function submitAddForm() {
  const id = await createMcp();
  if (id == null) return;
  hideAddForm();
  await loadMcp();
}

// Кнопка «Развернуть в Docker локально» в форме: сохранить элемент, затем развернуть.
async function deployFromForm() {
  const id = await createMcp();
  if (id == null) return;
  hideAddForm();
  await loadMcp();
  await streamLaunch(id, {}); // порт/токен/каталог берутся из сохранённого элемента
}

// Кнопка «Скачать cfe» в форме: сохранить элемент, показать его карточку и
// скачать расширение — без ухода со страницы и без закрытия элемента.
async function downloadFromForm() {
  const id = await createMcp();
  if (id == null) return;
  hideAddForm();
  await loadMcp();
  await showMcpCard(id);
  downloadCfe(id);
}

function resetAddForm() {
  const sel = document.getElementById("mcp-kind");
  if (sel.options.length) sel.value = sel.options[0].value; // Произвольный
  renderTypeFields();
}

function hideAddForm() {
  document.getElementById("add-form").style.display = "none";
}

async function showMcpCard(mcpId) {
  const mcp = allMcps.find((m) => m.id === mcpId);
  if (!mcp) return;

  const cardPanel = document.getElementById("cardPanel");
  const tableView = document.getElementById("tableView");
  const type = mcpTypes.find((t) => t.key === mcp.standard_key);

  // Подпись URL — из пер-типовых переопределений вида (метаданные → «URL хоста»).
  const urlLabel = labelFor(type, "url");

  const fieldsHtml = [
    cardField("Наименование", mcp.name),
    mcp.mcp_name ? cardField("Имя в .mcp.json", mcp.mcp_name) : "",
    cardField("Назначение", mcp.purpose),
    mcp.url ? cardField(urlLabel, mcp.url) : "",
    mcp.db_name ? cardField("Имя базы", mcp.db_name) : "",
    mcp.port ? cardField("Порт", mcp.port) : "",
    mcp.token_env ? cardField("Токен", "••••••") : "",
    mcp.catalog_dir ? cardField("Каталог кодовой базы", mcp.catalog_dir) : "",
    mcp.platform_path ? cardField("Путь к платформе", mcp.platform_path) : "",
    mcp.connection_json ? cardField("Подключение", mcp.connection_json, true) : "",
  ].join("");

  // В карточке — без редактируемых полей; действия берут параметры из элемента.
  let controlsHtml = "";
  const isCfe = (type && type.has_cfe) || mcp.kind === "extension";
  const isDocker = (type && type.action === "docker") || mcp.kind === "docker";

  if (isCfe) {
    controlsHtml = `<button type="button" onclick="downloadCfe('${mcp.id}')">Скачать cfe</button>`;
  } else if (isDocker) {
    controlsHtml = `<button type="button" onclick="launchMcp('${mcp.id}')">Развернуть в Docker локально</button>`;
  }

  cardPanel.innerHTML = `
    <div class="mcp-card-panel">
      <div class="card-header">
        <h2>${escapeHtml(mcp.name) || "(без названия)"}</h2>
        <a href="#" class="back-link" onclick="hideMcpCard(event)">← Назад</a>
      </div>
      ${fieldsHtml}
      <div class="card-controls">
        ${controlsHtml}
        <button type="button" onclick="deleteMcp('${mcp.id}')">Удалить</button>
      </div>
    </div>
  `;

  tableView.style.display = "none";
  cardPanel.style.display = "block";
}

function cardField(label, value, mono) {
  return `
    <div class="card-field">
      <span class="card-label">${label}</span>
      <div class="card-value${mono ? " monospace" : ""}">${escapeHtml(value) || "—"}</div>
    </div>
  `;
}

function hideMcpCard(event) {
  if (event && event.preventDefault) event.preventDefault();
  document.getElementById("cardPanel").style.display = "none";
  document.getElementById("tableView").style.display = "block";
}

// Живой стриминг лога сборки образа и запуска контейнера в панель лога.
async function streamLaunch(mcpId, body) {
  const el = document.getElementById("log-text");
  el.textContent = "";
  const panel = document.getElementById("log-output");
  panel.style.display = "block";
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const res = await fetch(`/api/mcp/${mcpId}/launch/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok || !res.body) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail || detail;
      } catch (e) {}
      el.textContent += `Ошибка: ${detail}\n`;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      el.textContent += decoder.decode(value, { stream: true });
      el.scrollTop = el.scrollHeight;
    }
  } catch (e) {
    el.textContent += `\nОшибка: ${e.message}\n`;
  } finally {
    loadMcp();
  }
}

async function launchMcp(mcpId) {
  // Порт/токен и прочие параметры берутся из сохранённого элемента на сервере.
  const btns = document.querySelectorAll(".card-controls button");
  btns.forEach((b) => (b.disabled = true));
  try {
    await streamLaunch(mcpId, {});
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

async function deleteMcp(mcpId) {
  if (!confirm("Удалить MCP?")) return;
  const res = await fetch(`/api/mcp/${mcpId}`, { method: "DELETE" });
  if (res.ok) {
    loadMcp();
    hideMcpCard();
  } else {
    alert("Ошибка удаления MCP");
  }
}

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
