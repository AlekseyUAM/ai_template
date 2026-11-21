---
name: template-remove
description: Delete a template from a 1C object (data processor, report, catalog, document, etc.)
argument-hint: <ObjectName> <TemplateName>
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /template-remove - Delete a template

Deletes the template and removes its registration from the object's root XML.

## Usage

```
/template-remove <ObjectName> <TemplateName>
```

| Parameter    | Required | Default | Description                |
|--------------|:------------:|--------------|-------------------------------------|
| ObjectName   | yes          | -            | Object name                |
| TemplateName | yes          | -            | Template name to delete    |
| SrcDir       | no           | `src`        | Source directory           |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/template-remove.py" -ObjectName "<ObjectName>" -TemplateName "<TemplateName>" [-SrcDir "<SrcDir>"]
```

## What is deleted

```
<SrcDir>/<ObjectName>/Templates/<TemplateName>.xml     # Метаданные макета
<SrcDir>/<ObjectName>/Templates/<TemplateName>/         # Каталог макета (рекурсивно)
```

## What is modified

- `<SrcDir>/<ObjectName>.xml` - `<Template>` is removed from `ChildObjects`
- For ExternalReport/Report: if the deleted template was specified in `MainDataCompositionSchema`, the value is cleared
