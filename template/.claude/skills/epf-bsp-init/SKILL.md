---
name: epf-bsp-init
description: Form the `СведенияОВнешнейОбработке` function in the data processor object module - a description for connecting via the BSP subsystem «Дополнительные отчёты и обработки». Use when you need to make a data processor BSP-compatible, connectable via «Дополнительные отчёты и обработки»
argument-hint: <ProcessorName> <Вид>
allowed-tools:
  - Read
  - Edit
  - Glob
  - Grep
---

# /epf-bsp-init - Registering a data processor in BSP

Adds to the data processor object module the `СведенияОВнешнейОбработке()` function required for registration in the BSP subsystem «Дополнительные отчёты и обработки».

## Usage

```
/epf-bsp-init <ProcessorName> <Вид> [Назначение...]
```

| Parameter      | Required | Default | Description                                                |
|---------------|:------------:|--------------|---------------------------------------------------------|
| ProcessorName | yes           | -            | Data processor name (it must be created via `/epf-init`)   |
| Вид           | yes           | -            | Data processor kind (see the mapping below)                        |
| Назначение    | *            | -            | Metadata objects for assignable kinds                 |
| SrcDir        | no           | `src`        | Source directory                                      |

\* Назначение is required for the kinds: ЗаполнениеОбъекта, Отчет, ПечатнаяФорма, СозданиеСвязанныхОбъектов.

## Data processor kind mapping

The user can specify the kind in free form. Determine the needed one by context:

| What the user writes                        | Вид                        | API method                                    |
|-------------------------------------------|----------------------------|----------------------------------------------|
| additional data processor, data processor, global      | ДополнительнаяОбработка    | `ВидОбработкиДополнительнаяОбработка()`      |
| additional report, global report              | ДополнительныйОтчет       | `ВидОбработкиДополнительныйОтчет()`         |
| filling, fill                     | ЗаполнениеОбъекта          | `ВидОбработкиЗаполнениеОбъекта()`            |
| report (assignable, for an object)          | Отчет                      | `ВидОбработкиОтчет()`                        |
| print form, print                    | ПечатнаяФорма              | `ВидОбработкиПечатнаяФорма()`                |
| creation of related objects               | СозданиеСвязанныхОбъектов  | `ВидОбработкиСозданиеСвязанныхОбъектов()`    |

## Default command type

| Вид                        | Default ТипКоманды                   |
|----------------------------|-------------------------------------------|
| ДополнительнаяОбработка    | `ТипКомандыОткрытиеФормы()`               |
| ДополнительныйОтчет       | `ТипКомандыОткрытиеФормы()`               |
| ЗаполнениеОбъекта          | `ТипКомандыВызовСерверногоМетода()`        |
| Отчет                      | `ТипКомандыОткрытиеФормы()`               |
| ПечатнаяФорма              | `ТипКомандыВызовСерверногоМетода()`        |
| СозданиеСвязанныхОбъектов  | `ТипКомандыВызовСерверногоМетода()`        |

## Template: СведенияОВнешнейОбработке

The base template is the same for all kinds; only the API method calls and conditional sections differ.

```bsl
Функция СведенияОВнешнейОбработке() Экспорт

	МетаданныеОбработки = Метаданные();

	ПараметрыРегистрации = ДополнительныеОтчетыИОбработки.СведенияОВнешнейОбработке("2.2.2.1");
	ПараметрыРегистрации.Вид    = ДополнительныеОтчетыИОбработкиКлиентСервер.{{ВидОбработки}};
	ПараметрыРегистрации.Версия = "1.0";

	{{СЕКЦИЯ_НАЗНАЧЕНИЕ}}

	НоваяКоманда = ПараметрыРегистрации.Команды.Добавить();
	НоваяКоманда.Представление        = МетаданныеОбработки.Представление();
	НоваяКоманда.Идентификатор        = МетаданныеОбработки.Имя;
	НоваяКоманда.Использование        = ДополнительныеОтчетыИОбработкиКлиентСервер.{{ТипКоманды}};
	НоваяКоманда.ПоказыватьОповещение = Ложь;
	{{СЕКЦИЯ_МОДИФИКАТОР}}

	Возврат ПараметрыРегистрации;

КонецФункции
```

### Substitutions

- `{{ВидОбработки}}` - API method from the kind mapping table
- `{{ТипКоманды}}` - API method from the default command type table

### Conditional sections

**`{{СЕКЦИЯ_НАЗНАЧЕНИЕ}}`** - only for assignable kinds (ЗаполнениеОбъекта, Отчет, ПечатнаяФорма, СозданиеСвязанныхОбъектов). One line per object:

