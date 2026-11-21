---
name: mxl-info
description: Analyze the structure of a spreadsheet document (MXL) template - areas, parameters, column sets. Use in print development - to get the template areas and fillable parameters
argument-hint: <TemplatePath> or <ProcessorName> <TemplateName>
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /mxl-info - Template structure analysis

Reads Template.xml of a spreadsheet document and outputs a compact summary: named areas, parameters, column sets. Replaces the need to read thousands of lines of XML.

## Usage

```
/mxl-info <TemplatePath>
/mxl-info <ProcessorName> <TemplateName>
```

## Parameters

| Parameter     | Required     | Default      | Description                              |
|---------------|:------------:|--------------|------------------------------------------|
| TemplatePath  | no           | -            | Direct path to Template.xml              |
| ProcessorName | no           | -            | Data processor name (alternative to a path) |
| TemplateName  | no           | -            | Template name (alternative to a path)    |
| SrcDir        | no           | `src`        | Source directory                         |
| Format        | no           | `text`       | Output format: `text` or `json`          |
| WithText      | no           | false        | Include static text and templates        |
| MaxParams     | no           | 10           | Max parameters in the list per area      |
| Limit         | no           | 150          | Max output lines (overflow protection)   |
| Offset        | no           | 0            | Skip N lines (for pagination)            |

Specify either `-TemplatePath`, or both `-ProcessorName` and `-TemplateName`.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/mxl-info.py" -TemplatePath "<путь>"
```

Or by data processor/template name:
```bash
python "${CLAUDE_SKILL_DIR}/scripts/mxl-info.py" -ProcessorName "<Имя>" -TemplateName "<Макет>" [-SrcDir "<каталог>"]
```

Additional flags:
```bash
... -WithText              # включить текстовое содержимое ячеек
... -Format json           # JSON-вывод для программной обработки
... -MaxParams 20          # показать больше параметров на область
... -Offset 150            # пагинация: пропустить первые 150 строк
```

## Reading the output

### Areas - sorted top to bottom

Areas are listed in document order (by row position), not alphabetically. This matches the order of outputting areas in fill code - top to bottom.

```
--- Named areas ---
  Заголовок          Rows     rows 1-4     (1 params)
  Поставщик          Rows     rows 5-6     (1 params)
  Строка             Rows     rows 14-14   (8 params)
  Итого              Rows     rows 16-17   (1 params)
```

Area types:
- **Rows** - horizontal area (row range). Retrieval: `Макет.ПолучитьОбласть("Имя")`
- **Columns** - vertical area (column range). Retrieval: `Макет.ПолучитьОбласть("Имя")`
- **Rectangle** - fixed area (rows + columns). Usually uses a separate column set.
- **Drawing** - named drawing/barcode.

### Intersections

When there are both Rows and Columns areas (labels, price tags), the script outputs intersection pairs:

```
--- Intersections (use with GetArea) ---
  ВысотаЭтикетки|ШиринаЭтикетки
```

In BSL: `Макет.ПолучитьОбласть("ВысотаЭтикетки|ШиринаЭтикетки")`

### Parameters and detailParameter

Parameters are listed by area. If a parameter has a `detailParameter` (decryption), it is shown below:

```
--- Parameters by area ---
  Поставщик: ПредставлениеПоставщика
    detail: ПредставлениеПоставщика->Поставщик
  Строка: НомерСтроки, Товар, Количество, Цена, Сумма, ... (+3)
    detail: Товар->Номенклатура
```

This means: the `Товар` parameter displays a value, and on click opens `Номенклатура` (the decryption object).

### Parameters from templates (suffix `[tpl]`)

Some parameters are embedded in template text: `"Инв № [ИнвентарныйНомер]"`. They are filled via fillType=Template, not fillType=Parameter. The script always extracts them and marks them with the `[tpl]` suffix:

```
  НумерацияЛистов: Номер [tpl], Дата [tpl], НомерЛиста [tpl]
```

In BSL template parameters are filled the same way as regular ones:
```bsl
Область.Параметры.Номер = НомерДокумента;
Область.Параметры.Дата = ДатаДокумента;
```

Numeric substitutions like `[5]`, `[6]` (references to footnotes in official forms) are ignored.

### Text content (`-WithText`)

Shows static text (labels, headings) and template strings with `[Параметр]` substitutions:

```
--- Text content ---
  ШапкаТаблицы:
    Text: "№", "Товар", "Ед. изм.", "Кол-во", "Цена", "Сумма"
  Строка:
    Templates: "Инв № [ИнвентарныйНомер]"
```

- **Text** - static labels (fillType=Text). Useful for understanding the purpose of columns.
- **Templates** - text with `[ИмяПараметра]` substitutions (fillType=Template). The parameter inside `[]` is filled programmatically.
