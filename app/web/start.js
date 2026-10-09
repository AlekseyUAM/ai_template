/* start.js — стартовая страница Agent Monitor */

const REFRESH_INTERVAL_MS = 5000;
let _treeData = null; // кэш дерева для DnD
let _draggedTaskId = null; // для отслеживания перемещений

/* ── версия ──────────────────────────────────────────────────────────── */
async function loadVersion() {
  try {
    const r = await fetch("/api/env/version");
    if (!r.ok) return;
    const data = await r.json();
    const ver = data.version || data.current || "";
    if (ver) {
      const el = document.getElementById("ver");
      if (el) el.textContent = "v" + ver;
    }
  } catch (_) { /* молчим */ }
}

/* ── удалить задачу ──────────────────────────────────────────────────── */
async function deleteTask(taskId) {
  try {
    const r = await fetch(`/api/env/tasks/${taskId}`, { method: "DELETE" });
    if (!r.ok) { alert("Не удалось удалить задачу"); }
    await renderTree();
  } catch (e) {
    console.error("delete task error", e);
  }
}

/* ── статус → CSS-класс ──────────────────────────────────────────────── */
function statusClass(status) {
  if (status === "выполняется") return "status-running";
  if (status === "ошибка") return "status-failed";
  if (status === "выполнена") return "status-done";
  return "";
}

/* ── построить дерево ────────────────────────────────────────────────── */
async function renderTree() {
  const container = document.getElementById("tree");
  if (!container) return;

  let data;
  try {
    const r = await fetch("/api/env/tree");
    if (!r.ok) {
      container.innerHTML = `<span class="tree-empty">Ошибка загрузки дерева (${r.status})</span>`;
      return;
    }
    data = await r.json();
    _treeData = data; // кэшируем для использования в DnD и других функциях
  } catch (e) {
    container.innerHTML = `<span class="tree-empty">Нет соединения с сервером</span>`;
    return;
  }

  const projects = data.projects || [];
  if (projects.length === 0) {
    container.innerHTML = `<span class="tree-empty">Проектов нет. Создайте первый проект.</span>`;
    return;
  }

  const html = projects.map(proj => {
    const tasksHtml = proj.tasks && proj.tasks.length > 0
      ? proj.tasks.map(task => {
          const cls = statusClass(task.status);
          const elapsed = task.elapsed_min != null ? task.elapsed_min + " мин" : "";
          const taskPath = task.task_path || "";
          return `
            <div class="tree-task" data-task-id="${task.id}" data-status-raw="${escHtml(task.status_raw || '')}">
              <button class="task-del" title="Удалить задачу" onclick="deleteTask(${Number(task.id)})">✕</button>
              <span class="task-name" title="${escHtml(task.name)}">${escHtml(task.name)}</span>
              <span class="task-path" title="${escHtml(taskPath)}">${escHtml(taskPath)}</span>
              <span class="task-status ${cls}">${escHtml(task.status)}</span>
              <span class="task-elapsed">${escHtml(elapsed)}</span>
            </div>`;
        }).join("")
      : `<div class="no-tasks">Задач нет</div>`;

    return `
      <div class="tree-project">
        <div class="tree-project-header">
          <span class="proj-name">${escHtml(proj.name)}</span>
          <span class="proj-path">${escHtml(proj.path || "")}</span>
        </div>
        <div class="tree-tasks">${tasksHtml}</div>
      </div>`;
  }).join("");

  container.innerHTML = html;

  // Делаем planned-задачи перетаскиваемыми
  makePlanedTasksDraggable();
}

// Используем общий помощник escapeHtml из esc.js (экранирует все пять символов).
function escHtml(str) {
  return escapeHtml(str);
}

/* ── стеки выполнения ────────────────────────────────────────────────── */

