---
name: cfe-patch-method
description: Generation and actualization of a method interceptor in a 1C extension (CFE). Use when you need to intercept a borrowed object method - insert code before, after, instead of the original, change its body (ИзменениеИКонтроль) - or actualize the interceptor after the original changes
argument-hint: -ExtensionPath <path> -ConfigPath <path> -ModulePath "Catalog.X.ObjectModule" -MethodName "ПриЗаписи" -InterceptorType Before
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-patch-method - Method interceptor generation

Reads the method original from the source configuration and generates a `.bsl` interceptor of the borrowed object: with the correct context directive, a full signature, surrounding preprocessor instructions and regions. For `ИзменениеИКонтроль` copies the whole body of the original. Creates a module file, appends to an existing one or actualizes an already borrowed method.

## Precondition

The object must be borrowed into the extension (`/cfe-borrow`). Access to the base configuration sources is needed (`-ConfigPath`) - the method original is read from there. `NamePrefix` is taken from the extension `Configuration.xml`.

### ConfigPath auto-detection

If the user did not specify `-ConfigPath` - try to detect it automatically:
1. Read `.v8-project.json` from the project root
2. Resolve the target infobase (by name, branch or `default` - the algorithm from `/db-list`)
3. If the infobase has a `configSrc` field - use it as `-ConfigPath`
4. If there is no `configSrc` - ask the user

## Parameters

| Parameter | Description | Default |
|----------|----------|--------------|
| `ExtensionPath` | Path to the extension (required) | - |
| `ConfigPath` | Path to the source configuration | required, except when `ModulePath` is a file path |
| `ModulePath` | Logical name (`Тип.Имя.Модуль`) **or** path to a `.bsl` module file | required for generation |
| `MethodName` | Name of the method to intercept | required for generation |
| `InterceptorType` | `Before` / `After` / `Instead` / `ModificationAndControl` | required for generation |
| `Check` | Check controlled methods for drift (report only) | - |
| `Actualize` | Actualize drifted controlled methods | - |

## ModulePath format

| ModulePath | File |
|------------|------|
| `Catalog.X.ObjectModule` | `Catalogs/X/Ext/ObjectModule.bsl` |
| `Catalog.X.ManagerModule` | `Catalogs/X/Ext/ManagerModule.bsl` |
| `Catalog.X.Form.Y` | `Catalogs/X/Forms/Y/Ext/Form/Module.bsl` |
| `CommonModule.X` | `CommonModules/X/Ext/Module.bsl` |
| `CommonForm.X` | `CommonForms/X/Ext/Form/Module.bsl` |
| `Document.X.ObjectModule` | `Documents/X/Ext/ObjectModule.bsl` |
| `Document.X.Form.Y` | `Documents/X/Forms/Y/Ext/Form/Module.bsl` |

Similarly for Report, DataProcessor, InformationRegister and other types.

Instead of a logical name in `ModulePath` you can pass a **path to the file** of the source module `.bsl` - then `-ConfigPath` does not need to be specified (the original is read directly from this file). The extension module path is determined automatically from the standard folder in the path.

## Interception types

| InterceptorType | Decorator | Purpose | Applicable to |
|-----------------|-----------|------------|------------|
| `Before` | `&Перед` | Code before the original method call | procedures |
| `After` | `&После` | Code after the original method call | procedures |
| `Instead` | `&Вместо` | Method replacement; the body contains the `ПродолжитьВызов(...)` scaffold | procedures and functions |
| `ModificationAndControl` | `&ИзменениеИКонтроль` | Copy of the original body for editing with `#Вставка`/`#Удаление` markers | procedures and functions |

## Markers `#Вставка` / `#Удаление` (for `ModificationAndControl`)

`&ИзменениеИКонтроль` inserts into the interceptor a **copy of the original body**. Then edit the body for your rework, **marking every change** - this is how the platform distinguishes your edit from the unchanged original:

- **Adding code** -> wrap it in `#Вставка` ... `#КонецВставки`.
- **Deleting original code** -> wrap the deleted lines in `#Удаление` ... `#КонецУдаления`, but **leave the lines themselves between the markers** (the platform compares them with the original).
- **Replacing** -> `#Удаление` old `#КонецУдаления` immediately after it `#Вставка` new `#КонецВставки`.

