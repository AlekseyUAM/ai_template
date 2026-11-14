"""Промпт сессии-аналитика, извлечение ответа и детерминированный отчёт."""
from __future__ import annotations

import os
from pathlib import Path

from bench_metrics import StreamSummary


def build_prompt(*, run_id: str, project_dir: Path, repo_root: Path,
                 run_dir: Path, metrics_path: Path, digest_path: Path,
                 manifest_path: Path, reference_path: Path | None,
                 contaminated: bool, task_folders: list[str]) -> str:
    reference = str(reference_path) if reference_path else "недоступен"
    tasks = ", ".join(task_folders)
    return f"""Ты — старший аналитик benchmark-прогона Claude-агента на 1С.

Твоя задача — по собранным фактам объяснить, почему прогон занял столько времени,
сколько было лишних итераций тестов и ревью, и предложить улучшения template.
Ты НЕ выполняешь задачи, НЕ запускаешь тесты и загрузку ИБ, НЕ меняешь файлы проекта.

## Входы (читай только их)
- Метрики: {metrics_path}
- Дайджест: {digest_path}
- Манифест входов (каталоги задач и артефакты): {manifest_path}
- Диффы прогона: {run_dir / "diffs"}
- Транскрипты: {run_dir / "transcripts"}
- Проект: {project_dir}
- Корень репозитория (template и benchmark): {repo_root}
- Эталонная реализация: {reference}
- Задачи прогона: {tasks}
- Прогон: {run_id}
- Проект мог быть не свежим (--force): {'да' if contaminated else 'нет'}

Разрешено: Read, Grep, Glob, Bash только для чтения логов и запуска
`.claude/skills/*/scripts/*.py` (code-analyze/query-analyze), MCP `bsl_ls`.
Запрещено: Edit/Write/MultiEdit/NotebookEdit, запуск тестов, загрузка конфигурации,
изменение git-состояния, выполнение задач.

## Обязательные ограничения
- Рекомендации должны быть ОБЩИМИ для любых будущих задач. Не затачивай template
  под задачи #001/#002 и не предлагай код, специфичный только для них.
- Не хардкодь фрагменты кода из example.bsl в template.
- Не увеличивай число символов в описаниях задач benchmark/tasks. Если предлагаешь
  переформулировку — покажи длину «до/после» и оставь «после» не больше «до».
- Не выдавай пропущенные проверки за пройденные: если анализатор/слой недоступен,
  так и напиши.
- Отделяй факты (метрики, логи, файл:строка) от гипотез.
- Сравнивай итоговый модуль с эталоном семантически, а не по текстовому совпадению:
  что упущено, что реализовано иначе, что сделано лучше/хуже.

## Формат ответа
Верни ТОЛЬКО markdown-отчёт (без преамбул и комментариев о процессе), на русском,
со структурой:
1. `## Сводка прогона` — таблица «задача → лимит → факт → исход → этапы → итерации →
   тесты → вердикт ревью», стоимость/токены, пометка о --force.
2. `## Время выполнения` — где ушло время, долгие операции, простои.
3. `## Итерации написания и запуска тестов` — циклы, причины возвратов, лишние прогоны.
4. `## Итерации код-ревью` — раунды, находки, возвраты.
5. `## Качество кода` — сравнение с эталоном, находки анализаторов по коду и эталону.
6. `## Окружение template` — сбои MCP/хуков/платформы, повторяющиеся ошибки,
   отсутствующие инструменты, медленные места.
7. `## Рекомендации` — таблицы «быстрые победы (P1)» и «крупные изменения (P2)»:
   проблема + доказательство, конкретное изменение (файлы), ожидаемый эффект,
   риск/трудоёмкость. Отдельно — предложения по описаниям задач, `ЮнитТесты`, инструментам.
8. `## Что уже работает хорошо`.
9. `## Приложение` — пути к метрикам, дайджесту, диффам, транскриптам.

Отчёт должен быть конкретным: каждая рекомендация опирается на метрику, лог или
файл:строку. Если данных для вывода нет — напиши «недостаточно данных», не выдумывай.
"""


def extract_analyst_text(stream: StreamSummary) -> str | None:
    result = stream.result or {}
    text = result.get("result")
    if result.get("is_error") or not isinstance(text, str):
        return None
    # lstrip(), не strip(): сохраняем конечный перевод строки (ожидание теста),
    # финальный \n нормализует write_report.
    return text.lstrip() or None


def deterministic_report(*, run_id: str, project_dir: Path, run_dir: Path,
                         metrics: dict, error: str | None = None,
                         skipped: bool = False) -> str:
    lines = [f"# Результат benchmark-прогона {run_id}", ""]
    if error:
        lines += ["## ⚠ Аналитическая сессия не дала отчёт", "",
                  f"Ошибка: {error}", "",
                  "Ниже — только объективные метрики прогона.", ""]
    elif skipped:
        lines += ["## Качественный анализ пропущен (--skip-analysis)", ""]
    run = metrics.get("run") or {}
    lines += ["## Сводка прогона", "",
              f"- Проект: `{project_dir}`",
              f"- Каталог прогона: `{run_dir}`",
              f"- Команда агента: `{run.get('claude_cmd', '—')}`",
              f"- --force: {'да' if run.get('force') else 'нет'}", "",
              "| Задача | Лимит | Исход | Факт |", "|---|---|---|---|"]
    for task in metrics.get("tasks") or []:
        seconds = task.get("duration_sec")
        fact = f"{seconds / 60:.1f} мин" if isinstance(seconds, (int, float)) else "—"
        lines.append(f"| {task.get('folder')} | {task.get('limit_minutes')} мин | "
                     f"{task.get('outcome')} | {fact} |")
    lines += ["", "## Артефакты", "",
              f"- Метрики: `{run_dir / 'metrics.json'}`",
              f"- Дайджест: `{run_dir / 'digest.md'}`",
              f"- Диффы: `{run_dir / 'diffs'}`",
              f"- Транскрипты: `{run_dir / 'transcripts'}`", ""]
    return "\n".join(lines)


def write_report(project_dir: Path, text: str) -> Path:
    target = project_dir / "tmp" / "RESULT.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text if text.endswith("\n") else text + "\n",
                       encoding="utf-8")
        os.replace(tmp, target)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    return target
