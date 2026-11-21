# Form Presets

Presets control the layout of forms generated in `--from-object` mode.

## How it works

The merge chain (each next level overrides the previous one via deep merge):

1. **Hardcoded defaults** -- built into the script, ERP-oriented
2. **Built-in preset** -- a file from this folder (`erp-standard.json` by default)
3. **Project-level preset** -- the file `presets/skills/form/<name>.json`, searched upwards from OutputPath

The preset name is set by the `--preset` parameter (default `erp-standard`).

## Project-level preset

To override the standard preset in your project, create the file:

```
<project-root>/presets/skills/form/erp-standard.json
```

The script searches for this file going up from OutputPath to the root. The first file found is applied on top of the built-in one via deep merge -- you do not need to copy the whole preset, just specify the keys to override.

## Sections

The top-level keys in JSON are sections of the form `{тип}.{назначение}`:

| Section | Object type | Form purpose |
|--------|-------------|------------------|
| `document.item` | Document | Document form |
| `document.list` | Document | List form |
| `document.choice` | Document | Choice form |
| `catalog.item` | Catalog | Item form |
| `catalog.folder` | Catalog | Folder form |
| `catalog.list` | Catalog | List form |
| `catalog.choice` | Catalog | Choice form |
| `informationRegister.record` | InformationRegister | Record form |
| `informationRegister.list` | InformationRegister | List form |
| `accumulationRegister.list` | AccumulationRegister | List form |
| `chartOfCharacteristicTypes.*` | ChartOfCharacteristicTypes | item/folder/list/choice |
| `exchangePlan.*` | ExchangePlan | item/list/choice |
| `chartOfAccounts.*` | ChartOfAccounts | item/folder/list/choice |

### basedOn

A section can inherit from another:

```json
{
  "document.choice": {
    "basedOn": "document.list",
    "properties": { "windowOpeningMode": "LockOwnerWindow" }
  }
}
```

## Section keys

### Object form (Item/Record)

| Key | Description | Allowed values |
|------|----------|---------------------|
| `header.position` | Where to place the header | `"insidePage"` -- on the first page, `"abovePages"` -- above the pages |
| `header.layout` | Header columns | `"1col"`, `"2col"` |
| `header.distribute` | Distribution in 2 columns | `"even"`, `"left"`, `"right"` |
| `header.dateTitle` | Date title (Document) | string, e.g. `"от"` |
| `footer.fields` | Fields in the footer | array of attribute names, e.g. `["Комментарий"]` |
| `footer.position` | Where to place the footer | `"insidePage"`, `"belowPages"`, `"none"` |
| `tabularSections.container` | Tabular section container | `"pages"` -- on tabs, `"inline"` -- at the root, `"single-no-pages"` -- one tabular section without pages |
| `tabularSections.exclude` | Exclude tabular sections | array of names, e.g. `["ДополнительныеРеквизиты"]` |
| `tabularSections.lineNumber` | LineNumber column | `true` / `false` |
| `additional.position` | Additional attributes block | `"page"` -- a separate tab, `"below"` -- below the tabular sections, `"none"` -- do not create |
| `additional.layout` | Additional block columns | `"1col"`, `"2col"` |
| `additional.bspGroup` | Group ДополнительныеРеквизиты | `true` / `false` |
| `codeDescription.layout` | Code + Description | `"horizontal"`, `"vertical"` |
| `codeDescription.order` | Code/Description order | `"descriptionFirst"`, `"codeFirst"` |
| `parent.title` | Родитель field title | string, e.g. `"Входит в группу"` |
| `parent.position` | Родитель field position | `"beforeCodeDescription"`, `"afterCodeDescription"`, `"inHeader"` |
| `owner.readOnly` | Owner read-only | `true` / `false` |
| `owner.position` | Владелец field position | `"first"` |
| `fieldDefaults.ref.choiceButton` | Choice button for references | `true` / `false` |
| `fieldDefaults.boolean.element` | Element for Boolean | `"check"` (checkbox) |
| `commandBar` | Form command bar | `"auto"`, `"none"` |
| `properties` | Form properties | object: `autoTitle`, `windowOpeningMode` and others |

### List form (List/Choice)

| Key | Description | Allowed values |
|------|----------|---------------------|
| `columns` | Which columns to show | `"all"` -- all attributes, or an array of names |
| `columnType` | Column element type | `"labelField"`, `"input"` |
| `hiddenRef` | Hidden Ref column | `true` / `false` |
| `tableCommandBar` | Table command bar | `"auto"`, `"none"` |
| `commandBar` | Form command bar | `"auto"`, `"none"` |
| `choiceMode` | Choice mode (ChoiceForm) | `true` / `false` |
| `properties` | Form properties | object: `windowOpeningMode` and others |

## Example of a project-level preset

```json
{
  "name": "my-project",
  "description": "Стиль форм нашего проекта",

  "document.item": {
    "header": {
      "layout": "1col"
    },
    "tabularSections": {
      "exclude": ["ДополнительныеРеквизиты", "СведенияОСертификатах"]
    },
    "additional": {
      "position": "none"
    }
  },

  "catalog.item": {
    "codeDescription": {
      "order": "codeFirst"
    }
  }
}
```

This file overrides only the specified keys -- the rest is inherited from the built-in preset.
