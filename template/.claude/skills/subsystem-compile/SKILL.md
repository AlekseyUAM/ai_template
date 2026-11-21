---
name: subsystem-compile
description: Create a 1C subsystem - XML sources from a JSON definition. Use when you need to add a subsystem (section) to the configuration
argument-hint: "[-DefinitionFile <json> | -Value <json-string>] -OutputDir <ConfigDir> [-Parent <path>]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /subsystem-compile - generate a subsystem from JSON

Takes a JSON subsystem definition → generates XML + file structure + registers it in the parent (Configuration.xml or a parent subsystem).

## Parameters and command

| Parameter | Description |
|----------|----------|
| `DefinitionFile` | Path to the JSON definition file |
| `Value` | Inline JSON string (alternative to DefinitionFile) |
| `OutputDir` | Dump root (where `Subsystems/`, `Configuration.xml` are) |
| `Parent` | Path to the parent subsystem XML (for nested ones) |
| `NoValidate` | Skip auto-validation |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/subsystem-compile.py" -Value '<json>' -OutputDir '<ConfigDir>'
```

## JSON definition

```json
{
  "name": "МояПодсистема",
  "synonym": "Моя подсистема",
  "comment": "",
  "includeInCommandInterface": true,
  "useOneCommand": false,
  "explanation": "Описание раздела",
  "picture": "CommonPicture.МояКартинка",
  "content": ["Catalog.Товары", "Document.Заказ"]
}
```

Minimal: only `name`. Everything else has defaults.

## Examples

```bash
# Минимальная подсистема
... -Value '{"name":"Тест"}' -OutputDir config/

# С составом и картинкой
... -Value '{"name":"Продажи","content":["Catalog.Товары","Report.Продажи"],"picture":"CommonPicture.Продажи"}' -OutputDir config/

# Вложенная подсистема
... -Value '{"name":"Дочерняя"}' -OutputDir config/ -Parent config/Subsystems/Продажи.xml
```
