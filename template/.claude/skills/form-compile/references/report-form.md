# Report form

A form connected to a report object (`Report`). Besides regular form properties, it has several properties in `properties` that link the form to the composition mechanism (DCS): where the result is output, where the drill-down data is, what type it is. All of them are set in the top-level `properties` block.

```json
"properties": {
  "reportFormType": "Main",
  "reportResult": "РезультатОтчета",
  "detailsData": "ДанныеРасшифровки"
}
```

None of these properties is required - specify only those needed by a particular form.

## Report form type (`reportFormType`)

The form's role within the report:

| Value | Purpose |
|----------|-----------|
| `Main` | Main report form (result + settings) |
| `Settings` | Settings form |
| `Variant` | Variant form |

```json
"reportFormType": "Main"
```

## Binding to composition

| Key | Type | Purpose |
|------|-----|-----------|
| `reportResult` | string | Name of the form result attribute (the spreadsheet document where the report is output) |
| `detailsData` | string | Name of the drill-down data attribute |
| `variantAppearance` | string | Name of the variant appearance attribute |

The value of each key is a form attribute name (not a data path). An attribute with that name must be present in the form's `attributes`.

## Custom settings folder (`customSettingsFolder`)

A form group element into which the composer's custom settings are generated. Set **by the name** of the group element:

```json
"customSettingsFolder": "ГруппаПользовательскихНастроек"
```

## Other composition properties

Rare, set only when explicitly needed:

| Key | Values | Purpose |
|------|----------|-----------|
| `autoShowState` | `Auto`, `DontShow`, `ShowOnComposition` | Auto-show of the composition state |
| `reportResultViewMode` | `Auto` | Result view mode |
| `viewModeApplicationOnSetReportResult` | `Auto` | Application of the view mode when setting the result |

## Realistic example

The main report form with DCS: the result attribute, drill-down data and the custom settings group.

```json
{
  "properties": {
    "reportFormType": "Main",
    "reportResult": "РезультатОтчета",
    "detailsData": "ДанныеРасшифровки",
    "customSettingsFolder": "ГруппаПользовательскихНастроек"
  },
  "attributes": [
    { "name": "РезультатОтчета", "type": "SpreadsheetDocument" },
    { "name": "ДанныеРасшифровки", "type": "DataCompositionDetailsData" }
  ],
  "elements": [
    { "group": "vertical", "name": "ГруппаПользовательскихНастроек" },
    { "spreadsheet": "РезультатОтчета", "path": "РезультатОтчета",
      "titleLocation": "none" }
  ]
}
```
