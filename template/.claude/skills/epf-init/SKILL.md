---
name: epf-init
description: Create an empty 1C external data processor (scaffold XML sources). Use when you need to create a new external data processor from scratch
argument-hint: -Name <Name> [-Synonym <Synonym>] [-SrcDir <SrcDir>] [-FormatVersion <version>]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /epf-init - Creating a new data processor

Generates a minimal set of XML sources for a 1C external data processor: the root metadata file and the data processor directory.

## Usage

```
/epf-init <Name> [Synonym] [SrcDir] [FormatVersion]
```

| Parameter      | Required | Default | Description                                       |
|---------------|:------------:|--------------|------------------------------------------------|
| Name          | yes           | -            | Data processor name (Latin/Cyrillic)             |
| Synonym       | no           | = Name       | Synonym (display name)                     |
| SrcDir        | no           | `src`        | Source directory relative to CWD            |
| FormatVersion | no           | `2.17`       | Export format version - see below              |

`FormatVersion` - **not higher** than the format version of the platform on which the object will be built and opened:
8.3.24 - `2.17`, 8.3.25 - `2.18`, 8.3.26 - `2.19`, 8.3.27 - `2.20`, 8.5 - `2.21`. A lower one may be taken:
the platform reads its own format and any older one, so the default `2.17` fits the whole line of
8.3.24 and higher. For older platforms the count goes the same way, one version per release (8.3.23 - `2.16`),
but the skills were not tested on them - such a value is accepted with a warning.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/epf-init.py" -Name "<Name>" [-Synonym "<Synonym>"] [-SrcDir "<SrcDir>"] [-FormatVersion "<версия>"]
```

## Next steps

- Add a form: `/form-add`
- Add a template: `/template-add`
- Add help: `/help-add`
- Build EPF: skill `1c-batch`, command `build-epf`
