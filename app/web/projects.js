document.addEventListener("DOMContentLoaded", loadProjects);

let allProjects = [];

async function loadProjects() {
  try {
    const r = await fetch("/api/env/projects");
    const data = await r.json();
    allProjects = data.projects || [];

    const tbody = document.getElementById("projectsTable");
    const tableView = document.getElementById("tableView");

    if (allProjects.length === 0) {
      tableView.innerHTML = `
        <div class="empty-state">
          <h2>Нет проектов</h2>
          <p>Создайте новый проект, чтобы начать работу</p>
        </div>
      `;
      return;
    }

    tbody.innerHTML = "";
    for (const proj of allProjects) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(proj.name) || "(без названия)"}</td>
        <td class="path-cell">${escapeHtml(proj.path) || "-"}</td>
      `;
      tr.onclick = () => showProjectCard(proj.id);
      tbody.appendChild(tr);
    }
  } catch (e) {
    document.getElementById("tableView").textContent = `Ошибка загрузки: ${e.message}`;
  }
}

async function showProjectCard(projectId) {
  try {
    const r = await fetch(`/api/env/projects/${projectId}`);
    const data = await r.json();
    const project = data.project;

    const cardPanel = document.getElementById("cardPanel");
    const tableView = document.getElementById("tableView");

    cardPanel.innerHTML = `
      <div class="project-card-panel">
        <div class="card-header">
          <h2>${escapeHtml(project.name) || "(без названия)"}</h2>
          <a href="#" class="back-link" onclick="hideProjectCard(event)">← Назад</a>
        </div>
        <div class="card-field">
          <span class="card-label">Имя</span>
          <div class="card-value">${escapeHtml(project.name) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Каталог</span>
          <div class="card-value monospace">${escapeHtml(project.path) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Версия окружения</span>
          <div class="card-value">${escapeHtml(project.env_version) || "-"}</div>
        </div>
        <div class="card-controls">
          <button type="button" onclick="updateProjectEnv(${projectId})">
            Обновить версию окружения
          </button>
          <button type="button" onclick="deleteProject(${projectId})">Удалить</button>
        </div>
      </div>
    `;

    tableView.style.display = "none";
    cardPanel.style.display = "block";
  } catch (e) {
    alert(`Ошибка загрузки проекта: ${e.message}`);
  }
}

function hideProjectCard(event) {
  event.preventDefault();
  const cardPanel = document.getElementById("cardPanel");
  const tableView = document.getElementById("tableView");
  cardPanel.style.display = "none";
  tableView.style.display = "block";
}

async function updateProjectEnv(projectId) {
  const cardPanel = document.getElementById("cardPanel");
  const controls = cardPanel.querySelector(".card-controls");
  const btns = cardPanel.querySelectorAll(".card-controls button");
  btns.forEach((b) => (b.disabled = true));

  // Создать (или очистить) область лога под кнопками.
  let log = document.getElementById("env-log");
  if (!log) {
    log = document.createElement("pre");
    log.id = "env-log";
    if (controls && controls.parentNode) {
      controls.parentNode.insertBefore(log, controls.nextSibling);
    } else {
      cardPanel.appendChild(log);
    }
  }
  log.textContent = "";

  try {
    const res = await fetch(
      `/api/env/projects/${projectId}/update-env/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    if (!res.ok || !res.body) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail || detail;
      } catch (e) {}
      log.textContent += `Ошибка: ${detail}\n`;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      log.textContent += decoder.decode(value, { stream: true });
      log.scrollTop = log.scrollHeight;
    }
    // Обновить поле «Версия окружения» на месте, не стирая лог.
    try {
      const r = await fetch(`/api/env/projects/${projectId}`);
      const data = await r.json();
      const ver = data.project && data.project.env_version;
      const field = cardPanel.querySelectorAll(".card-field .card-value");
      if (field.length >= 3 && ver) {
        field[2].textContent = ver;
      }
    } catch (e) {}
  } catch (e) {
    log.textContent += `\nОшибка: ${e.message}\n`;
  } finally {
    btns.forEach((b) => (b.disabled = false));
  }
}

async function deleteProject(projectId) {
  if (!confirm("Удалить проект из БД вместе со связанными задачами?\n" +
               "Каталог с файлами на диске останется на месте.")) return;
  try {
    const r = await fetch(`/api/env/projects/${projectId}`, { method: "DELETE" });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      alert(`Ошибка удаления: ${d.detail || r.statusText}`);
      return;
    }
    hideProjectCard({ preventDefault: () => {} });
    await loadProjects();
  } catch (e) {
    alert(`Ошибка: ${e.message}`);
  }
}
