---
name: epf-bsp-add-command
description: Define a command in the BSP data processor description (`СведенияОВнешнейОбработке`) - open a form, call a client/server method, fill an object, etc. Use when you need to register a command in a BSP additional data processor
argument-hint: <ProcessorName> <Идентификатор> [ТипКоманды] [Представление]
allowed-tools:
  - Read
  - Edit
  - Glob
  - Grep
---

# /epf-bsp-add-command - Adding a BSP command

Adds a command to the existing `СведенияОВнешнейОбработке()` function and generates the corresponding handler.

First the data processor must be initialized via `/epf-bsp-init`.

## Usage

```
/epf-bsp-add-command <ProcessorName> <Идентификатор> [ТипКоманды] [Представление]
```

| Parameter      | Required | Default          | Description                                   |
|---------------|:------------:|-----------------------|--------------------------------------------|
| ProcessorName | yes          | -                     | Data processor name                              |
| Идентификатор | yes          | -                     | Internal command name (Latin)          |
| ТипКоманды    | no           | from the data processor kind     | Command launch type (see the mapping below)     |
| Представление | no           | = Идентификатор       | Command display name for the user  |
| SrcDir        | no           | `src`                 | Source directory                         |

## Command type mapping

The user can specify the type in free form:

| What the user writes                    | ТипКоманды                                | Available for the data processor kind |
|---------------------------------------|-------------------------------------------|-----------------------------|
| open form, form                  | `ТипКомандыОткрытиеФормы()`               | any                      |
| client method, on the client          | `ТипКомандыВызовКлиентскогоМетода()`      | any                      |
| server method, on the server           | `ТипКомандыВызовСерверногоМетода()`       | any                      |
| form filling, fill the form     | `ТипКомандыЗаполнениеФормы()`             | ЗаполнениеОбъекта           |
| loading from file, import from file    | `ТипКомандыЗагрузкаДанныхИзФайла()`       | ДополнительнаяОбработка; the configuration must have the subsystem «Загрузка данных из файла» |

BSP has no other command types. If the requested type does not fit any row - ask the user, do not invent a method. If the type is unavailable for the data processor kind - tell about it and do not add the command.

If the user did not specify the type - determine it by the data processor kind from the existing `СведенияОВнешнейОбработке()` code:

| Data processor kind (from the code)    | Default ТипКоманды                   |
|----------------------------|-------------------------------------------|
| ДополнительнаяОбработка    | `ТипКомандыОткрытиеФормы()`               |
| ДополнительныйОтчет       | `ТипКомандыОткрытиеФормы()`               |
| ЗаполнениеОбъекта          | `ТипКомандыВызовСерверногоМетода()`        |
| Отчет                      | `ТипКомандыОткрытиеФормы()`               |
| ПечатнаяФорма              | `ТипКомандыВызовСерверногоМетода()`        |
| СозданиеСвязанныхОбъектов  | `ТипКомандыВызовСерверногоМетода()`        |

## Command addition template

Inserted into `СведенияОВнешнейОбработке()` **before** the `Возврат ПараметрыРегистрации` line:

```bsl
	НоваяКоманда = ПараметрыРегистрации.Команды.Добавить();
	НоваяКоманда.Представление        = НСтр("ru = '{{Представление}}'");
	НоваяКоманда.Идентификатор        = "{{Идентификатор}}";
	НоваяКоманда.Использование        = ДополнительныеОтчетыИОбработкиКлиентСервер.{{ТипКоманды}};
	НоваяКоманда.ПоказыватьОповещение = Ложь;
```

For print forms (ВидОбработкиПечатнаяФорма) also add:

```bsl
	НоваяКоманда.Модификатор = "ПечатьMXL";
```

For the ЗагрузкаДанныхИзФайла command `Модификатор` is required: the full name of the catalog into which data is loaded. If the user did not name it - ask.

```bsl
	НоваяКоманда.Модификатор = "Справочник.Номенклатура";
```

Note: unlike the first command (from `/epf-bsp-init`), additional commands use string literals `НСтр("ru = '...'")` for the representation and a string for the identifier, not `Метаданные()`.

## Handler templates

The template is chosen by the pair "command type x data processor kind".

### ОткрытиеФормы

Handler not needed: the main data processor form opens, the command identifier comes in `Параметры.ИдентификаторКоманды`.

### ВызовСерверногоМетода, ЗаполнениеФормы - if a handler already exists

If the `ВыполнитьКоманду` procedure already exists in the object module, add a branch before `КонецЕсли`:

```bsl
	ИначеЕсли ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
```

### ВызовСерверногоМетода, ЗаполнениеФормы - if there is no handler

The procedure is added to the object module. The signature depends on the data processor kind.

ДополнительнаяОбработка, ДополнительныйОтчет (without `ОбъектыНазначения`):

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ПараметрыВыполненияКоманды) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

ЗаполнениеОбъекта, Отчет:

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначения, ПараметрыВыполненияКоманды) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

For a command of the ЗаполнениеФормы type the handler is the same: `ОбъектыНазначения` = `Неопределено`, the form being filled is passed in `ПараметрыВыполненияКоманды.ЭтаФорма`.

СозданиеСвязанныхОбъектов (references of created objects are added to the `СозданныеОбъекты` array):

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначения, СозданныеОбъекты, ПараметрыВыполненияКоманды) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

### ПечатнаяФорма - if the Печать procedure already exists

Add a block before `КонецПроцедуры`:

