# Catalog: ОбщегоНазначения (and client-server variants)

Public API of the `ОбщегоНазначения` (server), `ОбщегоНазначенияКлиентСервер`
(everywhere), `ОбщегоНазначенияКлиент` (client) modules. Entry format:

> **`Функция(Параметры)`** - purpose.
> 🚲 - what the developer usually writes manually instead of this.

The context is given in the subsection heading. `⚠ устар.` - do not recommend, a replacement is given.
The most frequent source of "wheels" - object attributes and collections.

---

## Object attributes - `ОбщегоНазначения` (server)

The main topic. Reading an attribute via `Ссылка.Реквизит` makes an implicit query;
in a loop - N queries. BSP reads with one query and accounts for rights.

- **`ЗначениеРеквизитаОбъекта(Ссылка, ИмяРеквизита, ВыбратьРазрешенные = Ложь)`** - the value of one attribute by ref, in one query.
  🚲 Custom `Запрос` for one field; `Ссылка.Реквизит` in heavy code; helper `ПолучитьРеквизит`.
- **`ЗначенияРеквизитовОбъекта(Ссылка, Реквизиты, ВыбратьРазрешенные = Ложь)`** - a structure of values of several attributes of one ref (`Реквизиты` is the string "Склад,Организация" or an array/structure).
  🚲 Several `Ссылка.А`, `Ссылка.Б` accesses in a row; a query for a couple of fields.
- **`ЗначенияРеквизитовОбъектов(Ссылки, Реквизиты, ВыбратьРазрешенные = Ложь)`** - a map "ref → structure of values" for a set of refs, **in one query**.
  🚲 Loop `Для Каждого Ссылка Из Массив … Ссылка.Реквизит` (N DBMS queries).
- **`ЗначениеРеквизитаОбъектов(МассивСсылок, ИмяРеквизита, ВыбратьРазрешенные = Ложь)`** - a map "ref → value of one attribute" for a set of refs.
  🚲 The same loop for one field.
- **`УстановитьЗначениеРеквизита(Объект, ИмяРеквизита, Значение)`** / **`УстановитьЗначенияРеквизитов(Объект, Значения)`** - safely fill attribute(s), with an existence check.
- **`ЕстьРеквизитОбъекта(ИмяРеквизита, МетаданныеОбъекта)`** - whether an attribute with such a name exists.
  🚲 Custom iteration over `МетаданныеОбъекта.Реквизиты`.

### `ОбщегоНазначенияКлиентСервер`
- **`ЕстьРеквизитИлиСвойствоОбъекта(Объект, ИмяРеквизита)`** - whether an arbitrary object has an attribute/property without accessing metadata.
  🚲 `Попытка … Объект[Имя] … Исключение` just to check presence.

---

## Predefined items, posting, refs - `ОбщегоНазначения`

- **`ПредопределенныйЭлемент(ПолноеИмяПредопределенного)`** - the ref of a predefined item by full name ("Справочник.Валюты.Рубль"), including where direct access is unavailable.
  🚲 A query for the predefined item; storing its ref by hand.
- **`ЭтоПредопределенныеЭлементы(Элементы)`** - the predefined flag (accounting for rights).
- **`ПроверитьПроведенностьДокументов(Документы)`** - returns unposted documents from the list.
  🚲 Loop with a `Докумен.Проведен` check.
- **`ПровестиДокументы(Документы)`** - attempts to post, returns those that failed.
- **`ЕстьСсылкиНаОбъект(СсылкаИлиМассив, ИскатьСредиСлужебных = Ложь)`** - whether there are refs to the object in the database.
  🚲 Custom search for usage locations by queries.
- **`ЗаменитьСсылки(ПарыЗамен, ПараметрыЗамены = Неопределено)`** - replacement of refs in all data.
- **`МестаИспользования(НаборСсылок, АдресРезультата = "")`** - all usage locations of refs.
- **`ИмяЗначенияПеречисления(Значение)`** - the enum value name by ref.

---

## Collections: arrays, structures, maps - `ОбщегоНазначенияКлиентСервер`

Available on both the client and the server.

