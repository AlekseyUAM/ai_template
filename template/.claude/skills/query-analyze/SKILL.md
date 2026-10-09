---
name: query-analyze
description: Автоматический анализ запросов 1С на нарушения стандартов оптимальных запросов. Используй для поиска проблем/ошибок в тексте запроса перед код-ревью.
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /query-analyze — автоматический анализ запросов 1С

Находит нарушения стандартов разработки оптимальных запросов (ИТС, std*).
Работает в два шага: извлечение текста запроса из `.bsl`/СКД-XML и прогон
реестра автоматических проверок.

## Извлечение запросов

```bash
# Из .bsl-файла или каталога (рекурсивно)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Catalogs/Товары/Ext/ManagerModule.bsl
# Из макетов СКД (XML)
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path src/cf/Reports -Xml
```

Выводит блоки `# <путь>:<строка>` с текстом запроса, разделённые `--- 8< ---`.

## Анализ запроса

```bash
# Текст запроса из файла
python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" query.txt
# Или из stdin
python "${CLAUDE_SKILL_DIR}/scripts/extract_queries.py" -Path Module.bsl | python "${CLAUDE_SKILL_DIR}/scripts/analyze_query.py" -
```

Находки печатаются как `severity | std-код | строка | сообщение`. Флаг
`-Detailed` показывает и пройденные проверки. Код возврата ≠ 0 при находках
уровня `error`.

## Зависимости

Структурные (AST) проверки требуют:
- `node` в PATH;
- вендоренного бандла `scripts/vendor/sdbl_parse.js` (пересборка: `scripts/vendor/build-parser.sh`).

Без них работают **только текстовые правила** (keyword-lowercase, query-one-line); все
структурные проверки **ПРОПУСКАЮТСЯ** (не считаются пройденными). Инструмент
выводит предупреждение в stderr в этом случае.

## Чего анализатор НЕ проверяет

Автопроверки работают только по тексту запроса. Соответствие индексам БД,
семантике задачи и составу метаданных проверяется вручную — см. навык
`query-review`.
