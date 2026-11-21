---
name: v8-xsd-fetch
description: Downloading 1C XML dump format XSD schemas by format version into the project directory. Use when you need to download or update platform schemas for validating a dump by XSD, or find out which schema versions are available
argument-hint: "[-Versions 2.20,2.21] [-List]"
allowed-tools:
  - Bash
  - Read
---

# /v8-xsd-fetch - Platform XSD schemas

Downloads XSD schemas of the dump format by format version into the project schema directory
(`.v8-xsd` next to `.v8-project.json`, or the path from its `xsdPath` key).

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/v8-xsd-fetch.py" -Versions "2.20"
```

| Parameter | Description |
|----------|----------|
| `-Versions "<список>"` | Format versions, comma-separated. Without it - all available (about 600 KB per version) |
| `-List` | Show available versions and which are already downloaded, without downloading anything |
| `-OutPath <путь>` | Another schema directory - only if the user named it |
| `-Force` | Re-download already downloaded files |

## Which version to take

The format version is the `version` attribute of the dump's `Configuration.xml` root (for example,
`2.20`), not the platform release number. Download the dump versions the project works with.

Do not add the schema directory to Git: if the project is a repository, the directory must be in `.gitignore`.

No network - tell the user: schemas can be copied manually from the
`schemas/designer/<версия>/` directories of the repository https://github.com/yellow-hammer/namespace-forest.
