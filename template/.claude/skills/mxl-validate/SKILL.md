---
name: mxl-validate
description: Validate a spreadsheet document (MXL) template. Use after creating or modifying a template to check correctness
argument-hint: <TemplatePath> [-Detailed] [-MaxErrors 20]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /mxl-validate - spreadsheet document (MXL) template validation

Checks Template.xml for structural errors: indexes, palette references, named area and merge ranges, consistency of input field cells.

## Parameters

| Parameter     | Req.  | Default | Description                                |
|---------------|:-----:|---------|--------------------------------------------|
| TemplatePath  | yes   | -       | Path to the template (directory or Template.xml) |
| Detailed      | no    | -       | Detailed output (all checks, including successful ones) |
| MaxErrors     | no    | 20      | Stop after N errors                        |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/mxl-validate.py" -TemplatePath "Catalogs/Номенклатура/Templates/Макет"
python "${CLAUDE_SKILL_DIR}/scripts/mxl-validate.py" -TemplatePath "src/МояОбработка/Templates/ПечатнаяФорма"
```
