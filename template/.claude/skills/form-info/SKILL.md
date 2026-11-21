---
name: form-info
description: Analyze the structure of a 1C managed form (Form.xml) - elements, attributes, commands, events. Use to understand a form - when writing the form module, analyzing handlers and elements
argument-hint: <FormPath>
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /form-info - Compact form summary

Reads Form.xml and outputs the element tree, attributes with types, commands, events. Replaces reading thousands of lines of XML.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-info.py" -FormPath "<путь к Form.xml>"
```

## Parameters

| Parameter | Required | Description |
|----------|:------------:|----------|
| FormPath | yes | Path to the Form.xml file |
| Expand   | no | Expand a collapsed section by name or title, `*` - all |
| Limit    | no | Max lines (default 150) |
| Offset   | no | Skip N lines (pagination) |

The output is self-documenting. `[Group:AH]`/`[Group:AV]` = AlwaysHorizontal/AlwaysVertical.
