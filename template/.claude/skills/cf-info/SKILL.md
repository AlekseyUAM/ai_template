---
name: cf-info
description: Analysis of the 1C configuration structure - properties, composition, object counters. Use for an overview of the configuration - which objects exist, how many, which settings
argument-hint: <ConfigPath> [-Mode overview|brief|full] [-Section home-page]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cf-info - 1C configuration structure

Reads Configuration.xml from the configuration export and prints a compact description of the structure.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `ConfigPath` | Path to Configuration.xml or the export directory |
| `Mode` | Mode: `overview` (default), `brief`, `full` |
| `Section` | Drill-down by section (alias: `Name`). Currently: `home-page` |
| `Limit` / `Offset` | Paging (150 lines by default) |
| `OutFile` | Write the result to a file (UTF-8 BOM) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cf-info.py" -ConfigPath "<путь>"
```

## Three modes

| Mode | What it shows |
|---|---|
| `overview` *(default)* | Header + key properties + table of object counters by type |
| `brief` | One line: Name - "Synonym" vVersion \| N objects \| compatibility |
| `full` | All properties by category + full ChildObjects list + DefaultRoles + mobile features |

## Examples

```bash
# Обзор пустой конфигурации
... -ConfigPath src

# Краткая сводка реальной конфигурации
... -ConfigPath src -Mode brief

# Полная информация
... -ConfigPath src -Mode full

# С пагинацией
... -ConfigPath src -Mode full -Limit 50 -Offset 100

# Drill-down: только начальная страница (раскладка форм с ролями)
... -ConfigPath src -Section home-page
```