Example:
```bsl
&ИзменениеИКонтроль("ПриЗаписи")
Процедура Расш_ПриЗаписи(Отказ)
	СуммаДокумента = РассчитатьСумму();
#Вставка
	// доработка: округляем
	СуммаДокумента = Окр(СуммаДокумента, 2);
#КонецВставки
#Удаление
	Записать();
#КонецУдаления
#Вставка
	ЗаписатьСПроверкой(Отказ);
#КонецВставки
КонецПроцедуры
```

Rules:
- Markers go on a **separate line from column 0** (no indent), even inside indents and query text (`|…`).
- **Unmarked lines must match the original verbatim** - that is the "control". Verbatim - including comments, case and spaces inside a line (`Х = Х + 1` ≠ `Х=Х+1`); only indentation and empty lines are free. If the original in the source configuration changes, the unmarked context will diverge -> the method will need actualization (see below; check in batch with `-Check`).
- Change only your own `#Вставка`/`#Удаление`; do not touch other people's original.

## Actualization

After the original changes in the source configuration, the `&ИзменениеИКонтроль` interceptor may get out of sync - the unmarked context will diverge from the new original. The platform stays silent about this on load, so actualize yourself:

- **Check** - `-Check`: a report on all controlled methods of the extension, writes nothing (`exit 1` if there is drift or a conflict).
- **Actualize** - `-Actualize`: transfers edits (`#Вставка`/`#Удаление`) onto the new original across the whole extension. Narrow the scope: `-ModulePath` - one module, `+ -MethodName` - one method. For one method the same is done by a repeated call with `-InterceptorType ModificationAndControl`.

Statuses in the output:

- `[АКТУАЛЕН]` - the original has not changed, no edits;
- `[АКТУАЛИЗИРОВАН]` - the body was updated to the new original, edits preserved (the output has a summary);
- `[АКТУАЛИЗИРОВАН-ЧАСТИЧНО]` - some edits could not be placed (the anchor changed in the new original). They are marked `// [РЕСИНК-КОНФЛИКТ]` in the module and are not lost; the merge workspace path is in the output (start with `index.md`, then for each conflict its `conflict.md`, place the blocks manually in the extension `.bsl`);
- `[ПЕРЕНЕСЕНО В ОСНОВНУЮ]` - the edit is already in the new original (the inserted code was added by the vendor) or the deleted block is already cut out. The edit is not relevant - it is removed from the body, no need to duplicate/conflict. If this is so with all edits of the method - the interceptor can be deleted. `-Check` does not fail `exit` because of this.

A repeated `Before`/`After`/`Instead` call for an already intercepted method does not create a duplicate (`[ПРОПУЩЕН]`).

`-Check` looks at the sources. The platform verdict is after loading into the infobase: `/db-cfe-admin check`.

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/cfe-patch-method.py" -ExtensionPath src\cfe\extname -ConfigPath src\cf -ModulePath "Catalog.Контрагенты.ObjectModule" -MethodName "ПриЗаписи" -InterceptorType Before
```

## Examples

```bash
# Код перед записью
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -ModulePath "Catalog.Контрагенты.ObjectModule" -MethodName "ПриЗаписи" -InterceptorType Before

# Перехват После на форме
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -ModulePath "Document.Заказ.Form.ФормаДокумента" -MethodName "ПослеЗаписиНаСервере" -InterceptorType After

# Замена функции (ПродолжитьВызов)
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -ModulePath "CommonModule.ОбщийМодуль" -MethodName "ПолучитьДанные" -InterceptorType Instead

# ИзменениеИКонтроль — копия тела для правки маркерами
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -ModulePath "Document.РеализацияТоваров.ObjectModule" -MethodName "ОбработкаПроведения" -InterceptorType ModificationAndControl

# ModulePath как путь к файлу модуля-источника (без -ConfigPath)
... -ExtensionPath src\cfe\extname -ModulePath "src\cf\CommonModules\ОбщийМодуль\Ext\Module.bsl" -MethodName "ПолучитьДанные" -InterceptorType Instead

# Проверить все контролируемые методы расширения на дрейф
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Check

# Актуализировать дрейфнувшие контролируемые методы пачкой
... -ExtensionPath src\cfe\extname -ConfigPath src\cf -Actualize
```

## Verification

```
/cfe-validate <ExtensionPath> -ConfigPath <ConfigPath>
```