- **`ЗначениеВМассиве(Значение)`** - an array of one value.
  🚲 `М = Новый Массив; М.Добавить(Знач);` - three lines for one element (a frequent wheel when passing a filter).
- **`СвернутьМассив(Массив)`** - a copy of the array with unique values.
  🚲 Removing duplicates by a loop via nested search / via a map.
- **`РазностьМассивов(Массив, МассивВычитания)`** - elements of the first that are absent in the second.
  🚲 Double loop with `Найти`.
- **`ДополнитьМассив(Приемник, Источник, ТолькоУникальные = Ложь)`** - add all array elements.
  🚲 Loop `Для Каждого … Приемник.Добавить`.
- **`УдалитьЗначениеИзМассива(Массив, Значение)`** / **`УдалитьВсеВхожденияЗначенияИзМассива(Массив, Значение)`** / **`УдалитьВсеВхожденияТипаИзМассива(Массив, Тип)`** - removing elements.
  🚲 Reverse loop over indexes with `Удалить`.
- **`СвойствоСтруктуры(Структура, Ключ, ЗначениеПоУмолчанию = Неопределено)`** - the property value or a default value.
  🚲 `Если Структура.Свойство("К") Тогда Знач = Структура.К Иначе Знач = …`.
- **`ДополнитьСтруктуру(Приемник, Источник, Заменять = Неопределено)`** / **`ДополнитьСоответствие(Приемник, Источник, Заменять)`** - merging.
  🚲 Loop `Для Каждого КлючЗначение Из Источник`.
- **`КлючиСтруктурыВСтроку(Структура, Разделитель = ",")`** - a string of keys.
  🚲 Loop with key gluing.
- **`СпискиЗначенийИдентичны(Список1, Список2)`** - comparison of value lists/arrays by values.
- **`ДополнитьСписок(СписокПриемник, СписокИсточник, ...)`** - merging value lists.

### Value tables - `ОбщегоНазначения` (server)
- **`ВыгрузитьКолонку(КоллекцияСтрок, ИмяКолонки, ТолькоУникальные = Ложь)`** - an array of column values.
  🚲 Loop over VT rows collecting values into an array.
- **`ТаблицаЗначенийВМассив(ТаблицаЗначений)`** - an array of structures (to pass a VT to the client).
  🚲 Manual moving of rows into an array of structures.
- **`СтрокаТаблицыЗначенийВСтруктуру(СтрокаТЗ)`** - VT row → structure by columns.
- **`КоллекцииИдентичны(К1, К2, ИменаКолонок = "", ...)`** - row-by-row comparison of VT/tree.
  🚲 Custom row-by-row comparing loop.
- **`СтруктураПоМенеджеруЗаписи(МенеджерЗаписи, МетаданныеРегистра)`** - set dimensions/resources/attributes into a structure.

### `ОбщегоНазначенияКлиентСервер` - tables (without types unavailable on the client)
- **`ДополнитьТаблицу(ТаблицаИсточник, ТаблицаПриемник)`** - copy rows of one VT into another.
  🚲 Loop with `ЗаполнитьЗначенияСвойств` over rows.
- **`ДополнитьТаблицуИзМассива(Таблица, Массив, ИмяПоля)`** - VT rows from an array of values.

---

## Copying and comparing data

### `ОбщегоНазначения` (server) and `ОбщегоНазначенияКлиент` (client)
- **`СкопироватьРекурсивно(Источник, ФиксироватьДанные = Неопределено)`** - a full copy of a structure/map/array/list/VT accounting for nesting.
  🚲 Manual traversal with collection recreation; the obsolete `СкопироватьСтруктуру`/`СкопироватьМассив`.
- **`ОбщегоНазначения.ДанныеСовпадают(Данные1, Данные2)`** - comparison of complex nested data.
  🚲 Custom recursive comparator.
- **`ОбщегоНазначения.ФиксированныеДанные(Данные, ВызыватьИсключение = Истина)`** - recursive fixation of a structure/map/array.
- **`ОбщегоНазначения.КонтрольнаяСуммаСтрокой(Данные, Алгоритм = Неопределено)`** - a checksum of arbitrary data.
  🚲 Custom hash via `ХешированиеДанных` with serialization.

