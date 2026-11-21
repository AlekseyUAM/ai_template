# cf-edit - operations reference

## modify-property

Properties to edit:

### Scalar
`Name`, `Version`, `Vendor`, `Comment`, `NamePrefix`, `UpdateCatalogAddress`

### LocalString (multilingual)
`Synonym`, `BriefInformation`, `DetailedInformation`, `Copyright`, `VendorInformationAddress`, `ConfigurationInformationAddress`

### Enum
| Property | Allowed values |
|----------|---------------------|
| `CompatibilityMode` | `Version8_3_20` ... `Version8_3_28`, `Version8_5_1`, `DontUse` |
| `ConfigurationExtensionCompatibilityMode` | same |
| `DefaultRunMode` | `ManagedApplication`, `OrdinaryApplication`, `Auto` |
| `ScriptVariant` | `Russian`, `English` |
| `DataLockControlMode` | `Managed`, `Automatic`, `AutomaticAndManaged` |
| `ObjectAutonumerationMode` | `NotAutoFree`, `AutoFree` |
| `ModalityUseMode` | `DontUse`, `Use`, `UseWithWarnings` |
| `SynchronousPlatformExtensionAndAddInCallUseMode` | `DontUse`, `Use`, `UseWithWarnings` |
| `InterfaceCompatibilityMode` | `Version8_2`, `Version8_2EnableTaxi`, `Taxi`, `TaxiEnableVersion8_2`, `TaxiEnableVersion8_5`, `Version8_5EnableTaxi`, `Version8_5` |
| `DatabaseTablespacesUseMode` | `DontUse`, `Use` |
| `MainClientApplicationWindowMode` | `Normal`, `Workplace`, `FullscreenWorkplace`, `Kiosk`, `EmbeddedWorkplace` |

### Ref
`DefaultLanguage` - value of the form `Language.Русский`

### Batch format
`"Version=1.0.0.1 ;; Vendor=Фирма 1С ;; Synonym=Тестовая конфигурация"`

## add-childObject / remove-childObject

Format: `Type.Name` - XML type and object name separated by a dot.

**Important about `add-childObject`**: registers in `<ChildObjects>` an object **whose file already exists on disk**. If the file is missing - exit 1. To create a new object use the dedicated skill - `/meta-compile` (Catalog, Document, Enum, Report, registers, etc.), `/role-compile` (Role), `/subsystem-compile` (Subsystem). They create the file AND register it in one call.

Batch: `"Catalog.Товары ;; Document.Заказ ;; Enum.ВидыОплат"`

## sort-childObjects

Sorts objects in `<ChildObjects>` by name **within a kind**. The value is the kind name (`Catalog`, `Role`, ...), batch via `;;`. Without a value, all kinds present in the file are processed.

```
-Operation sort-childObjects                       — все виды, кроме перечисленных ниже
-Operation sort-childObjects -Value "Catalog"       — только справочники
-Operation sort-childObjects -Value "Catalog ;; Role"
```

Kinds are not sorted until explicitly named: `CommonAttribute`, `Subsystem`, `CommandGroup`, `Language`.

A call without a value additionally puts kind groups into canonical order; a call with an explicit kind touches only names within it.

## add-defaultRole / remove-defaultRole / set-defaultRoles

Role name: `ПолныеПрава` or `Role.ПолныеПрава` (the `Role.` prefix is added automatically).

`set-defaultRoles` fully replaces the list of roles.

## set-panels

Overwrites `Ext/ClientApplicationInterface.xml` - the panel layout of the Taxi workspace. The file is created from scratch; anything not mentioned in `value` is absent from the screen.

`value` - an object with keys `top`, `left`, `right`, `bottom`. Each key is an array of entries. A key may be omitted (= empty side).

**Entry** - one of:
- An alias string (one panel in this slot)
- An object `{"group": [...]}` (stack: panels/subgroups inside are placed one below another)

**Panel aliases:**

| Alias | Panel |
|-------|--------|
| `sections` | Sections panel |
| `open` | Open panel |
| `favorites` | Favorites panel |
| `history` | History panel |
| `functions` | Functions panel of the current section |

**Semantics:**
- Several entries on one side -> separate slots "side by side" (several `<top>`/... tags)
- `{"group":[...]}` -> one tag with a `<group>` wrapper, the elements inside go as a stack

**Example** (DefinitionFile):
```json
[
  {
    "operation": "set-panels",
    "value": {
      "top":    ["open"],
      "left":   ["sections"],
      "right":  [{ "group": ["favorites", "history"] }],
      "bottom": ["functions"]
    }
  }
]
```

Via `-Value` (CLI): pass the object as a JSON string - `... -Operation set-panels -Value '{"top":["open"]}'`.

## set-home-page

Overwrites `Ext/HomePageWorkArea.xml` - the layout of forms on the home page (working area). The file is created from scratch; anything not mentioned in `value` is absent.

`value` - an object:

| Key | Canonical (XML) | Description |
|------|----------------|----------|
| `template` | `WorkingAreaTemplate` | `OneColumn` / `TwoColumnsEqualWidth` (default) / `TwoColumnsVariableWidth` |
| `left` | `LeftColumn` | array of form entries |
| `right` | `RightColumn` | array of form entries (forbidden with `OneColumn`) |

Both short and canonical (XML) keys are accepted - both work.

**Form entry** - one of:
- A string `"<form>"` - form name only, defaults `height=10`, `visibility=true`
- An object `{form, height?, visibility?, roles?}`

| Field | Canonical | Default | Description |
|------|----------|--------|----------|
| `form` | `Form` | - | `CommonForm.X` or `Type.Object.Form.Name` (or UUID) |
| `height` | `Height` | `10` | Height |
| `visibility` | `Visibility` | `true` | Common visibility (`<xr:Common>`) |
| `roles` | - | - | `{"Role.Имя": true|false, ...}` - per-role overrides |

**Visibility semantics:** `visibility` = the common rule, `roles` - point exceptions. Hide for everyone except one role: `{"visibility": false, "roles": {"Role.Опер": true}}`.

**Example:**
```json
[
  {
    "operation": "set-home-page",
    "value": {
      "template": "TwoColumnsVariableWidth",
      "left": [
        "CommonForm.НачалоРаботы",
        { "form": "CommonForm.СписокЗадач", "height": 100, "visibility": false },
        { "form": "Catalog.Контрагенты.Form.ФормаСписка", "height": 50 },
        {
          "form": "CommonForm.РабочийСтолОператора",
          "visibility": false,
          "roles": { "Role.Оператор": true, "Role.ПолныеПрава": false }
        }
      ],
      "right": [
        { "form": "DataProcessor.Поиск.Form.ФормаПоиска", "height": 30 }
      ]
    }
  }
]
```

## DefinitionFile (JSON)

```json
[
  { "operation": "modify-property", "value": "Version=2.0.0.1 ;; Vendor=Test" },
  { "operation": "add-childObject", "value": "Catalog.Товары ;; Document.Заказ" },
  { "operation": "add-defaultRole", "value": "ПолныеПрава" }
]
```
