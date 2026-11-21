---
name: cf-init
description: Create an empty 1C configuration (scaffold XML sources). Use when you need to start a new configuration from scratch
argument-hint: <Name> [-Synonym <name>] [-OutputDir src]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cf-init - Creating an empty 1C configuration

Creates a scaffold of empty 1C configuration sources: `Configuration.xml`, `Languages/Русский.xml`.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `Name` | Configuration name (required) |
| `Synonym` | Synonym (= Name if not specified) |
| `OutputDir` | Directory to create (default: `src`) |
| `Version` | Configuration version |
| `Vendor` | Vendor |
| `CompatibilityMode` | Compatibility mode (default: `Version8_3_24`) |
| `FormatVersion` | Export format version (default: `2.17`) |

Both parameters are set from the **target platform** - the one the configuration will run on - but by different rules.

`FormatVersion` - **not higher** than the target platform format version: 8.3.24 - `2.17`, 8.3.25 - `2.18`,
8.3.26 - `2.19`, 8.3.27 - `2.20`, 8.5 - `2.21`. A lower one may be taken: the platform reads its own format and any
older one, so the default `2.17` fits the whole 8.3.24 and higher line.

`CompatibilityMode` affects the available functionality. If the task does not say otherwise - **equal to the
target platform** (`Version8_3_27` for 8.3.27); this is the same as "Do not use" in the
Configurator, and this is exactly the value the platform sets for a new infobase. A lower mode is taken
deliberately - when the configuration must also work on older platforms; it disables features that
appeared later. Above the target platform - not allowed: such a configuration will load, but will not work on it.

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cf-init.py" -Name "МояКонфигурация"
```

## Examples

```bash
# Базовая конфигурация
... -Name МояКонфигурация -Synonym "Моя конфигурация" -OutputDir test-tmp/cf

# С версией и поставщиком
... -Name TestCfg -Synonym "Тестовая" -Version "1.0.0.1" -Vendor "Фирма 1С" -OutputDir test-tmp/cf2

# Под платформу 8.3.27 — версия формата и режим совместимости вместе
... -Name TestCfg -FormatVersion 2.20 -CompatibilityMode Version8_3_27 -OutputDir test-tmp/cf3
```

## Verification

```
/cf-init TestConfig -OutputDir test-tmp/cf
/cf-info test-tmp/cf          — проверить созданное
/cf-validate test-tmp/cf      — валидировать
```
