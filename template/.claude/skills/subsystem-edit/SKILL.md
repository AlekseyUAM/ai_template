---
name: subsystem-edit
description: Point edits of a 1C subsystem. Use when you need to add or remove objects from a subsystem, manage child subsystems or change properties
argument-hint: -SubsystemPath <path> -Operation <op> -Value <value>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /subsystem-edit - editing a 1C subsystem

Point edits of subsystem XML: content, child subsystems, properties.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `SubsystemPath` | Path to the subsystem XML file |
| `DefinitionFile` | JSON file with an array of operations |
| `Operation` | One operation (alternative to DefinitionFile) |
| `Value` | Value for the operation |
| `NoValidate` | Skip auto-validation |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/subsystem-edit.py" -SubsystemPath '<path>' -Operation add-content -Value 'Catalog.Товары'
```

## Operations

| Operation | Value | Description |
|----------|----------|----------|
| `add-content` | `"Catalog.X"` or `["Catalog.X","Document.Y"]` | Add objects to Content |
| `remove-content` | `"Catalog.X"` or `["Catalog.X"]` | Remove objects from Content |
| `add-child` | `"ИмяПодсистемы"` | Add a child subsystem to ChildObjects |
| `remove-child` | `"ИмяПодсистемы"` | Remove a child subsystem |
| `set-property` | `{"name":"prop","value":"val"}` | Change a property (Synonym, IncludeInCommandInterface, UseOneCommand, etc.) |

## Examples

```bash
# Добавить объект в состав
... -SubsystemPath Subsystems/Продажи.xml -Operation add-content -Value "Document.Заказ"

# Добавить несколько объектов
... -SubsystemPath Subsystems/Продажи.xml -Operation add-content -Value '["Catalog.Товары","Report.Продажи"]'

# Удалить объект из состава
... -SubsystemPath Subsystems/Продажи.xml -Operation remove-content -Value "Report.Старый"

# Добавить дочернюю подсистему
... -SubsystemPath Subsystems/Продажи.xml -Operation add-child -Value "НоваяДочерняя"

# Изменить свойство
... -SubsystemPath Subsystems/Продажи.xml -Operation set-property -Value '{"name":"IncludeInCommandInterface","value":"false"}'
```
