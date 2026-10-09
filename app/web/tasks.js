document.addEventListener("DOMContentLoaded", loadTasks);

let allTasks = [];

async function loadTasks() {
  try {
    const r = await fetch("/api/env/tree");
    const data = await r.json();
    const projects = data.projects || [];

    // Flatten tasks from all projects
    allTasks = [];
    const projectMap = {};
    for (const proj of projects) {
      projectMap[proj.id] = proj.name;
      for (const task of (proj.tasks || [])) {
        allTasks.push({
          id: task.id,
          name: task.name,
          project_id: proj.id,
          project_name: proj.name,
          status: task.status,
          stages_json: task.stages_json,
        });
      }
    }

    const tbody = document.getElementById("tasksTable");
    const tableView = document.getElementById("tableView");

    if (allTasks.length === 0) {
      tableView.innerHTML = `
        <div class="empty-state">
          <h2>Нет задач</h2>
          <p>Создайте новую задачу, чтобы начать работу</p>
        </div>
      `;
      return;
    }

    tbody.innerHTML = "";
    for (const task of allTasks) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(task.name) || "(без названия)"}</td>
        <td>${escapeHtml(task.project_name) || "-"}</td>
        <td>${escapeHtml(task.status) || "-"}</td>
      `;
      tr.onclick = () => showTaskCard(task.id);
      tbody.appendChild(tr);
    }
  } catch (e) {
    document.getElementById("tableView").textContent = `Ошибка загрузки: ${e.message}`;
  }
}

async function showTaskCard(taskId) {
  try {
    const r = await fetch(`/api/env/tasks/${taskId}`);
    const data = await r.json();
    const task = data.task;

    // Parse stages_json
    let stages = [];
    if (task.stages_json) {
      try {
        stages = JSON.parse(task.stages_json);
      } catch (e) {
        console.error("Failed to parse stages_json:", e);
      }
    }

    const stagesHtml = stages.length > 0 ? `
      <div class="stages-list">
        ${stages.map(stage => `
          <div class="stage-item">
            <strong>${escapeHtml(stage.name)}</strong>
            <span class="stage-status ${escapeHtml(stage.status) || "planned"}">
              ${escapeHtml(stage.status) || "запланирован"}
            </span>
          </div>
        `).join("")}
      </div>
    ` : "<div class=\"card-value\">-</div>";

    const cardPanel = document.getElementById("cardPanel");
    const tableView = document.getElementById("tableView");

    // Find project name
    const projectTask = allTasks.find(t => t.id === taskId);
    const projectName = projectTask ? projectTask.project_name : "-";

    cardPanel.innerHTML = `
      <div class="task-card-panel">
        <div class="card-header">
          <h2>${escapeHtml(task.name) || "(без названия)"}</h2>
          <a href="#" class="back-link" onclick="hideTaskCard(event)">← Назад</a>
        </div>
        <div class="card-field">
          <span class="card-label">Название</span>
          <div class="card-value">${escapeHtml(task.name) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Проект</span>
          <div class="card-value">${escapeHtml(projectName)}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Цель</span>
          <div class="card-value">${escapeHtml(task.goal) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">План</span>
          <div class="card-value">${escapeHtml(task.plan) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Ограничения</span>
          <div class="card-value">${escapeHtml(task.constraints) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Тесты</span>
          <div class="card-value">${escapeHtml(task.tests) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Статус</span>
          <div class="card-value">${escapeHtml(task.status) || "-"}</div>
        </div>
        <div class="card-field">
          <span class="card-label">Этапы</span>
          ${stagesHtml}
        </div>
      </div>
    `;

    tableView.style.display = "none";
    cardPanel.style.display = "block";
  } catch (e) {
    alert(`Ошибка загрузки задачи: ${e.message}`);
  }
}

function hideTaskCard(event) {
  event.preventDefault();
  const cardPanel = document.getElementById("cardPanel");
  const tableView = document.getElementById("tableView");
  cardPanel.style.display = "none";
  tableView.style.display = "block";
}
