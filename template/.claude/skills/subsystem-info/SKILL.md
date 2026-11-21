---
name: subsystem-info
description: Analyze 1C subsystem structure from an XML dump - content, child subsystems, command interface, hierarchy tree. Use to study subsystem structure and navigate the configuration
argument-hint: <SubsystemPath> [-Mode overview|content|ci|tree|full] [-Name <element>]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /subsystem-info - 1C subsystem structure

Reads subsystem XML from a 1C configuration dump and prints a compact structure description.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `SubsystemPath` | Path to the subsystem XML file, subsystem directory, or the `Subsystems/` directory (for tree) |
| `Mode` | Mode: `overview` (default), `content`, `ci`, `tree`, `full` |
| `Name` | Drill-down: object type in content, section in ci, subsystem name in tree |
| `Limit` / `Offset` | Pagination (default 150 lines) |
| `OutFile` | Write the result to a file (UTF-8 BOM) |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/subsystem-info.py" -SubsystemPath "<путь>"
```

## Five modes

| Mode | What it shows |
|---|---|
| `overview` *(default)* | Compact summary: properties, content (grouped by type), child subsystems, CI presence |
| `content` | Content list grouped by object type. `-Name Catalog` - catalogs only |
| `ci` | CommandInterface.xml parse: visibility, placement, order of commands/subsystems/groups |
| `tree` | Recursive subsystem hierarchy tree with markers [CI], [OneCmd], [Скрыт] |
| `full` | Full summary: overview + content + ci in one call |

## Examples

```bash
# Обзор подсистемы
... -SubsystemPath Subsystems/Продажи.xml

# Состав подсистемы
... -SubsystemPath Subsystems/Администрирование.xml -Mode content

# Только документы в составе
... -SubsystemPath Subsystems/Продажи.xml -Mode content -Name Document

# Командный интерфейс подсистемы
... -SubsystemPath Subsystems/Продажи.xml -Mode ci

# Дерево подсистем от корня
... -SubsystemPath Subsystems -Mode tree

# Дерево от конкретной подсистемы
... -SubsystemPath Subsystems/Администрирование.xml -Mode tree

# Дерево только для одной подсистемы
... -SubsystemPath Subsystems -Mode tree -Name Администрирование
```
