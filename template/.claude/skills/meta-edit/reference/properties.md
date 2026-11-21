# Object properties and list properties

Operation reference for regular object properties and list properties (Owners, RegisterRecords, BasedOn, InputByString).

## modify-property

Changing object properties by the 1C property name (PascalCase, as in the Configurator). Format: `Ключ=Значение`
(batch via `;;`):
```bash
-Operation modify-property -Value "CodeLength=11 ;; DescriptionLength=150"
-Operation modify-property -Value "Hierarchical=true"
```

A property can be set even if it is not yet set on the object (e.g. `FullTextSearch`, `DataHistory`).
Property names of the corresponding object type are allowed.

### Type - value type (Constant, chart of characteristic types)

`Type=...` rebuilds the value type descriptor. The value is a 1C type in the same syntax
as for attributes: composite via `+`, with qualifiers and reference types:
```bash
-Operation modify-property -Value "Type=String(100) + Number(15,2) + CatalogRef.Номенклатура"
```
Structural properties (with nested nodes) are not set via `Ключ=Значение` - the only exception is `Type`.

## List properties

Properties whose value is a list of references. Managed via inline `add-*` / `remove-*` / `set-*` and via JSON `modify.properties`.

| Property | Objects | Inline value |
|----------|---------|-----------------|
| Owners | Catalog | `Catalog.XXX` |
| RegisterRecords | Document, Sequence | `AccumulationRegister.XXX` |
| BasedOn | reference* | `Document.XXX` |
| InputByString | reference* | `StandardAttribute.Description` |
| DataLockFields | reference* | `Организация` (short attribute name -> full path) |
| RegisteredDocuments | DocumentJournal | `Document.XXX` |

\* Catalog, Document, ChartOfCharacteristicTypes, ChartOfAccounts, ChartOfCalculationTypes, ExchangePlan, BusinessProcess, Task.

### add-owner / add-registerRecord / add-basedOn / add-registeredDocument

Full metadata name `MetaType.Name`:
```bash
-Operation add-owner -Value "Catalog.Контрагенты ;; Catalog.Организации"
-Operation add-registerRecord -Value "AccumulationRegister.ОстаткиТоваров"
-Operation add-basedOn -Value "Document.ЗаказКлиента"
-Operation add-registeredDocument -Value "Document.РасходныйОрдер"
```

### add-inputByString / add-dataLockField

Field paths (a short attribute name is expanded to the full path automatically):
```bash
-Operation add-inputByString -Value "StandardAttribute.Description ;; StandardAttribute.Code"
-Operation add-dataLockField -Value "Организация ;; Контрагент"
```

### remove-owner / remove-registerRecord / remove-basedOn / remove-inputByString / remove-dataLockField / remove-registeredDocument

```bash
-Operation remove-owner -Value "Catalog.Контрагенты"
-Operation remove-inputByString -Value "Catalog.МойСпр.StandardAttribute.Code"
-Operation remove-dataLockField -Value "Организация"
```

### set-owners / set-registerRecords / set-basedOn / set-inputByString / set-dataLockFields / set-registeredDocuments

Replace the **whole list** (unlike add/remove):
```bash
-Operation set-owners -Value "Catalog.Организации ;; Catalog.Контрагенты"
-Operation set-registerRecords -Value "AccumulationRegister.Продажи ;; AccumulationRegister.ОстаткиТоваров"
-Operation set-inputByString -Value "StandardAttribute.Description ;; StandardAttribute.Code"
```
