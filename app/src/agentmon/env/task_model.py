"""
Модель задач v2 с гейтами (этапы, общий статус, валидация).

Задача v2 включает 7 этапов с поддержкой гейтов:
- Каждый этап может быть включен/отключен
- Гейтированные этапы требуют подтверждения перед началом следующих
- Общий статус вычисляется на основе статусов этапов
"""

# 7 этапов с подагентом и артефактом
DEFAULT_STAGES = [
    {"name": "analyze", "subagent": "analyst", "artifact": "ANALYZE.md"},
    {"name": "plan", "subagent": "architect", "artifact": "ARCHITECT.md"},
    {"name": "tests", "subagent": "developer", "artifact": "TESTS.md"},
    {"name": "develop", "subagent": "developer", "artifact": "DEVELOP.md"},
    {"name": "testing", "subagent": "tester", "artifact": "TESTING.md"},
    {"name": "review", "subagent": "reviewer", "artifact": "REVIEW.md"},
    {"name": "docs", "subagent": "developer", "artifact": "DOCS.md"},
]

# Имена стадий для удобства
STAGE_NAMES = [s["name"] for s in DEFAULT_STAGES]


def build_stages(enabled_names, gated_names=()):
    """
    Создаёт список этапов с заполненными полями статуса и гейтов.

    Args:
        enabled_names: список имён включённых этапов
        gated_names: список имён этапов, имеющих гейт

    Returns:
        list[dict]: каждый этап с полями:
            - name: имя этапа
            - enabled: включен ли этап
            - subagent: имя подагента
            - artifact: имя артефакта
            - gate: есть ли гейт на этапе
            - approved: одобрен ли гейт (False по умолчанию)
            - status: 'pending' если enabled, 'skipped' если нет
            - changed_files: список изменённых файлов
    """
    enabled_set = set(enabled_names)
    gated_set = set(gated_names)

    stages = []
    for stage_def in DEFAULT_STAGES:
        name = stage_def["name"]
        is_enabled = name in enabled_set
        is_gated = name in gated_set

        stage = {
            "name": name,
            "enabled": is_enabled,
            "subagent": stage_def["subagent"],
            "artifact": stage_def["artifact"],
            "gate": is_gated,
            "approved": False,
            "status": "pending" if is_enabled else "skipped",
            "changed_files": [],
        }
        stages.append(stage)

    return stages


def overall_status(stages):
    """
    Вычисляет общий статус задачи по статусам этапов.

    Приоритет (по убыванию):
    1. failed: если какой-то enabled этап имеет статус 'failed'
    2. awaiting_user: если гейтированный enabled этап done и не approved,
       и существует enabled pending этап после него
    3. done: если все enabled этапы имеют статус 'done'
    4. running: если какой-то enabled этап имеет статус 'running'
    5. planned: если есть enabled этап с другим статусом
    6. done: если нет enabled этапов

    Args:
        stages: список этапов из build_stages

    Returns:
        str: вычисляемый по этапам статус — один из 'failed', 'awaiting_user',
             'done', 'running', 'planned'. Внешне управляемые статусы ('queued',
             'stopped') эта функция не возвращает — их выставляют диспетчер/стек,
             и пересчёт overall по этапам их не сохраняет.
    """
    # Получаем только включённые этапы
    enabled_stages = [s for s in stages if s["enabled"]]

    # Если нет включённых этапов -> done
    if not enabled_stages:
        return "done"

    # Приоритет 1: any failed
    if any(s["status"] == "failed" for s in enabled_stages):
        return "failed"

    # Приоритет 2: awaiting_user
    # Гейтированный этап done и не approved, и есть enabled pending после
    for i, stage in enumerate(enabled_stages):
        if (stage["gate"] and stage["status"] == "done" and not stage["approved"]):
            # Проверяем есть ли pending после этого этапа
            for later_stage in enabled_stages[i + 1:]:
                if later_stage["status"] == "pending":
                    return "awaiting_user"

    # Приоритет 3: all done
    if all(s["status"] == "done" for s in enabled_stages):
        return "done"

    # Приоритет 4: any running
    if any(s["status"] == "running" for s in enabled_stages):
        return "running"

    # Приоритет 5: default -> planned
    return "planned"


def validate_task(*, name, identifier, goal, plan, constraints, tests, enabled_names):
    """
    Валидирует поля задачи и возвращает список ошибок на русском.

    Проверяет:
    - name, identifier, goal, plan, constraints не пусты
    - identifier не содержит символов, ломающих имя каталога
    - если этап 'tests' включен, то tests не пуст
    - если этап 'testing' включен, то 'tests' тоже включен

    Args:
        name: название задачи
        identifier: идентификатор задачи (используется как имя каталога task#{identifier})
        goal: цель задачи
        plan: план выполнения
        constraints: ограничения
        tests: текст с тестами
        enabled_names: список включённых этапов

    Returns:
        list[str]: список ошибок на русском (пусто если валидна)
    """
    errors = []

    # Проверки на пустые базовые поля
    if not name or not name.strip():
        errors.append("Название задачи не может быть пустым")

    if not identifier or not identifier.strip():
        errors.append("Идентификатор не может быть пустым")
    elif any(ch in identifier for ch in ("/", "\\")) or ".." in identifier:
        errors.append("Идентификатор не должен содержать '/', '\\' или '..'")

    if not goal or not goal.strip():
        errors.append("Цель не может быть пустой")

    if not plan or not plan.strip():
        errors.append("План не может быть пустым")

    if not constraints or not constraints.strip():
        errors.append("Ограничения не могут быть пустыми")

    # Проверка: если 'tests' этап включен, то tests текст должен быть непуст
    enabled_set = set(enabled_names)
    if "tests" in enabled_set:
        if not tests or not tests.strip():
            errors.append("Текст тестов не может быть пустым при включённом этапе 'tests'")

    # Проверка: если 'testing' включен, то 'tests' должен быть включен
    if "testing" in enabled_set and "tests" not in enabled_set:
        errors.append("Этап 'testing' требует включённого этапа 'tests'")

    return errors
