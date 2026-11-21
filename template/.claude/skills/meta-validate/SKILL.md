---
name: meta-validate
description: Validate a 1C metadata object. Use after creating or modifying a configuration object to check correctness
argument-hint: <ObjectPath> [-Detailed] [-MaxErrors 30] — pipe-separated paths for batch
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /meta-validate - 1C metadata object validation

Checks metadata object XML from a configuration dump for structural errors.

## Parameters

| Parameter   | Required | Default | Description                                      |
|------------|:-----:|---------|-------------------------------------------------|
| ObjectPath | yes    | -       | Path to the XML file or directory. Via `\|` for batch |
| Detailed   | no   | -       | Detailed output (all checks, including successful ones) |
| MaxErrors  | no   | 30      | Stop after N errors (per object)        |
| OutFile    | no   | -       | Write the result to a file (UTF-8 BOM)           |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-validate.py" -ObjectPath "Catalogs/Номенклатура/Номенклатура.xml"
python "${CLAUDE_SKILL_DIR}/scripts/meta-validate.py" -ObjectPath "Catalogs/Банки|Documents/Заказ"
```
