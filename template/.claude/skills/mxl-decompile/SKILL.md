---
name: mxl-decompile
description: Decompile a spreadsheet document (MXL) into a JSON definition. Use when you need to get an editable description of an existing template
argument-hint: -TemplatePath <path> [-OutputPath <path>]
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /mxl-decompile - Template decompiler to DSL

Accepts Template.xml of a 1C spreadsheet document and generates a compact JSON definition (DSL). The reverse of `/mxl-compile`.

## Usage

```
/mxl-decompile <TemplatePath> [OutputPath]
```

## Parameters

| Parameter    | Required     | Description                             |
|--------------|:------------:|-----------------------------------------|
| TemplatePath | yes          | Path to Template.xml                    |
| OutputPath   | no           | Path for JSON (if not set - stdout)     |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/mxl-decompile.py" -TemplatePath "<путь>/Template.xml" [-OutputPath "<путь>.json"]
```

## Workflow

Decompile an existing template for analysis or rework:

1. Call `/mxl-decompile` to get JSON from Template.xml
2. Analyze or modify the JSON (add areas, change styles)
3. Call `/mxl-compile` to generate a new Template.xml
4. Call `/mxl-validate` for validation

The output JSON format is the same DSL that `/mxl-compile` accepts; its description lives in the `/mxl-compile` skill.

## Keys not in the DSL description

The parsed template contains keys that are not in the `/mxl-compile` instructions: for example,
`rowStyle` has an `apply` modifier, an input field cell has `controlType: "none"`. They carry
state of the source file that cannot be expressed otherwise. You do not need to write them yourself; do not delete them
from the parsed JSON either: the compiler accepts them back as is, and without them the template
will change.

## What to know about rebuilding

Editing via the DSL is a full regeneration of the template, not a point change of XML. Therefore
the diff after a "decompile -> compile" cycle is usually wider than the actual rework, even when
the content is preserved in full.

Byte-for-byte matching with the original is not always to be expected. Templates that were edited for a long time
in Configurator retain traces of previous states: for example, a cell format carries a column width
that has changed since then. Such values are not derived from the resulting document,
and they do not return to the rebuilt file.

They do not survive the cycle at all (they do not get into JSON, they do not return to XML):

- merges not tied to a cell - across the whole height or width of the document;
- chart settings (`Chart`, `GanttChart`) - the drawing itself is preserved, its content is not;
- the print area.

If the task is to keep someone else's template as is and fix a little in it, verify the result
with `/mxl-info` or a diff: the items listed above must be restored by hand.