```bsl
	ПечатнаяФорма = УправлениеПечатью.СведенияОПечатнойФорме(КоллекцияПечатныхФорм, "{{Идентификатор}}");
	Если ПечатнаяФорма <> Неопределено Тогда
		ПечатнаяФорма.ТабличныйДокумент = Сформировать{{Идентификатор}}(МассивОбъектов, ОбъектыПечати);
		ПечатнаяФорма.СинонимМакета = НСтр("ru = '{{Представление}}'");
	КонецЕсли;
```

### ПечатнаяФорма - if there is no Печать procedure

```bsl
Процедура Печать(МассивОбъектов, КоллекцияПечатныхФорм, ОбъектыПечати, ПараметрыВывода) Экспорт

	ПечатнаяФорма = УправлениеПечатью.СведенияОПечатнойФорме(КоллекцияПечатныхФорм, "{{Идентификатор}}");
	Если ПечатнаяФорма <> Неопределено Тогда
		ПечатнаяФорма.ТабличныйДокумент = Сформировать{{Идентификатор}}(МассивОбъектов, ОбъектыПечати);
		ПечатнаяФорма.СинонимМакета = НСтр("ru = '{{Представление}}'");
	КонецЕсли;

КонецПроцедуры
```

### ВызовКлиентскогоМетода

Added to the **main form module** (`Forms/<FormName>/Ext/Form/Module.bsl`). The name and signature depend on the data processor kind.

ДополнительнаяОбработка, ДополнительныйОтчет:

```bsl
&НаКлиенте
Процедура ВыполнитьКоманду(ИдентификаторКоманды) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

ЗаполнениеОбъекта, Отчет:

```bsl
&НаКлиенте
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначенияМассив) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

СозданиеСвязанныхОбъектов:

```bsl
&НаКлиенте
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначенияМассив, СозданныеОбъекты) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

ПечатнаяФорма (the procedure is called `Печать`, not `ВыполнитьКоманду`):

```bsl
&НаКлиенте
Процедура Печать(ИдентификаторКоманды, ОбъектыНазначенияМассив) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Реализация {{Идентификатор}}
	КонецЕсли;

КонецПроцедуры
```

If the procedure already exists - add an `ИначеЕсли` branch.

### ЗагрузкаДанныхИзФайла

Three export procedures are added to the object module. If one of them already exists - add an `ИначеЕсли` branch to it.

```bsl
Процедура ОпределитьПараметрыЗагрузкиДанныхИзФайла(ИдентификаторКоманды, ПараметрыЗагрузки) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// ПараметрыЗагрузки.ИмяМакетаСШаблоном = "ЗагрузкаДанныхИзФайла";
		// ПараметрыЗагрузки.ОбязательныеКолонки.Добавить("<ИмяКолонки>");
	КонецЕсли;

КонецПроцедуры

Процедура СопоставитьЗагружаемыеДанныеИзФайла(ИдентификаторКоманды, ЗагружаемыеДанные) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Заполнить колонку СопоставленныйОбъект по данным из файла
	КонецЕсли;

КонецПроцедуры

Процедура ЗагрузитьИзФайла(ИдентификаторКоманды, ЗагружаемыеДанные, ПараметрыЗагрузки, Отказ) Экспорт

	Если ИдентификаторКоманды = "{{Идентификатор}}" Тогда
		// TODO: Загрузка; для каждой строки заполнить РезультатСопоставленияСтроки
		// ("Создан", "Обновлен", "Пропущен") и при ошибке ОписаниеОшибки
	КонецЕсли;

КонецПроцедуры
```

Columns of the loaded data are taken from the `ЗагрузкаДанныхИзФайла` data processor template (the template name can be overridden via `ПараметрыЗагрузки.ИмяМакетаСШаблоном`). If there is no template - suggest creating it via `/template-add`.

## Instructions

1. Find and read `ObjectModule.bsl` via Glob: `src/{{ProcessorName}}/Ext/ObjectModule.bsl`
2. Make sure `СведенияОВнешнейОбработке()` exists. If not - suggest calling `/epf-bsp-init`
3. Determine the data processor kind from the existing code (find the line with `ВидОбработки...()`)
4. Insert the command block **before** `Возврат ПараметрыРегистрации`
5. Add a handler using the template for the command type and data processor kind from step 3:
   - For server handlers and ЗагрузкаДанныхИзФайла - in `ObjectModule.bsl`, region `ПрограммныйИнтерфейс`
   - For client handlers - in the main form module (find via Glob: `src/{{ProcessorName}}/Forms/*/Ext/Form/Module.bsl`)
6. If the handler (`ВыполнитьКоманду` / `Печать` / loading procedures) already exists - add a branch, do not create a duplicate procedure
7. Use tabs for indentation

## Example

User: `/epf-bsp-add-command МояОбработка ЗаказПокупателя серверный "Заказ покупателя"`

In `СведенияОВнешнейОбработке()` before `Возврат` the following will be added:

```bsl
	НоваяКоманда = ПараметрыРегистрации.Команды.Добавить();
	НоваяКоманда.Представление        = НСтр("ru = 'Заказ покупателя'");
	НоваяКоманда.Идентификатор        = "ЗаказПокупателя";
	НоваяКоманда.Использование        = ДополнительныеОтчетыИОбработкиКлиентСервер.ТипКомандыВызовСерверногоМетода();
	НоваяКоманда.ПоказыватьОповещение = Ложь;
```

And a handling block will be added to the existing `ВыполнитьКоманду` procedure.
