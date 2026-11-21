---
name: erf-init
description: Create an empty 1C external report (scaffold XML sources). Use when you need to create a new external report from scratch
argument-hint: -Name <Name> [-Synonym <Synonym>] [-SrcDir <SrcDir>] [-FormatVersion <version>] [-WithSKD]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /erf-init - Creating a new report

Generates a minimal set of XML sources for a 1C external report: the root metadata file and the report directory.

## Usage

```
/erf-init <Name> [Synonym] [SrcDir] [FormatVersion] [--with-skd]
```

| Parameter      | Required | Default | Description                              |
|---------------|:------------:|--------------|---------------------------------------|
| Name          | yes           | -            | Report name (Latin/Cyrillic)       |
| Synonym       | no           | = Name       | Synonym (display name)            |
| SrcDir        | no           | `src`        | Source directory relative to CWD   |
| FormatVersion | no           | `2.17`       | Export format version - see below              |
| --WithSKD     | no           | -            | Create an empty DCS and bind it to MainDataCompositionSchema |

`FormatVersion` - **not higher** than the format version of the platform on which the object will be built and opened:
8.3.24 - `2.17`, 8.3.25 - `2.18`, 8.3.26 - `2.19`, 8.3.27 - `2.20`, 8.5 - `2.21`. A lower one may be taken:
the platform reads its own format and any older one, so the default `2.17` fits the whole line of
8.3.24 and higher. For older platforms the count goes the same way, one version per release (8.3.23 - `2.16`),
but the skills were not tested on them - such a value is accepted with a warning.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/erf-init.py" -Name "<Name>" [-Synonym "<Synonym>"] [-SrcDir "<SrcDir>"] [-FormatVersion "<версия>"] [-WithSKD]
```

## Next steps

- Add a form: `/form-add`
- Add a template: `/template-add`
- Add help: `/help-add`
- Build ERF: skill `1c-batch`, command `build-epf` (the same command also builds .erf)