> ⚠ obsolete in `ОбщегоНазначенияКлиентСервер`: `СкопироватьСтруктуру`,
> `СкопироватьСоответствие`, `СкопироватьМассив`, `СкопироватьСписокЗначений`,
> `СкопироватьРекурсивно` → use `СкопироватьРекурсивно` from
> `ОбщегоНазначения`/`ОбщегоНазначенияКлиент`. `СократитьМассив` → `РазностьМассивов`.

---

## Types and metadata - `ОбщегоНазначения` (server)

Determining the object kind by metadata name is a classic antipattern
(caught by `code-analyze: type-check-via-metadata-name`).

- **`ЭтоДокумент / ЭтоСправочник / ЭтоПеречисление / ЭтоПланОбмена / ЭтоПланВидовХарактеристик / ЭтоПланСчетов / ЭтоПланВидовРасчета / ЭтоБизнесПроцесс / ЭтоЗадача / ЭтоРегистрСведений / ЭтоРегистрНакопления / ЭтоРегистрБухгалтерии / ЭтоРегистрРасчета / ЭтоКонстанта / ЭтоЖурналДокументов / ЭтоПоследовательность / ЭтоРегламентноеЗадание / ЭтоРегистр(ОбъектМетаданных)`** - membership in a common type.
  🚲 Parsing `Строка(ТипЗнч(…))`; `Метаданные().Имя`, `ПолноеИмя()` with `СтрНачинаетсяС`.
- **`ЭтоОбъектСсылочногоТипа(ОписаниеОбъекта)`** - whether the metadata object is of ref type.
- **`ЭтоСсылка(ПроверяемыйТип)`** - whether the type is a ref type.
- **`ЗначениеСсылочногоТипа(Значение)`** - whether the value is of ref type.
- **`СсылкаСуществует(ПроверяемаяСсылка)`** - whether there is a record in the database by the ref (broken).
  🚲 Query `ВЫБРАТЬ … ГДЕ Ссылка = &Ссылка` to check existence.
- **`ОбъектЯвляетсяГруппой(Объект)`** - whether the catalog/characteristic type plan item is a group.
- **`ИмяТаблицыПоСсылке(Ссылка)`** / **`ВидОбъектаПоСсылке(Ссылка)`** / **`ВидОбъектаПоТипу(ТипОбъекта)`** - full name / kind name.
  🚲 Parsing `Метаданные().ПолноеИмя()` with string functions.
- **`ОбъектМетаданныхПоПолномуИмени(ПолноеИмя)`** - a fast analogue of `Метаданные.НайтиПоПолномуИмени`.
- **`МенеджерОбъектаПоПолномуИмени(ПолноеИмя)`** / **`МенеджерОбъектаПоСсылке(Ссылка)`** - the object manager.
  🚲 A long `Если … Документы[Имя] … ИначеЕсли Справочники[Имя]`.
- **`СтроковоеПредставлениеТипа(Тип)`** - "СправочникСсылка.Имя" by type.
- **`ИдентификаторОбъектаМетаданных(…)`** / **`ОбъектМетаданныхПоИдентификатору(…)`** - a ref identifier of a metadata object for storing in the database and back.
- **`ПредставлениеОбъекта(ОбъектМетаданных)`** / **`ПредставлениеСписка(ОбъектМетаданных)`** - synonym/presentation from metadata properties.
- **`ОписаниеТипаСтрока(ДлинаСтроки)` / `ОписаниеТипаЧисло(...)` / `ОписаниеТипаДата(ЧастиДаты)` / `ОписаниеТипаВсеСсылки()`** - `ОписаниеТипов` constructors.
  🚲 Manual creation of `Новый ОписаниеТипов` with a type array and qualifiers.
- **`ОписаниеТипаСостоитИзТипа(ОписаниеТипа, ТипЗначения)`** - whether the description consists of a single type.
- **`ИменаРеквизитовПоТипу(Ссылка, Тип)`** - attributes of an object of the given type.

