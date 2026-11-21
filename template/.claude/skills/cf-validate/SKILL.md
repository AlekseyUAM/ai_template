---
name: cf-validate
description: Validation of a 1C configuration. Use after creating or modifying a configuration to check correctness
argument-hint: <ConfigPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cf-validate - 1C configuration validation

Checks Configuration.xml for structural errors: XML well-formedness, InternalInfo, properties, enum values, ChildObjects, DefaultLanguage, language files, object directories.

## Parameters

| Parameter   | Req. | Default | Description                                      |
|------------|:-----:|---------|-------------------------------------------------|
| ConfigPath | yes   | -       | Path to Configuration.xml or the export directory  |
| Detailed   | no    | -       | Detailed output (all checks, including successful ones) |
| MaxErrors  | no    | 30      | Stop after N errors                     |
| OutFile    | no    | -       | Write the result to a file (UTF-8 BOM)           |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cf-validate.py" -ConfigPath "upload/cfempty"
python "${CLAUDE_SKILL_DIR}/scripts/cf-validate.py" -ConfigPath "upload/cfempty/Configuration.xml"
```
