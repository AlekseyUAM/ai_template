---
name: cfe-init
description: Create a 1C configuration extension (CFE) - scaffold XML sources. Use when you need to create a new extension to fix, customize or supplement a configuration
argument-hint: <Name> [-ConfigPath <path>] [-Purpose Patch|Customization|AddOn] [-CompatibilityMode Version8_3_24]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-init - Creating a 1C configuration extension

Creates an extension scaffold: `Configuration.xml`, `Languages/Русский.xml`, optionally `Roles/`.

## Preparation

If there is an export of the base configuration, pass `-ConfigPath` - the script will automatically determine `CompatibilityMode` and the language UUID from the base configuration.

### ConfigPath auto-detection

If the user did not specify `-ConfigPath` - try to detect it automatically:
1. Read `.v8-project.json` from the project root
2. Resolve the target infobase (by name, branch or `default` - the algorithm from `/db-list`)
3. If the infobase has a `configSrc` field - use it as `-ConfigPath`
4. If there is no `configSrc` - ask the user

If `.v8-project.json` is not found and `-ConfigPath` is not set - the extension will be created with a warning (language UUID = zeros, default CompatibilityMode).

## Parameters

| Parameter | Description | Default |
|----------|----------|--------------|
| `Name` | Extension name (required) | - |
| `Synonym` | Synonym | = Name |
| `NamePrefix` | Prefix of own objects | = Name + "_" |
| `OutputDir` | Directory to create; put the extension in its own subdirectory named after it: `src\cfe\<Name>` | `src` |
| `Purpose` | `Patch` (fix) / `Customization` (rework) / `AddOn` (add-on) | `Customization` |
| `Version` | Extension version | - |
| `Vendor` | Vendor | - |
| `CompatibilityMode` | Compatibility mode; when `ConfigPath` is set it is determined from the base configuration and this parameter is not needed | `Version8_3_24` |
| `ConfigPath` | Path to the base configuration export (auto-determines CompatibilityMode and Language UUID) | - |
| `NoRole` | Without the main role | false |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cfe-init.py" -Name "МоёРасширение" -OutputDir "src\cfe\МоёРасширение" -ConfigPath "src\cf"
```

## Examples

```bash
# Расширение для ERP с авто-определением совместимости из базовой конфигурации
... -Name Расш1 -ConfigPath src\cf -OutputDir src\cfe\Расш1

# Расширение-исправление с явным режимом совместимости
... -Name Расш1 -Purpose Patch -CompatibilityMode Version8_3_17 -OutputDir src\cfe\Расш1

# Расширение-доработка с версией
... -Name МоёРасширение -Version "1.0.0.1" -Vendor "Компания" -OutputDir src\cfe\МоёРасширение

# Без роли, с явным префиксом
... -Name ИсправлениеБага -NamePrefix "ИБ_" -Purpose Patch -NoRole -OutputDir src\cfe\ИсправлениеБага
```

## Verification

```
/cfe-validate <OutputDir> -ConfigPath <ConfigPath>
```
