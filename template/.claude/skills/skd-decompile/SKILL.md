---
name: skd-decompile
description: Decompile a 1C data composition schema (DCS) into a JSON draft in skd-compile format. Use for scaffolding a new report from an example or for structural refactoring. Not for point edits
argument-hint: <TemplatePath> [-OutputPath <out.json>]
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /skd-decompile - JSON draft from DCS Template.xml

Reads Template.xml and emits JSON in the `skd-compile` format. **The result is a draft**, not a reversible representation: see the "What you get" section.

## When to use

- **Scaffold a new report from an example** - take an existing DCS, get JSON, fix it and compile into a new one.
- **Structural refactoring** - rewrite a variant, redraw a template, rework a field set.

## When **not** to use

- **Point edits of a finished report** (add a field, filter, total, rename) -> `/skd-edit`. The "decompile -> edit JSON -> compile" cycle rewrites the template entirely, may lose uncovered constructs and produces a large diff in the sources. `/skd-edit` edits locally, without full reconstruction.

## Parameters

| Parameter | Description |
|----------|----------|
| `TemplatePath` | Path to Template.xml (required) |
| `OutputPath` | Path to the output JSON. If not set - JSON to stdout |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/skd-decompile.py" -TemplatePath "<Template.xml>" -OutputPath "<out.json>"
```

## What you get

A JSON draft in the `/skd-compile` format - **not a complete reversible representation of the DCS**. Such JSON may not go straight into the compiler: it contains sentinel nodes (the `__unsupported__` marker).

- **Ready nodes** - most of the DCS (fields, parameters, templates, variants with structure/filter/order/conditionalAppearance, etc.) maps into JSON as regular DSL nodes.
- **Sentinel nodes** - places where a construct occurred that the decompiler cannot express in the DSL. The JSON remains valid, but the compiler will refuse to build it until the sentinel is **replaced with a manual implementation** (explicit raw `template`, explicit appearance, etc.) **or removed**, if the construct is not needed in the new report. This is a deliberate barrier - so that uncovered items do not end up in the final report unnoticed.
- **`<basename>.warnings.md`** next to `OutputPath` - a list of all sentinel nodes with coordinates in the source; it is convenient for walking through places that need manual rework.
- **Critical constructs** (Picture cells, ХранилищеЗначения, nested schemas, non-DCS root) - the script fails with a non-zero code and a message to stderr; such a Template is not suitable as an example.

## Workflow

1. `/skd-decompile <Template.xml> -OutputPath draft.json` - get the draft.
2. Open `draft.warnings.md`, see what was not covered.
3. Fix the JSON for the task. Sentinel nodes - replace with a manual implementation (via explicit raw `template`, via a manual appearance description, etc.) or delete them if the construct is not needed in the new report.
4. `/skd-compile -DefinitionFile draft.json -OutputPath new-Template.xml` - build it back.
5. `/skd-validate` + `/skd-info` - check.
