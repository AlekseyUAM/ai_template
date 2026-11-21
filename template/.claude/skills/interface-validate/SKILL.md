---
name: interface-validate
description: Validate the 1C command interface. Use after setting up a subsystem command interface to verify correctness
argument-hint: <CIPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /interface-validate - validation of CommandInterface.xml

Checks the command interface XML for structural errors: root element, allowed sections, order, command reference format, duplicates.

## Parameters

| Parameter | Req. | Default | Description                             |
|-----------|:-----:|---------|-----------------------------------------|
| CIPath    | yes   | -       | Path to CommandInterface.xml            |
| Detailed  | no    | -       | Verbose output (all checks, including successful ones) |
| MaxErrors | no    | 30      | Stop after N errors                     |
| OutFile   | no    | -       | Write the result to a file (UTF-8 BOM)  |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/interface-validate.py" -CIPath "Subsystems/Продажи"
python "${CLAUDE_SKILL_DIR}/scripts/interface-validate.py" -CIPath "Subsystems/Продажи/Ext/CommandInterface.xml"
```
