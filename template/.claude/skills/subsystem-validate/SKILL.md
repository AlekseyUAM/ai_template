---
name: subsystem-validate
description: Validate a 1C subsystem. Use after creating or modifying a subsystem to verify correctness
argument-hint: <SubsystemPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /subsystem-validate - validation of a 1C subsystem

Checks structural correctness of the subsystem XML file from a configuration dump.

## Parameters

| Parameter     | Req. | Default | Description                               |
|---------------|:-----:|---------|-------------------------------------------|
| SubsystemPath | yes   | -       | Path to the subsystem XML file            |
| Detailed      | no    | -       | Verbose output (all checks, including successful ones) |
| MaxErrors     | no    | 30      | Stop after N errors                       |
| OutFile       | no    | -       | Write the result to a file                |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/subsystem-validate.py" -SubsystemPath "Subsystems/Продажи"
python "${CLAUDE_SKILL_DIR}/scripts/subsystem-validate.py" -SubsystemPath "Subsystems/Продажи.xml"
```