async function renderStacks() {
  const container = document.getElementById("stacks-container");
  if (!container) return;

  try {
    const r = await fetch("/api/env/stacks");
    if (!r.ok) {
      container.innerHTML = `<div class="placeholder">Ошибка загрузки стеков (${r.status})</div>`;
      return;
    }
    const data = await r.json();
    const stacks = data.stacks || [];

    if (stacks.length === 0) {
      container.innerHTML = `<div class="placeholder">Нет стеков. Создайте первый стек.</div>`;
      return;
    }

    const html = stacks.map(stack => {
      const itemsHtml = stack.items && stack.items.length > 0
        ? stack.items.map(item => {
            const itemCls = item.task_status === "выполняется" ? "status-running" :
                          item.task_status === "ошибка" ? "status-failed" : "";
            return `<div class="stack-item" draggable="true" data-task-id="${item.task_id}"
                         data-item-id="${item.item_id}" data-project-id="${item.project_id}">
              <span class="${itemCls}">${escHtml(item.task_name)}</span>
              <span style="font-size:10px; color:var(--muted);"> (${escHtml(item.task_status)})</span>
            </div>`;
          }).join("")
        : `<div class="stack-item-empty">Нет задач</div>`;

      const isRunning = stack.status === "running";
      return `
        <div class="stack-column" data-stack-id="${stack.id}" data-stack-status="${stack.status}">
          <div class="stack-header">
            <span class="stack-name">${escHtml(stack.name)}</span>
            <span class="stack-status">${escHtml(stack.status)}</span>
            <div class="stack-controls">
              <button class="stack-btn start-btn" title="Запустить" onclick="startStack(${Number(stack.id)})">▶</button>
              <button class="stack-btn stop-btn" title="Остановить" onclick="stopStack(${Number(stack.id)})" ${!isRunning ? 'style="opacity:0.4"' : ''}>⏸</button>
              <button class="stack-btn delete-btn delete" title="Удалить" onclick="deleteStack(${Number(stack.id)})">✕</button>
            </div>
          </div>
          <div class="stack-items" ondrop="handleDropOnStack(event, ${Number(stack.id)})" ondragover="handleDragOverStack(event)" ondragleave="handleDragLeaveStack(event)">
            ${itemsHtml}
          </div>
        </div>`;
    }).join("");

    container.innerHTML = html;

    // Установить обработчики DnD для элементов стека
    document.querySelectorAll(".stack-item").forEach(item => {
      item.addEventListener("dragstart", handleStackItemDragStart);
      item.addEventListener("dragend", handleStackItemDragEnd);
      item.addEventListener("dragover", handleStackItemDragOver);
      item.addEventListener("drop", handleStackItemDrop);
    });
  } catch (e) {
    console.error("render stacks error", e);
    container.innerHTML = `<div class="placeholder">Ошибка соединения</div>`;
  }
}

async function createStack() {
  const name = prompt("Название стека:");
  if (!name) return;

  try {
    const r = await fetch("/api/env/stacks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!r.ok) {
      alert("Ошибка создания стека");
      return;
    }
    await renderStacks();
  } catch (e) {
    console.error("create stack error", e);
    alert("Ошибка соединения");
  }
}

async function createTestTask() {
  // Используем первый проект из дерева, или запрашиваем
  if (!_treeData || !_treeData.projects || _treeData.projects.length === 0) {
    alert("Нет проектов. Создайте проект сначала.");
    return;
  }

  const projectId = _treeData.projects[0].id;
  const name = prompt("Название тестовой задачи:", "Тест");
  if (name === null) return;

  try {
    const r = await fetch("/api/env/tasks/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, name: name || "Тест" }),
    });
    if (!r.ok) {
      alert("Ошибка создания тестовой задачи");
      return;
    }
    // Обновляем дерево и стеки
    await renderTree();
    await renderStacks();
  } catch (e) {
    console.error("create test task error", e);
    alert("Ошибка соединения");
  }
}

async function startStack(stackId) {
  try {
    const r = await fetch(`/api/env/stacks/${stackId}/start`, { method: "POST" });
    if (!r.ok) alert("Ошибка запуска стека");
    await renderStacks();
  } catch (e) {
    console.error("start stack error", e);
  }
}

async function stopStack(stackId) {
  try {
    const r = await fetch(`/api/env/stacks/${stackId}/stop`, { method: "POST" });
    if (!r.ok) alert("Ошибка остановки стека");
    await renderStacks();
  } catch (e) {
    console.error("stop stack error", e);
  }
}

async function deleteStack(stackId) {
  if (!confirm("Удалить стек?")) return;
  try {
    const r = await fetch(`/api/env/stacks/${stackId}`, { method: "DELETE" });
    if (!r.ok) alert("Ошибка удаления стека");
    await renderStacks();
  } catch (e) {
    console.error("delete stack error", e);
  }
}

/* ── drag-and-drop ──────────────────────────────────────────────────── */

function handleStackItemDragStart(e) {
  _draggedTaskId = e.currentTarget.dataset.taskId;
  e.currentTarget.classList.add("drag-from");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", _draggedTaskId);
}

function handleStackItemDragEnd(e) {
  e.currentTarget.classList.remove("drag-from");
  document.querySelectorAll(".stack-item.drag-over").forEach(el => {
    el.classList.remove("drag-over");
  });
  _draggedTaskId = null;
}

function handleStackItemDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  if (e.currentTarget.classList.contains("stack-item")) {
    e.currentTarget.classList.add("drag-over");
  }
}

