---
name: form-validate
description: Validate a 1C managed form. Use after creating or modifying a form to check correctness. If a BaseForm is present, automatically checks callType and extension IDs
argument-hint: <FormPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /form-validate - validating a 1C managed form

Checks Form.xml for structural errors: ID uniqueness, presence of companion elements, correctness of DataPath and command references.

## Parameters

| Parameter | Req.  | Def.    | Description                             |
|-----------|:-----:|---------|-----------------------------------------|
| FormPath  | yes   | -       | Path to the Form.xml file               |
| Detailed  | no    | -       | Detailed output (all checks, including successful ones) |
| MaxErrors | no    | 30      | Stop after N errors                     |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-validate.py" -FormPath "Catalogs/Номенклатура/Forms/ФормаЭлемента"
python "${CLAUDE_SKILL_DIR}/scripts/form-validate.py" -FormPath "src/МояОбработка/Forms/Форма/Ext/Form.xml"
```

