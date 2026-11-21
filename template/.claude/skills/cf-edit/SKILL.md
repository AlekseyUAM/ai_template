---
name: cf-edit
description: Pointwise editing of a 1C configuration. Use when you need to change configuration properties, add or remove an object from the composition, set up default roles, change panel layout, set up the home page
argument-hint: -ConfigPath <path> -Operation <op> -Value <value>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /cf-edit - 1C configuration editing

Pointwise editing of Configuration.xml: properties, ChildObjects composition, default roles.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `ConfigPath` | Path to Configuration.xml or the export directory |
| `Operation` | Operation (see the table) |
| `Value` | Value for the operation (batch via `;;`) |
| `DefinitionFile` | JSON file with an array of operations |
| `NoValidate` | Skip auto-validation |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cf-edit.py" -ConfigPath '<path>' -Operation modify-property -Value 'Version=1.0.0.1'
```

## Operations

| Operation | Value format | Description |
|----------|-------------|----------|
| `modify-property` | `Ключ=Значение` (batch `;;`) | Change a property |
| `add-childObject` | `Type.Name` (batch `;;`) | Register an already existing object file in ChildObjects. To create a new object use `/meta-compile`, `/role-compile`, `/subsystem-compile` - they register automatically |
| `remove-childObject` | `Type.Name` (batch `;;`) | Remove an object from ChildObjects |
| `sort-childObjects` | kind, e.g. `Catalog` (batch `;;`), or empty | Sort ChildObjects by name within a kind. Without a value - all kinds except four (see reference) |
| `add-defaultRole` | `Role.Name` or `Name` | Add a default role |
| `remove-defaultRole` | `Role.Name` or `Name` | Remove a default role |
| `set-defaultRoles` | Names via `;;` | Replace the list of default roles |
| `set-panels` | JSON object (see [reference.md](reference.md)) | Overwrite `Ext/ClientApplicationInterface.xml` (panel layout) |
| `set-home-page` | JSON object (see [reference.md](reference.md)) | Overwrite `Ext/HomePageWorkArea.xml` (home page) |

Allowed property values, DefinitionFile (JSON) format, canonical order: [reference.md](reference.md)

## Examples

```bash
# Изменить версию и поставщика
... -ConfigPath src -Operation modify-property -Value "Version=1.0.0.1 ;; Vendor=Фирма 1С"

# Добавить объекты
... -ConfigPath src -Operation add-childObject -Value "Catalog.Товары ;; Document.Заказ"

# Удалить объект
... -ConfigPath src -Operation remove-childObject -Value "Catalog.Устаревший"

# Роли по умолчанию
... -ConfigPath src -Operation add-defaultRole -Value "ПолныеПрава"
... -ConfigPath src -Operation set-defaultRoles -Value "ПолныеПрава ;; Администратор"
```
