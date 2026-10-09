// app/web/task-wizard.js

const STAGES = [
  { name: "analyze", label: "Аналитика" },
  { name: "plan", label: "Планирование" },
  { name: "tests", label: "Написание тестов" },
  { name: "develop", label: "Разработка" },
  { name: "testing", label: "Тестирование" },
  { name: "review", label: "Код-ревью" },
  { name: "docs", label: "Документация" },
];

// Этап «Тестирование» нельзя выбрать без «Написания тестов»: держим чекбокс
// testing выключенным (и снятым), пока не включён этап tests.
function syncTestingAvailability() {
  const testsCb = document.querySelector('.stage-enabled[data-stage="tests"]');
  const testingCb = document.querySelector('.stage-enabled[data-stage="testing"]');
  if (!testsCb || !testingCb) return;
  if (testsCb.checked) {
    testingCb.disabled = false;
  } else {
    testingCb.checked = false;
    testingCb.disabled = true;
  }
}

// Load projects on page load
async function loadProjects() {
  try {
    const r = await fetch("/api/env/projects");
    const data = await r.json();
    const ownerSelect = document.getElementById("owner");
    if (data.projects && Array.isArray(data.projects)) {
      data.projects.forEach(proj => {
        const option = document.createElement("option");
        option.value = proj.id;
        option.textContent = proj.name;
        ownerSelect.appendChild(option);
      });
    }
  } catch (err) {
    console.error("Failed to load projects:", err);
  }
}

// Populate stages table
function populateStages() {
  const tbody = document.getElementById("stagesBody");
  STAGES.forEach(stage => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="stage-name">${stage.label}</td>
      <td style="text-align: center;">
        <input type="checkbox" class="stage-enabled" name="stage-${stage.name}" data-stage="${stage.name}">
      </td>
      <td style="text-align: center;">
        <input type="checkbox" class="stage-gate" name="gate-${stage.name}" data-stage="${stage.name}">
      </td>
    `;
    tbody.appendChild(tr);
  });
  // Переключение этапа «Написание тестов» управляет доступностью «Тестирования».
  const testsCb = document.querySelector('.stage-enabled[data-stage="tests"]');
  if (testsCb) testsCb.addEventListener("change", syncTestingAvailability);
  syncTestingAvailability();
}

// Toggle all stages enabled
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("toggleAllStages").addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".stage-enabled").forEach(cb => { cb.checked = true; });
    syncTestingAvailability();
  });

  document.getElementById("toggleNoneStages").addEventListener("click", (e) => {
    e.preventDefault();
    document.querySelectorAll(".stage-enabled").forEach(cb => { cb.checked = false; });
    syncTestingAvailability();
  });

  populateStages();
  loadProjects();

  // Form submission
  document.getElementById("taskForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    // Clear previous errors
    document.querySelectorAll(".error").forEach(el => { el.textContent = ""; });
    document.getElementById("result").style.display = "none";

    // Collect form data
    const projectId = document.getElementById("owner").value;
    const name = document.getElementById("name").value.trim();
    const identifier = document.getElementById("identifier").value.trim();
    const goal = document.getElementById("goal").value.trim();
    const plan = document.getElementById("plan").value.trim();
    const constraints = document.getElementById("constraints").value.trim();
    const tests = document.getElementById("tests").value.trim();
    const updateDb = document.getElementById("update_db").checked;
    const markChanges = document.getElementById("mark_changes").checked;
    const interactive = document.getElementById("interactive").checked;
    const maxMinutes = parseInt(document.getElementById("max_minutes").value, 10);

    // Collect stages
    const enabledStages = [];
    const gatedStages = [];
    document.querySelectorAll(".stage-enabled").forEach(cb => {
      if (cb.checked) {
        const stageName = cb.dataset.stage;
        enabledStages.push(stageName);
        const gateCheckbox = document.querySelector(`.stage-gate[data-stage="${stageName}"]`);
        if (gateCheckbox && gateCheckbox.checked) {
          gatedStages.push(stageName);
        }
      }
    });

    // Validation
    const errors = {};
    if (!projectId) errors.owner = "Выберите проект";
    if (!name) errors.name = "Введите название";
    if (!identifier) errors.identifier = "Введите идентификатор";
    if (!goal) errors.goal = "Введите цель";
    if (!plan) errors.plan = "Введите план";
    if (!constraints) errors.constraints = "Введите ограничения";
    if (!Number.isInteger(maxMinutes) || maxMinutes < 1) {
      errors.max_minutes = "Укажите длительность в минутах (целое число ≥ 1)";
    }
    if (enabledStages.includes("tests") && !tests) {
      errors.tests = "Тесты обязательны если включен этап 'tests'";
    }
    if (enabledStages.includes("testing") && !enabledStages.includes("tests")) {
      errors.stages = "Этап 'testing' требует включённого этапа 'tests'";
    }

    // Show errors
    for (const [field, msg] of Object.entries(errors)) {
      const el = document.getElementById(field + "Error");
      if (el) el.textContent = msg;
    }

    if (Object.keys(errors).length > 0) {
      return;
    }

    // Submit
    const submitBtn = document.querySelector('#taskForm button[type="submit"].primary')
      || document.querySelector('#taskForm button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    try {
      const payload = {
        project_id: parseInt(projectId),
        name,
        identifier,
        goal,
        plan,
        constraints,
        tests: tests || "",
        enabled_stages: enabledStages,
        gated_stages: gatedStages,
        update_db: updateDb,
        mark_changes: markChanges,
        interactive: interactive,
        max_minutes: maxMinutes,
      };

      const r = await fetch("/api/env/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const resultDiv = document.getElementById("result");
      if (r.ok) {
        const data = await r.json();
        resultDiv.className = "success";
        resultDiv.innerHTML = `<strong>Задача создана!</strong><br>ID: ${escapeHtml(data.task.id)}<br>Статус: ${escapeHtml(data.task.status)}`;
        resultDiv.style.display = "block";
        document.getElementById("taskForm").reset();
        document.querySelectorAll(".stage-enabled").forEach(cb => { cb.checked = false; });
        document.querySelectorAll(".stage-gate").forEach(cb => { cb.checked = false; });
        syncTestingAvailability();
      } else {
        const data = await r.json();
        resultDiv.className = "error";
        const detail = data.detail || "Неизвестная ошибка";
        resultDiv.textContent = `Ошибка: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`;
        resultDiv.style.display = "block";
      }
    } catch (err) {
      const resultDiv = document.getElementById("result");
      resultDiv.className = "error";
      resultDiv.textContent = `Ошибка сети: ${err.message}`;
      resultDiv.style.display = "block";
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });
});