---

## Environment, configuration - `ОбщегоНазначения` (server) / `ОбщегоНазначенияКлиент`

- **`ИнформационнаяБазаФайловая()`** - whether the infobase is in file mode.
  🚲 Manual parsing of the connection string `СтрСоединенияИБ()`.
- **`ЭтоWindowsКлиент() / ЭтоWindowsСервер() / ЭтоLinuxКлиент() / ЭтоLinuxСервер() / ЭтоMacOSКлиент() / ЭтоВебКлиент() / ЭтоМобильныйКлиент()`** - OS/client detection.
  🚲 Parsing `СистемнаяИнформация().ТипПлатформы`.
- **`КлиентПодключенЧерезВебСервер()`**, **`РежимОтладки()`**, **`РаспределеннаяИнформационнаяБаза()`**, **`ЭтоПодчиненныйУзелРИБ()`**, **`РазделениеВключено()`**, **`ДоступноИспользованиеРазделенныхДанных()`** - environment flags.
- **`РедакцияКонфигурации()`** - the configuration revision ("1.2" from "1.2.3.4").
- **`ПодсистемаСуществует(ПолноеИмяПодсистемы)`** + **`ОбщийМодуль(Имя)`** - conditional call of an optional subsystem.
  🚲 `Попытка Выполнить("ОбщийМодуль.Метод()") Исключение` for a "soft" dependency.
- `ОбщегоНазначенияКлиент`: **`ДатаСеанса()`** - the current date in the session time zone (instead of `ТекущаяДата()` on the client), **`ДатаУниверсальная()`**.

> ⚠ obsolete: many such functions also exist in `ОбщегоНазначенияКлиентСервер` but
> are marked obsolete - take them from `ОбщегоНазначения`/`ОбщегоНазначенияКлиент`.

---

## Strings for queries and arithmetic - `ОбщегоНазначения` (server)

- **`СформироватьСтрокуДляПоискаВЗапросе(СтрокаПоиска)`** - escapes special characters for `ПОДОБНО`.
  🚲 Manual replacement of `%`, `_`, `[` in the pattern. See `query-review`.
- **`РазделительПакетаЗапросов()`** / **`ТекстОбъединитьВсе()`** - query text fragments.
- **`РаспределитьСуммуПропорциональноКоэффициентам(Сумма, Коэффициенты, Точность = 2)`** (also in `…КлиентСервер`) - amount allocation without losing cents.
  🚲 Manual division with the remainder added to the last row.

---

## Files, paths, email, versions, URI - `ОбщегоНазначенияКлиентСервер`

Work with a **string** path (not with the file system - that is in `ФайловаяСистема`).

- **`ДобавитьКонечныйРазделительПути(ПутьКаталога)`** - add `\`/`/` if missing.
  🚲 `Если Прав(Путь,1) <> "\" Тогда Путь = Путь + "\"`.
