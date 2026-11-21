---
name: cfe-borrow
description: Borrowing objects from a 1C configuration into an extension (CFE). Use when you need to intercept a method, change a form or add an attribute to an existing configuration object
argument-hint: -ExtensionPath <path> -ConfigPath <path> -Object "Catalog.Контрагенты.Form.ФормаЭлемента" -BorrowMainAttribute
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-borrow - Borrowing objects from a configuration

Borrows objects from the main configuration into the extension. Creates XML files with `ObjectBelonging=Adopted` and `ExtendedConfigurationObject`, adds an entry to the extension ChildObjects.

## Precondition

The extension must be created (`/cfe-init`) and contain a valid `Configuration.xml`.

### ConfigPath auto-detection

If the user did not specify `-ConfigPath` - try to detect it automatically:
1. Read `.v8-project.json` from the project root
2. Resolve the target infobase (by name, branch or `default` - the algorithm from `/db-list`)
3. If the infobase has a `configSrc` field - use it as `-ConfigPath`
4. If there is no `configSrc` - ask the user

## Parameters

| Parameter | Description |
|----------|----------|
| `ExtensionPath` | Path to the extension directory (required) |
| `ConfigPath` | Path to the source configuration (required) |
| `Object` | What to borrow (required), batch via `;;` |
| `Module` | Create empty object modules: `ObjectModule`, `ManagerModule`, `RecordSetModule`, `ValueManagerModule` (comma-separated) or `None`. For types with a single module (`CommonModule`, `HTTPService`, `WebService`) it is created even without the parameter |
| `BorrowMainAttribute` | Borrow the main form attribute. Without the parameter - does not borrow. `Form` - attributes used on the form. `All` - all object attributes. Requires a form in -Object |

## -Object format

- `Catalog.Контрагенты` - catalog
- `CommonModule.РаботаСФайлами` - common module
- `Document.РеализацияТоваров` - document
- `Enum.ВидыОплат` - enum
- `Catalog.Контрагенты.Form.ФормаЭлемента` - object form (form borrowing)
- `CommonForm.ВыборПериода` - common form, together with its content (like an object form). With `-BorrowMainAttribute` the owner is taken from the main attribute type: object (`DataProcessorObject.X` etc.), the main dynamic list table or the constants of a constants set
- `Catalog.X ;; CommonModule.Y ;; Enum.Z` - several objects

### Borrowing forms

The format `Тип.Имя.Form.ИмяФормы` borrows the form of a specific object. If the parent object is not borrowed yet - it will be borrowed automatically.

Created:
1. **Form metadata** - `Forms/ИмяФормы.xml` with `ObjectBelonging=Adopted`, `FormType=Managed`
2. **Form.xml** - `Forms/ИмяФормы/Ext/Form.xml` with a copy of the source form + `<BaseForm>` (initial state)
3. **Module.bsl** - an empty file `Forms/ИмяФормы/Ext/Form/Module.bsl`
4. **Registration** - `<Form>` in the ChildObjects of the parent object

### Borrowing the main form attribute (-BorrowMainAttribute)

**When needed**: the user wants to add a new attribute to an existing configuration object and display it on a borrowed form. Without `-BorrowMainAttribute` the form is borrowed "empty" - only visual elements, without binding to object data. With `-BorrowMainAttribute` the form keeps bindings to object attributes (DataPath), which then allows adding new elements to it via `/form-edit`.

**Two modes**:
- `Form` (default) - borrows only object attributes already displayed on the form. The optimal choice for most cases
- `All` - borrows all attributes and tabular sections of the object. Use if you plan to display attributes on the form that are not there yet

**Typical scenario** (adding an attribute + displaying it on the form):
1. `/cfe-borrow` with `-BorrowMainAttribute` - borrow the form with attributes
2. `/meta-edit` - add a new attribute to the extension object
3. `/form-edit` - display the attribute on the borrowed form

**Protection of existing data**: an already borrowed object is not overwritten - only the missing parts are added. A repeated call is safe: the extension's own attributes, borrowed subobjects and code in modules are preserved.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cfe-borrow.py" -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Контрагенты"
```

## Examples

```bash
# Заимствовать один объект
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Контрагенты"

# Заимствовать справочник вместе с модулями объекта и менеджера
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Контрагенты" -Module ObjectModule,ManagerModule

# Общий модуль без файла модуля
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "CommonModule.РаботаСФайлами" -Module None

# Заимствовать форму (автоматически заимствует родительский объект)
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Контрагенты.Form.ФормаЭлемента"

# Несколько объектов за раз
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Контрагенты ;; CommonModule.ОбщийМодуль ;; Enum.ВидыОплат"

# Заимствовать форму с основным реквизитом (реквизиты по DataPath формы)
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Номенклатура.Form.ФормаЭлемента" -BorrowMainAttribute

# Заимствовать форму с ВСЕМИ реквизитами объекта
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Object "Catalog.Номенклатура.Form.ФормаЭлемента" -BorrowMainAttribute All
```

## Verification

```
/cfe-validate <ExtensionPath> -ConfigPath <ConfigPath>
```

Pass the source configuration to the validator too: it checks borrowed forms against it.
