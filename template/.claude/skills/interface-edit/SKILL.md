---
name: interface-edit
description: Set up the command interface of a 1C subsystem. Use when you need to hide or show commands, place them in groups, set order
argument-hint: <CIPath> <Operation> <Value>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /interface-edit - editing CommandInterface.xml

Point edits of a 1C subsystem command interface file.

## Parameters

| Parameter | Req. | Description |
|----------|:-----:|----------|
| CIPath | yes | Path to CommandInterface.xml |
| Operation | no | Operation: hide, show, place, order, subsystem-order, group-order |
| Value | no | Value for the operation |
| DefinitionFile | no | JSON file with an array of operations (alternative to Operation) |
| CreateIfMissing | no | Create the file if it does not exist |
| NoValidate | no | Skip auto-validation |

## Command

### Inline mode

```bash
python "${CLAUDE_SKILL_DIR}/scripts/interface-edit.py" -CIPath '<path>' -Operation hide -Value '<cmd>'
```

### JSON mode

```bash
python "${CLAUDE_SKILL_DIR}/scripts/interface-edit.py" -CIPath '<path>' -DefinitionFile '<json>'
```

## Operations

| Operation | Value | Description |
|----------|----------|----------|
| hide | Cmd.Name or array | Hide a command (CommandsVisibility, false) |
| show | Cmd.Name or array | Show a command (visibility, true) |
| place | {"command":"...","group":"CommandGroup.X"} | Place a command in a group |
| order | {"group":"...","commands":[...]} | Set command order in a group |
| subsystem-order | ["Subsystem.X.Subsystem.A",...] | Order of child subsystems |
| group-order | ["NavigationPanelOrdinary",...] | Order of groups |

## Examples

```bash
# Скрыть команду
... -CIPath Subsystems/Продажи/Ext/CommandInterface.xml -Operation hide -Value "Catalog.Товары.StandardCommand.OpenList"

# Показать команду
... -Operation show -Value "Report.Продажи.Command.Отчёт"

# Разместить в группе
... -Operation place -Value '{"command":"Report.X.Command.Y","group":"CommandGroup.Отчеты"}'

# Задать порядок подсистем
... -Operation subsystem-order -Value '["Subsystem.X.Subsystem.A","Subsystem.X.Subsystem.B"]'

# Создать новый CI
... -CIPath <new-path> -Operation subsystem-order -Value '[...]' -CreateIfMissing
```

## Verification

```
/interface-validate <CIPath>
```
