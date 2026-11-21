---
name: erf-validate
description: Validation of a 1C external report (ERF). Use after creating or modifying a report to check correctness
argument-hint: <ObjectPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /erf-validate - external report (ERF) validation

Checks the structural correctness of the external report XML sources: root structure, InternalInfo, properties (including MainDataCompositionSchema), ChildObjects, attributes, tabular sections, name uniqueness, presence of form and template files.

Uses the same script as `/epf-validate` - auto-detection by element type (ExternalReport).

XML is checked. Module syntax is checked by the build: skill `1c-batch` (command `build-epf`).

## Parameters

| Parameter   | Req. | Default | Description                                      |
|------------|:-----:|---------|-------------------------------------------------|
| ObjectPath | yes   | -       | Path to the root XML or the report directory        |
| Detailed   | no    | -       | Detailed output (all checks, including successful ones) |
| MaxErrors  | no    | 30      | Stop after N errors                     |
| OutFile    | no    | -       | Write the result to a file (UTF-8 BOM)           |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/../epf-validate/scripts/epf-validate.py" -ObjectPath "src/МойОтчёт"
python "${CLAUDE_SKILL_DIR}/../epf-validate/scripts/epf-validate.py" -ObjectPath "src/МойОтчёт/МойОтчёт.xml"
```