```bsl
	ПараметрыРегистрации.Назначение.Добавить("Документ.СчетНаОплату");
```

Object name format: `ИмяКлассаОбъектаМетаданного.ИмяОбъекта` (for example `Документ.СчетНаОплату`, `Справочник.Контрагенты`).

For global kinds (ДополнительнаяОбработка, ДополнительныйОтчет) - the section is not needed, delete it together with the empty line.

**`{{СЕКЦИЯ_МОДИФИКАТОР}}`** - only for ПечатнаяФорма:

```bsl
	НоваяКоманда.Модификатор = "ПечатьMXL";
```

For other kinds - delete it together with the empty line.

## Server handler templates

For kinds with the `ВызовСерверногоМетода` command type add the corresponding handler procedure to the same `ПрограммныйИнтерфейс` region, after `СведенияОВнешнейОбработке`.

### For ЗаполнениеОбъекта

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначения, ПараметрыВыполненияКоманды) Экспорт

	// TODO: Реализация

КонецПроцедуры
```

### For СозданиеСвязанныхОбъектов

References of created objects are added to the `СозданныеОбъекты` array:

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ОбъектыНазначения, СозданныеОбъекты, ПараметрыВыполненияКоманды) Экспорт

	// TODO: Реализация

КонецПроцедуры
```

### For ПечатнаяФорма

```bsl
Процедура Печать(МассивОбъектов, КоллекцияПечатныхФорм, ОбъектыПечати, ПараметрыВывода) Экспорт

	// TODO: Реализация

КонецПроцедуры
```

### For ДополнительнаяОбработка / ДополнительныйОтчет (with ВызовСерверногоМетода)

If the user explicitly chose the server method instead of opening a form:

```bsl
Процедура ВыполнитьКоманду(ИдентификаторКоманды, ПараметрыВыполненияКоманды) Экспорт

	// TODO: Реализация

КонецПроцедуры
```

Note: global data processors have no `ОбъектыНазначения` parameter.

## Instructions

1. Find `ObjectModule.bsl` via Glob: `src/{{ProcessorName}}/Ext/ObjectModule.bsl`
2. Read the file
3. If `СведенияОВнешнейОбработке` already exists - tell the user and do not duplicate
4. If the file is not found - suggest calling `/epf-init` first
5. Find the region `#Область ПрограммныйИнтерфейс` ... `#КонецОбласти`
6. Insert the `СведенияОВнешнейОбработке()` function inside this region
7. If the kind requires a server handler - insert it into this region too, after the function
8. Use tabs for indentation (as in the source file)

## Example

User: `/epf-bsp-init МояОбработка печатная форма для Документ.СчетНаОплату`

Result in `ObjectModule.bsl`:

```bsl
#Область ОписаниеПеременных

#КонецОбласти

#Область ПрограммныйИнтерфейс

Функция СведенияОВнешнейОбработке() Экспорт

	МетаданныеОбработки = Метаданные();

	ПараметрыРегистрации = ДополнительныеОтчетыИОбработки.СведенияОВнешнейОбработке("2.2.2.1");
	ПараметрыРегистрации.Вид    = ДополнительныеОтчетыИОбработкиКлиентСервер.ВидОбработкиПечатнаяФорма();
	ПараметрыРегистрации.Версия = "1.0";

	ПараметрыРегистрации.Назначение.Добавить("Документ.СчетНаОплату");

	НоваяКоманда = ПараметрыРегистрации.Команды.Добавить();
	НоваяКоманда.Представление        = МетаданныеОбработки.Представление();
	НоваяКоманда.Идентификатор        = МетаданныеОбработки.Имя;
	НоваяКоманда.Использование        = ДополнительныеОтчетыИОбработкиКлиентСервер.ТипКомандыВызовСерверногоМетода();
	НоваяКоманда.ПоказыватьОповещение = Ложь;
	НоваяКоманда.Модификатор = "ПечатьMXL";

	Возврат ПараметрыРегистрации;

КонецФункции

Процедура Печать(МассивОбъектов, КоллекцияПечатныхФорм, ОбъектыПечати, ПараметрыВывода) Экспорт

	// TODO: Реализация

КонецПроцедуры

#КонецОбласти

#Область СлужебныеПроцедурыИФункции

#КонецОбласти
```

## Next steps

- Add another command: `/epf-bsp-add-command`
- Add a form: `/form-add`
- Add a template: `/template-add`
- Build EPF: skill `1c-batch`, command `build-epf`
