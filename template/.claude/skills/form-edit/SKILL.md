---
name: form-edit
description: Add elements, attributes and commands to an existing 1C managed form. Use when you need to modify a ready form pointwise
argument-hint: <FormPath> <JsonPath>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /form-edit - Editing a form

Adds elements, attributes and/or commands to an existing Form.xml. Automatically allocates IDs from the correct pool, generates companion elements (ContextMenu, ExtendedTooltip, etc.) and event handlers.

## Usage

```
/form-edit <FormPath> <JsonPath>
```

## Parameters

| Parameter | Required     | Description                      |
|-----------|:------------:|----------------------------------|
| FormPath  | yes          | Path to the existing Form.xml    |
| JsonPath  | yes          | Path to the JSON with the additions |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/form-edit.py" -FormPath "<путь>" -JsonPath "<путь>"
```

## JSON format

```json
{
  "into": "ГруппаШапка",
  "after": "Контрагент",
  "elements": [
    { "input": "Склад", "path": "Объект.Склад", "on": ["OnChange"] }
  ],
  "attributes": [
    { "name": "СуммаИтого", "type": "decimal(15,2)" }
  ],
  "commands": [
    { "name": "Рассчитать", "action": "РассчитатьОбработка" }
  ]
}
```

### Extensions (extension forms)

For borrowed forms (with `<BaseForm>`) extension mode is activated automatically: IDs start at 1000000+. Additional sections are available:

```json
{
  "formEvents": [
    { "name": "OnCreateAtServer", "handler": "Расш1_ПриСозданииПосле", "callType": "After" },
    { "name": "OnOpen", "handler": "Расш1_ПриОткрытии", "callType": "Before" }
  ],
  "elementEvents": [
    { "element": "Банк", "name": "OnChange", "handler": "Расш1_БанкПриИзменении", "callType": "Before" }
  ],
  "commands": [
    { "name": "Подбор", "action": "Расш1_ПодборПосле", "callType": "After" },
    { "name": "Запрос", "actions": [
      { "callType": "Before", "handler": "Расш1_ЗапросПеред" },
      { "callType": "After", "handler": "Расш1_ЗапросПосле" }
    ]}
  ],
  "elements": [
    { "input": "Поле", "path": "Объект.Поле", "on": [{ "event": "OnChange", "callType": "After" }] }
  ]
}
```

### Element positioning

| Key | Default | Description |
|------|-------------|----------|
| `into` | root ChildItems | Name of the group/table/page to insert into |
| `after` | at the end | Name of the element to insert after |

### Element types

Same DSL keys as in `/form-compile`:

| Key | XML tag | Companions |
|------|---------|------------|
| `input` | InputField | ContextMenu, ExtendedTooltip |
| `check` | CheckBoxField | ContextMenu, ExtendedTooltip |
| `label` | LabelDecoration | ContextMenu, ExtendedTooltip |
| `labelField` | LabelField | ContextMenu, ExtendedTooltip |
| `group` | UsualGroup | ExtendedTooltip |
| `table` | Table | ContextMenu, AutoCommandBar, Search*, ViewStatus* |
| `pages` | Pages | ExtendedTooltip |
| `page` | Page | ExtendedTooltip |
| `button` | Button | ExtendedTooltip |

Groups and tables support `children`/`columns` for nested elements.

### Buttons: command and stdCommand

- `"command": "ИмяКоманды"` -> `Form.Command.ИмяКоманды`
- `"stdCommand": "Close"` -> `Form.StandardCommand.Close`
- `"stdCommand": "Товары.Add"` -> `Form.Item.Товары.StandardCommand.Add` (standard command of the element)

### Valid events (`on`)

The compiler warns about errors in event names. Main ones:

- **input**: `OnChange`, `StartChoice`, `ChoiceProcessing`, `Clearing`, `AutoComplete`, `TextEditEnd`
- **check**: `OnChange`
- **table**: `OnStartEdit`, `OnEditEnd`, `OnChange`, `Selection`, `BeforeAddRow`, `BeforeDeleteRow`, `OnActivateRow`
- **label/picture**: `Click`, `URLProcessing`
- **pages**: `OnCurrentPageChange`
- **button**: `Click`

### Type system (for attributes)

`string`, `string(100)`, `decimal(15,2)`, `boolean`, `date`, `dateTime`, `CatalogRef.XXX`, `DocumentObject.XXX`, `ValueTable`, `DynamicList`, `Type1 | Type2` (composite).

### Extension sections

| Section | Purpose |
|--------|-----------|
| `formEvents` | Form-level events with `callType` (Before/After/Override) |
| `elementEvents` | Events on existing elements of the borrowed form |
| `callType` on `commands` | callType on the command's Action |
| `callType` on `on` | callType on events of new elements (object format) |

All extension sections are optional - without them the skill works as with regular forms.

## Workflow

1. `/form-info` - view the current form structure
2. Create a JSON with the additions
3. `/form-edit` - add to the form
4. `/form-validate` - check correctness
5. `/form-info` - make sure the additions are correct
