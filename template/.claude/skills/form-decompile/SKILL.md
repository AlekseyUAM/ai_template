---
name: form-decompile
description: Decompile a 1C managed form (Form.xml) into a JSON draft in form-compile format. Use to scaffold a new form from a sample or for structural refactoring. Not for point edits
argument-hint: <FormPath> [-OutputPath <out.json>]
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /form-decompile - JSON draft from a managed form's Form.xml

Reads Form.xml and emits compact JSON in the `form-compile` format. **The result is a draft**, not a reversible representation: see the "What you get" section.

## When to use

- **Scaffold a new form from a sample** - take an existing form, get JSON, adjust it and compile it into a new one.
- **Structural refactoring** - iterate over the element tree, attributes, commands.

## When **not** to use

- **Point edits of a ready form** (add an element, attribute, command) -> `/form-edit`. The "decompile -> edit JSON -> compile" cycle rewrites the whole form, may lose unsupported constructs and produces a big diff. `/form-edit` edits surgically.

## Parameters

| Parameter | Description |
|----------|----------|
| `FormPath` | Path to Form.xml (required) |
| `OutputPath` | Path to the output JSON. If not set - JSON to stdout |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-decompile.py" -FormPath "<Form.xml>" -OutputPath "<out.json>"
```

## What you get

A JSON draft in the `/form-compile` format - **not a full reversible representation**: the roundtrip `xml → json → xml` is not guaranteed, some DSL constructs are not covered and are **lost silently**.

Critical constructs (`ConditionalAppearance` with scope, design-time charts/schedulers on an attribute, unknown element type, non-Form root) -> the script fails with a non-zero code and a message on stderr; to edit such a form use `/form-edit`.

## Workflow

1. `/form-decompile <Form.xml> -OutputPath draft.json` - get a draft.
2. Adjust the JSON for the task.
3. `/form-compile -JsonPath draft.json -OutputPath new/Form.xml` - assemble it back.
4. `/form-validate` + `/form-info` - check the result.
