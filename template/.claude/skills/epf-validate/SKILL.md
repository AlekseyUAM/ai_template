---
name: epf-validate
description: Validation of a 1C external data processor (EPF). Use after creating or modifying a data processor to check correctness
argument-hint: <ObjectPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /epf-validate - external data processor (EPF) validation

Checks the structural correctness of the external data processor XML sources: root structure, InternalInfo, properties, ChildObjects, attributes, tabular sections, name uniqueness, presence of form and template files. Also works for external reports (ERF).

XML is checked. Module syntax is checked by the build: skill `1c-batch` (command `build-epf`).

## Parameters

| Parameter   | Req. | Default | Description                                      |
|------------|:-----:|---------|-------------------------------------------------|
| ObjectPath | yes   | -       | Path to the root XML or the data processor directory     |
| Detailed   | no    | -       | Detailed output (all checks, including successful ones) |
| MaxErrors  | no    | 30      | Stop after N errors                     |
| OutFile    | no    | -       | Write the result to a file (UTF-8 BOM)           |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/epf-validate.py" -ObjectPath "src/МояОбработка"
python "${CLAUDE_SKILL_DIR}/scripts/epf-validate.py" -ObjectPath "src/МояОбработка/МояОбработка.xml"
```