function handleStackItemDrop(e) {
  e.preventDefault();
  e.stopPropagation();

  const targetItem = e.currentTarget;
  if (!targetItem.classList.contains("stack-item")) return;

  targetItem.classList.remove("drag-over");

  const draggedTaskId = e.dataTransfer.getData("text/plain") || _draggedTaskId;
  const sourceItem = document.querySelector(`[data-task-id="${draggedTaskId}"].stack-item`);
  const targetTaskId = targetItem.dataset.taskId;

  if (draggedTaskId === targetTaskId) return;
  if (!sourceItem) return; // если перемещаем из дерева, нечего переупорядочивать

  // Переупорядочивание внутри стека
  const stackColumn = sourceItem.closest(".stack-column");
  const stackId = stackColumn.dataset.stackId;
  const stackStatus = stackColumn.dataset.stackStatus;

  if (stackStatus === "running") {
    alert("Нельзя переупорядочить задачи в запущенном стеке");
    return;
  }

  // Собираем новый порядок
  const items = Array.from(stackColumn.querySelectorAll(".stack-item"));
  const sourceIdx = items.indexOf(sourceItem);
  const targetIdx = items.indexOf(targetItem);

  if (sourceIdx === -1 || targetIdx === -1) return;

  // Переставляем в DOM
  if (sourceIdx < targetIdx) {
    targetItem.parentNode.insertBefore(sourceItem, targetItem.nextSibling);
  } else {
    targetItem.parentNode.insertBefore(sourceItem, targetItem);
  }

  // Отправляем новый порядок на сервер
  const newOrder = Array.from(stackColumn.querySelectorAll(".stack-item")).map(el => parseInt(el.dataset.taskId));
  reorderStack(stackId, newOrder);
}

function handleDropOnStack(e, stackId) {
  e.preventDefault();
  e.stopPropagation();

  const stackColumn = document.querySelector(`[data-stack-id="${stackId}"]`);
  if (!stackColumn) return;

  stackColumn.querySelector(".stack-items").classList.remove("drag-over");

  const draggedTaskId = e.dataTransfer.getData("text/plain") || _draggedTaskId;
  if (!draggedTaskId) return;

  // Проверяем, не принадлежит ли задача уже этому стеку
  const existingItem = stackColumn.querySelector(`[data-task-id="${draggedTaskId}"]`);
  if (existingItem) return; // уже в этом стеке

  // Добавляем задачу в стек
  addTaskToStack(stackId, parseInt(draggedTaskId));
}

function handleDragOverStack(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
  const stackItems = e.currentTarget;
  stackItems.classList.add("drag-over");
}

function handleDragLeaveStack(e) {
  if (e.currentTarget === e.target) {
    e.currentTarget.classList.remove("drag-over");
  }
}

async function addTaskToStack(stackId, taskId) {
  try {
    const r = await fetch(`/api/env/stacks/${stackId}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId }),
    });
    if (!r.ok) {
      const errData = await r.json();
      alert("Ошибка: " + (errData.detail || "не удалось добавить задачу"));
      return;
    }
    await renderStacks();
  } catch (e) {
    console.error("add task to stack error", e);
  }
}

async function reorderStack(stackId, taskIds) {
  try {
    const r = await fetch(`/api/env/stacks/${stackId}/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_ids: taskIds }),
    });
    if (!r.ok) alert("Ошибка переупорядочивания");
  } catch (e) {
    console.error("reorder stack error", e);
  }
}

/* ── makeable tree tasks ────────────────────────────────────────────── */

function makePlanedTasksDraggable() {
  document.querySelectorAll(".tree-task").forEach(el => {
    // Только задачи со статусом "planned" можно перетаскивать
    if (el.dataset.statusRaw === "planned") {
      const taskId = el.dataset.taskId;
      if (taskId) {
        el.draggable = true;
        el.addEventListener("dragstart", handleTreeTaskDragStart);
        el.addEventListener("dragend", handleTreeTaskDragEnd);
      }
    }
  });
}

function handleTreeTaskDragStart(e) {
  const row = e.currentTarget;
  const taskId = row.dataset.taskId;

  if (!taskId) return;

  _draggedTaskId = taskId;
  e.currentTarget.classList.add("drag-from");
  e.dataTransfer.effectAllowed = "copy";
  e.dataTransfer.setData("text/plain", taskId);
}

function handleTreeTaskDragEnd(e) {
  e.currentTarget.classList.remove("drag-from");
}

/* ── init ────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  loadVersion();
  renderTree();
  renderStacks();

  // Автообновление дерева и стеков
  setInterval(() => {
    renderTree();
    renderStacks();
  }, REFRESH_INTERVAL_MS);

  // Обработчики кнопок создания
  const btnCreateStack = document.getElementById("btn-create-stack");
  if (btnCreateStack) {
    btnCreateStack.addEventListener("click", createStack);
  }

  const btnCreateTestTask = document.getElementById("btn-create-test-task");
  if (btnCreateTestTask) {
    btnCreateTestTask.addEventListener("click", createTestTask);
  }
});