- **`ПолучитьПолноеИмяФайла(ИмяКаталога, ИмяФайла)`** - gluing a directory and a name.
- **`РазложитьПолноеИмяФайла(ПолноеИмяФайла, ЭтоКаталог = Ложь)`** - a structure: path, name, extension, base name.
  🚲 Custom path parsing via `СтрНайти`/`Сред` by `\` and `.`.
- **`ПолучитьРасширениеИмениФайла(ИмяФайла)`** / **`РасширениеБезТочки(Расширение)`** / **`ПолучитьИмяСРасширением(Имя, Расширение)`** - working with the extension.
- **`НайтиНедопустимыеСимволыВИмениФайла(ИмяФайла)`** / **`ЗаменитьНедопустимыеСимволыВИмениФайла(ИмяФайла, НаЧтоМенять)`** / **`ПолучитьНедопустимыеСимволыВИмениФайла()`** - file name validation.
  🚲 Custom forbidden character list and replacement.
- **`СтруктураURI(СтрокаURI)`** - parsing a URI into parts (scheme, host, port, path…).
  🚲 Manual URL parsing with string functions.
- **`АдресЭлектроннойПочтыСоответствуетТребованиям(Адрес, РазрешитьЛокальные = Ложь)`** - email validation per RFC.
  🚲 Custom regex/"@ and dot" check.
- **`АдресаЭлектроннойПочтыИзСтроки(СписокАдресов)`** / **`РазобратьСтрокуСПочтовымиАдресами(Адреса)`** - parsing an address string.
- **`СравнитьВерсии(Версия1, Версия2)`** / **`СравнитьВерсииБезНомераСборки(...)`** / **`ВерсияКонфигурацииБезНомераСборки(Версия)`** - comparison of versions "1.2.3.4".
  🚲 Custom version parsing into parts and element-by-element comparison.
- **`ЗаменитьНедопустимыеСимволыXML(Текст, СимволЗамены)`** / **`УдалитьНедопустимыеСимволыXML(Текст)`** - cleaning a string for XML.
- **`ПустойУникальныйИдентификатор()`** - empty UUID.

---

## XML / JSON serialization - `ОбщегоНазначения` (server)

- **`ЗначениеВСтрокуXML(Значение)`** / **`ЗначениеИзСтрокиXML(СтрокаXML)`** - (de)serialization of a value to/from an XML string.
  🚲 Manual `ЗаписьXML` + `СериализаторXDTO` combo every time.
- **`ЗначениеВJSON(Значение)`** / **`JSONВЗначение(Строка, ...)`** - (de)serialization to/from JSON.
  🚲 Manual `ЗаписатьJSON`/`ПрочитатьJSON` combo with write/read objects.
- **`ОбъектXDTOВСтрокуXML(ОбъектXDTO, Фабрика)`** / **`ОбъектXDTOИзСтрокиXML(СтрокаXML, Фабрика)`** - XDTO object to/from an XML string.
- **`ПрочитатьXMLВТаблицу(XML)`** - XML → value table by a description.

---

## Forms, filters, dynamic lists - `ОбщегоНазначенияКлиентСервер`

- **`ПолучитьРеквизитФормыПоПути(Форма, ПутьРеквизита)`** / **`УстановитьРеквизитФормыПоПути(Форма, Путь, Значение, ...)`** - access to a form attribute by a string path.
- **`УстановитьЭлементОтбора(ОбластьПоискаДобавления, ИмяПоля, ПравоеЗначение, ВидСравнения, ...)`** - add/replace a filter item.
  🚲 Manual creation of `ЭлементОтбора`, search for an existing one, property setting.
- **`УстановитьЭлементОтбораДинамическогоСписка(ДинамическийСписок, ИмяПоля, ПравоеЗначение, ...)`** / **`УдалитьЭлементыГруппыОтбораДинамическогоСписка(...)`** - dynamic list filter.
- **`УстановитьПараметрДинамическогоСписка(Список, ИмяПараметра, Значение, Использование = Истина)`** - dynamic list parameter.
- **`НайтиЭлементыИГруппыОтбора(...)`** / **`СоздатьГруппуЭлементовОтбора(...)`** / **`ИзменитьЭлементыОтбора(...)`** / **`УдалитьЭлементыГруппыОтбора(...)`** - working with the data composition filter tree.
- **`УстановитьСвойствоЭлементаФормы(ЭлементыФормы, ИмяЭлемента, ИмяСвойства, Значение)`** / **`ЗначениеСвойстваЭлементаФормы(...)`** - safe when the element may be absent on the form.
- `ОбщегоНазначения` (server): **`СтруктураСвойствДинамическогоСписка()`** + **`УстановитьСвойстваДинамическогоСписка(Список, СвойстваСписка)`** - query text/main table/dynamic reading in one call.

---

## Self-diagnostics and messages - `ОбщегоНазначенияКлиентСервер`

- **`Проверить(Условие, Сообщение = "", КонтекстПроверки = "")`** - an exception if the condition is false.
  🚲 `Если НЕ Условие Тогда ВызватьИсключение …`.
- **`ПроверитьПараметр(ИмяМетода, ИмяПараметра, Значение, ОжидаемыеТипы, ...)`** - parameter type check.
  🚲 Custom `Если ТипЗнч(П) <> Тип(…) Тогда ВызватьИсключение`.
- **`ДобавитьОшибкуПользователю(Ошибки, ПолеОшибки, Текст, ...)`** + **`СообщитьОшибкиПользователю(Ошибки, Отказ)`** - accumulation and output of same-type errors.
- **`ТекстОшибкиЗаполнения(...)`**, **`ПутьКТабличнойЧасти(ИмяТЧ, НомерСтроки, ИмяРеквизита)`** - texts/paths for form messages.
- `ОбщегоНазначения`/`ОбщегоНазначенияКлиент`: **`СообщитьПользователю(Текст, КлючДанных, Поле, ПутьКДанным, Отказ)`** - a message bound to data/a form field.
  🚲 Bare `Сообщить(…)` without binding to data; `Новый СообщениеПользователю` (the latter is caught by `code-analyze: user-message-via-constructor`).

---

## Code execution, settings, misc - `ОбщегоНазначения` (server)

- **`ВыполнитьВБезопасномРежиме(Алгоритм, Параметры)`** / **`ВычислитьВБезопасномРежиме(Выражение, Параметры)`** - `Выполнить`/`Вычислить` with safe mode and a security profile.
  🚲 Direct `Выполнить(Текст)` / `Вычислить(Текст)` without safe mode.
- **`ВыполнитьМетодКонфигурации(ИмяМетода, Параметры, ЭтоФункция)`** / **`ВыполнитьМетодОбъекта(Объект, ИмяМетода, ...)`** - calling a method by name accounting for security profiles.
- **`ХранилищеОбщихНастроекСохранить/Загрузить/Удалить(...)`**, similarly to `ХранилищеСистемныхНастроек*`, `ХранилищеНастроекДанныхФорм*` - work with settings storages supporting long keys and separation.
  🚲 Direct `ХранилищеОбщихНастроек.Сохранить(...)` without truncating long keys.
- **`ЗаписатьДанныеВБезопасноеХранилище(Владелец, Данные, Ключ)`** / **`ПрочитатьДанныеИзБезопасногоХранилища(Владелец, Ключи, ...)`** / **`УдалитьДанныеИзБезопасногоХранилища(...)`** - confidential data (passwords).
  🚲 Storing passwords in attributes/constants.
- **`ПодключитьКомпонентуИзМакета(Идентификатор, ПолноеИмяМакета, ...)`** - an external component from a ZIP template.
- **`СкопироватьСтрокиВБуферОбмена(ТЧ, ВыделенныеСтроки)`** / **`СтрокиИзБуфераОбмена()`** / **`ПустойБуферОбмена()`** - the internal tabular section row clipboard.
- **`РаспределитьСуммуПропорциональноКоэффициентам`** - see the arithmetic section.

---

## Client interaction - `ОбщегоНазначенияКлиент`

- **`ОповеститьОбИзмененииОбъекта(Источник, ...)`** / **`ОповеститьОбИзмененииОбъектов(Источник, ...)`** - notify forms/lists about a change.
  🚲 Bare `Оповестить("Имя", Параметр)` with home-made event names.
- **`ПоказатьПодтверждениеЗакрытияФормы(...)`** / **`ПоказатьПодтверждениеЗакрытияПроизвольнойФормы(...)`** - the standard "Data has been modified. Save?" question in `ПередЗакрытием`.
  🚲 Custom `ПоказатьВопрос` about unsaved data.
- **`ОбновитьИнтерфейсПрограммы()`** - refresh the interface while keeping the active window.
- **`ЦветСтиля(Имя)`** / **`ШрифтСтиля(Имя)`** - style elements by name.

> ⚠ obsolete in `ОбщегоНазначенияКлиент`: `ОткрытьФайлВПрограммеПросмотра`,
> `ОткрытьПроводник`, `ОткрытьНавигационнуюСсылку`, `СоздатьВременныйКаталог`,
> `ПоказатьВопросОбУстановкеРасширенияРаботыСФайлами` → moved to
> `ФайловаяСистемаКлиент` (see `modules.md`).
