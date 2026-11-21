---
name: meta-decompile
description: Decompile a 1C metadata object into a meta-compile JSON draft. Use when you need to get a DSL description draft of a new object based on another one. Does not preserve UUIDs/modules/forms.
argument-hint: <ObjectPath> [-OutputPath <out.json>]
disable-model-invocation: true
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /meta-decompile - DSL draft from metadata object XML

Reads metadata object XML (`Catalogs/Имя.xml`, etc.) and emits compact JSON in the `/meta-compile` format. The purpose is to **take an existing object as a sample and assemble a NEW one from it**: decompile -> adjust -> compile under a different name.

## ⚠️ Main point: this is NOT a reversible dump

Compiling the draft creates a **new object with a new identity**, not a copy of the original. The JSON does **not** include: UUIDs (the identity of the object itself and all children), module bodies, forms, templates, rights. Only the structure and properties are captured.

Hence the rule: **never compile the draft over the source object and never present it as a "reimport"** - the reassembled object has different UUIDs, so all references to the source object (from code, other objects, subsystem contents, predefined data) will break, and module code and forms will be lost.

## When to use

**Assemble a new object from an existing sample** - get a DSL draft of a working object, rename it and adapt its composition, compile it into a new one. Faster than writing DSL from scratch for a rich object.

## When **not** to use

- **Point edit of an existing object** (add an attribute, tabular section, property) -> `/meta-edit`. The decompile->compile cycle is harmful here: it produces an object with a new identity and loses modules/forms.
- **Save / restore / move the same object** (backup, migration between configurations preserving references) -> the standard 1C dump (`/db-dump-xml` <-> `/db-load-xml`, CF), not decompile.
- **Just understand the object structure** (attributes, tabular sections, types) without reassembly -> `/meta-info` (cheaper, does not create a file).

## Parameters

| Parameter | Description |
|----------|----------|
| `ObjectPath` | Path to the object XML (`Catalogs/Имя.xml`), required |
| `OutputPath` | Path to the output JSON. If not set - JSON to stdout |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/meta-decompile.py" -ObjectPath "<Объект.xml>" -OutputPath "<out.json>"
```

An unsupported object type or a non-`MetaDataObject` root -> a non-zero exit code and a message to stderr.

## Workflow (assembling a new object from a sample)

1. `/meta-decompile <Образец.xml> -OutputPath draft.json` - get a draft.
2. In `draft.json` **change `name`** to the new object name and adapt the composition (attributes/tabular sections/properties). References to *other* objects (owners, based on input, types) are by name and are preserved as is.
3. `/meta-compile -JsonPath draft.json -OutputDir <ConfigDir>` - assemble (the object gets fresh UUIDs).
4. `/meta-validate` + `/meta-info` - validate.
5. Modules, forms, templates, rights - add separately (they are not included in the draft).
