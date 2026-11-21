---
name: template-add
description: Add an empty template to a 1C object. Use when you need to create a new template for an object
argument-hint: <ObjectName> <TemplateName> <TemplateType>
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /template-add - Add a template

Creates a template of the specified type and registers it in the object's root XML.

## Usage

```
/template-add <ObjectName> <TemplateName> <TemplateType>
```

| Parameter     | Required | Default         | Description                                      |
|---------------|:------------:|-----------------|--------------------------------------------------|
| ObjectName    | yes          | -               | Object name                                      |
| TemplateName  | yes          | -               | Template name                                    |
| TemplateType  | yes          | -               | Type: HTML, Text, SpreadsheetDocument, BinaryData, DataCompositionSchema |
| Synonym       | no           | = TemplateName  | Template synonym                                 |
| Lang          | no           | `ru`            | Page language code - for the HTML type only. A repeated call with another language adds a page to the existing template |
| SrcDir        | no           | `src`           | Path to the object type folder (`Reports`, `DataProcessors`, `Catalogs`, `Documents`...), which contains `<ObjectName>.xml`. The default `src` suits directories with external data processors/reports lying nearby |
| -SetMainSKD   | no           | -               | Force setting MainDataCompositionSchema |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/template-add.py" -ObjectName "<ObjectName>" -TemplateName "<TemplateName>" -TemplateType "<TemplateType>" [-Synonym "<Synonym>"] [-Lang "<Lang>"] [-SrcDir "<SrcDir>"] [-SetMainSKD]
```

## Example

Add the main DCS to a report in an extension:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/template-add.py" -ObjectName "ОтчётПродажи" -TemplateName "ОсновнаяСхемаКомпоновкиДанных" -TemplateType "DataCompositionSchema" -SrcDir "src/cfe/МоёРасширение/Reports"
```

## Type mapping

The user may specify the type in free form. Determine the needed one from context:

| User writes                                 | TemplateType        | Extension | Content                 |
|---------------------------------------------|---------------------|------------|-------------------------|
| HTML                                        | HTMLDocument        | `Template/<lang>.html` | Empty HTML document |
| Text, text document, text                   | TextDocument        | `.txt`     | Empty file              |
| SpreadsheetDocument, spreadsheet document, MXL | SpreadsheetDocument | `.xml`     | Minimal spreadsheet |
| BinaryData, binary data                     | BinaryData          | `.bin`     | Empty file              |
| DataCompositionSchema, DCS, composition schema | DataCompositionSchema | `.xml`   | Minimal DCS schema      |

## Naming convention

For **print form** templates (SpreadsheetDocument type) use the `ПФ_MXL_` prefix:

| Context                                                          | Name format                | Example                 |
|------------------------------------------------------------------|----------------------------|-------------------------|
| Print form (a supplementary data processor of PrintForm kind, or the user explicitly says "print form") | `ПФ_MXL_<КраткоеИмя>`     | `ПФ_MXL_М11`, `ПФ_MXL_СчётФактура`, `ПФ_MXL_КонвертDL` |
| Other templates (data loading, service, settings)                | Without prefix             | `МакетЗагрузки`, `НастройкиПечати` |

If the user specified a template name without the prefix but the context is a print form, **add the `ПФ_MXL_` prefix automatically** and report it.

## MainDataCompositionSchema (auto)

When adding a template of `DataCompositionSchema` type to `ExternalReport` or `Report`:
- If `MainDataCompositionSchema` is empty - it is filled automatically with a reference to the template
- Use `--SetMainSKD` to overwrite the existing value

## What is created

```
<SrcDir>/<ObjectName>/Templates/
├── <TemplateName>.xml              # Метаданные макета (1 UUID)
└── <TemplateName>/
    └── Ext/
        ├── Template.<ext>          # Содержимое макета
        └── Template/<lang>.html    # HTML: содержимое (Template.xml — дескриптор)
```

## What is modified

- `<SrcDir>/<ObjectName>.xml` - a `<Template>` is added to the end of `ChildObjects`
- For ExternalReport/Report: `MainDataCompositionSchema` may be updated
