---
name: form-remove
description: Remove a form from a 1C object (data processor, report, catalog, document, etc.)
argument-hint: <ObjectName> <FormName>
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /form-remove - Removing a form

Deletes the form and removes its registration from the object's root XML.

## Usage

```
/form-remove <ObjectName> <FormName>
```

| Parameter  | Required     | Default      | Description                         |
|------------|:------------:|--------------|-------------------------------------|
| ObjectName | yes          | -            | Object name                         |
| FormName   | yes          | -            | Name of the form to delete          |
| SrcDir     | no           | `src`        | Source directory                    |
| Force      | no           | -            | Delete even if the form is referenced, and clear the references |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-remove.py" -ObjectName "<ObjectName>" -FormName "<FormName>" [-SrcDir "<SrcDir>"] [-Force]
```

## What is deleted

```
<SrcDir>/<ObjectName>/Forms/<FormName>.xml     # Метаданные формы
<SrcDir>/<ObjectName>/Forms/<FormName>/         # Каталог формы (рекурсивно)
```

## What is modified

- `<SrcDir>/<ObjectName>.xml` - `<Form>` is removed from `ChildObjects`
- Object properties that pointed to the deleted form are cleared
