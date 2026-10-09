# P1.4 — Задачи v2 + гейты — дизайн

Дата: 2026-10-04. Статус: утверждён (Фаза 1).

## Контекст
Задачи переходят в `TaskRepo` (P1.1). Новое по `tmp/NOTE.md`: владелец (проект),
«название» вместо заголовка, поле «тесты», правила галок, кнопки все/снять, гейты
(остановка и ожидание OK после выбранных этапов) + поток resume.

## Модель
- Задача: `project_id` (владелец), `name`, `goal`, `plan`, `constraints`, `tests`,
  `stages_json`, `status`, `stage`. Статусы: planned, queued, running, stopped,
  awaiting_user, done, failed.
- Этап в `stages_json`: `{name, enabled, subagent, artifact, gate, approved, status,
  changed_files}`. Семь этапов (как Фаза 0: analyze/plan/tests/develop/testing/review/
  docs). `gate=true` → после этого этапа задача уходит в `awaiting_user` и ждёт approve.
- Сводный статус (`overall`): failed > любой gated-done-not-approved → awaiting_user >
  all enabled done → done > running > planned/queued.

## Правила создания (валидация)
- `name`, `goal`, `plan`, `constraints` — обязательны.
- `tests` (текст) обязателен, если включён этап `tests`.
- этап `testing` нельзя включить без `tests`.
- кнопки «все галочки»/«снять все» — на UI.
- для каждого этапа — флаг gate (пауза для OK).

## API (`env/task_api2.py`, в create_app, prefix `/api/env/tasks`)
- `POST /api/env/tasks` — создать (валидация выше; stages_json из enabled+gated;
  пишет TaskRepo + на диск `tasks/task#<id>/TASK.md`+`task.json` для оркестратора).
- `GET /api/env/tasks?project_id=` / `GET /api/env/tasks/{id}`.
- `DELETE /api/env/tasks/{id}`.
- `POST /api/env/tasks/{id}/stage` `{stage, status, changed_files?}` — обновить этап
  (используется деплоенным инструментом/оркестратором; обновляет stages_json+статус
  задачи; при gated-done → awaiting_user).
- `POST /api/env/tasks/{id}/approve` `{stage}` — снять гейт (approved=true) → задача
  возвращается в planned/queued для продолжения.
- `GET /api/env/tasks/{id}/overall` → сводный статус.

## Web — создание задачи v2 (`/task-wizard` или обновить `/create-task`)
Поля: владелец (select из `/api/env/projects`), название, цель*, план*, ограничения*,
тесты (обязательно при галке tests), чекбоксы 7 этапов + «gate» на каждый, кнопки
«Все»/«Снять все». Валидация правил. Тёмная тема.

## Границы
- Реальный прогон задачи и обновление статусов оркестратором — P1.6 (там же repoint
  `task_status.py` на API). Здесь — модель, API, UI, переходы статусов и approve.
- Старый файловый `/api/tasks` и `/create-task` (Фаза 0) остаются.

## Тестирование
- build_stages с gated; overall_status все ветки (incl awaiting_user); правила
  валидации (tests обязателен при tests-этапе; testing без tests → ошибка).
- API: create (persist TaskRepo + on-disk TASK.md/task.json); list/get/delete;
  stage-update переводит gated-done → awaiting_user; approve снимает гейт.
- Страница создания задачи v2 отдаётся.
- Полный набор зелёный.
