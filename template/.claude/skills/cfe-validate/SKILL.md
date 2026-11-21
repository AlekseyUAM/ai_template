---
name: cfe-validate
description: Validation of a 1C configuration extension (CFE). Use after creating or modifying an extension to check correctness
argument-hint: <ExtensionPath> [-ConfigPath <ConfigDir>] [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-validate - configuration extension (CFE) validation

Checks the structural correctness of the extension: XML format, properties, composition, borrowed objects, role rights. An analog of `/cf-validate`, but for extensions.

Sources are checked. Applicability is after loading into the infobase: `/db-cfe-admin check`.

## Parameters

| Parameter      | Req. | Default | Description                                        |
|---------------|:-----:|---------|-------------------------------------------------|
| ExtensionPath | yes   | -       | Path to the extension directory or Configuration.xml |
| ConfigPath    | no    | -       | Configuration directory from which objects were borrowed |
| Detailed      | no    | -       | Detailed output (all checks, including successful ones)  |
| MaxErrors     | no    | 30      | Stop after N errors                      |
| OutFile       | no    | -       | Write the result to a file                        |

### ConfigPath

Always specify it when the source configuration is available: without it some errors of borrowed forms are not caught, and the extension may pass validation and then be rejected by the platform on load.

If the user did not specify the path - determine it yourself:
1. Read `.v8-project.json` from the project root
2. Resolve the target infobase (by name, branch or `default`)
3. Take its `configSrc` field

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname"
python "${CLAUDE_SKILL_DIR}/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname\Configuration.xml"
python "${CLAUDE_SKILL_DIR}/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname" -ConfigPath "src\cf"
```
