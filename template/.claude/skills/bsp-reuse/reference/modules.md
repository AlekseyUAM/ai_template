# Catalog: other BSP module groups

Public API of 15 groups (except `ОбщегоНазначения*` - see `obshego.md`). Format:

> **`Модуль.Функция(Параметры)`** - purpose.
> 🚲 - what is written manually instead of this.

`⚠ устар.` - do not recommend, a replacement is given. Reminder: functions of the "Files",
"Contact information", "Banks", "Currency rates", "Performance measurement" topics
are available only with the corresponding subsystem deployed.

---

## Strings - `СтроковыеФункцииКлиентСервер` (everywhere)

The largest source of "wheels" after object attributes.

- String splitting by a delimiter → **platform `СтрРазделить(Строка, Разделитель, ПропускатьПустые)`**, not BSP.
  🚲 Custom parsing via `СтрНайти` + `Сред` in a loop. ❌ Do not recommend `СтроковыеФункцииКлиентСервер.РазложитьСтрокуВМассивПодстрок` - it is a wrapper over the platform; on supported versions take `СтрРазделить` directly.
- **`РазложитьСтрокуВМассивСлов(Значение, РазделителиСлов = Неопределено)`** - splitting into words by a set of delimiters (a delimiter is any character from the set; the platform has no direct analogue).
- Substituting parameters into a template → **platform `СтрШаблон(Шаблон, Пар1…Пар10)`** (`%1…%N`), not BSP.
  🚲 Concatenation `"Текст " + Знач1 + " из " + Знач2`; manual replacement of `%1`. ❌ Do not recommend `СтроковыеФункцииКлиентСервер.ПодставитьПараметрыВСтроку` / `ПодставитьПараметрыВСтрокуИзМассива` - these are wrappers over the platform; take `СтрШаблон` directly.
- **`ВставитьПараметрыВСтроку(Шаблон, Параметры)`** - replacement of named `[Параметр]` with values.
- **`ПараметрыИзСтроки(СтрокаПараметров, Разделитель = ";")`** - parsing "key=value;…" into a map.
- **`СформироватьСтрокуСимволов(Символ, ДлинаСтроки)`** - a string of a repeating character.
  🚲 Loop with character concatenation.
- **`ДополнитьСтроку(Значение, ДлинаСтроки, Символ = "0", Режим = "Слева")`** - padding to length (leading zeros).
  🚲 Loop adding zeros on the left.
- **`УдалитьПовторяющиесяСимволы(Значение, УдаляемыйСимвол, Режим = "Слева")`** - trim repeated characters at the edges.
- **`СократитьДвойныеКавычки(Значение)`** - remove surrounding `"`.
- **`УдалитьПоследнийСимволВСтроке(Текст, ЧислоСимволов = 1)`** - trim N characters on the right.
  🚲 `Лев(Текст, СтрДлина(Текст) - 1)`.
- **`ТолькоЦифрыВСтроке(Значение, ...)`** / **`ТолькоЛатиницаВСтроке(...)`** / **`ТолькоСимволыНациональногоАлфавитаВСтроке(...)`** - string composition checks.
  🚲 Character-by-character loop with a character code check.
- **`ЭтоУникальныйИдентификатор(Значение)`** - whether the string looks like a UUID.
- **`ЗаменитьОдниСимволыДругими(ЗаменяемыеСимволы, Значение, СимволыЗамены)`** - character-by-character replacement.
- **`СтрокаВЧисло(Значение)`** / **`СтрокаВДату(Значение, ЧастьДаты)`** - safe conversion without exceptions (return `Неопределено`/an empty date).
  🚲 `Попытка Число(Строка) Исключение …`.
- **`ИзвлечьТекстИзHTML(ИсходныйТекст)`** - text without HTML tags.
  🚲 Custom tag stripper with regexes.
- **`ПреобразоватьЧислоВРимскуюНотацию(Число)`** / **`ПреобразоватьЧислоВАрабскуюНотацию(Строка)`** - conversion to Roman and Arabic notation.
- **`СтрокаСЧисломДляЛюбогоЯзыка(Шаблон, Число, Вид, ФорматнаяСтрока)`** - number + word form ("1 minute / 2 minutes / 5 minutes").
  🚲 Custom plural form selection. ⚠ obsolete: `ФормаМножественногоЧисла`, `ЧислоЦифрамиПредметИсчисленияПрописью`.

### `СтроковыеФункции` (server) / `СтроковыеФункцииКлиент` (client)
- **`ФорматированнаяСтрока(Шаблон, Параметр1 … Параметр5)`** - formatted string with style tags/images/links.
  🚲 Manual assembly of `ФорматированнаяСтрока` via `Новый ФорматированныйДокумент`. ⚠ obsolete: the same-named one in `СтроковыеФункцииКлиентСервер`.
- **`СтрокаЛатиницей(Значение)`** - transliteration.
  🚲 Custom transliteration table.
- **`ПредставлениеПериодаВТексте(ДатаНачала, ДатаОкончания, ФорматнаяСтрока, СЗаглавной)`** - "from … to …" as a string.

---

## File system - `ФайловаяСистема` (server) / `ФайловаяСистемаКлиент` (client)

- **`ФайловаяСистема.СоздатьВременныйКаталог(Расширение = "")`** + **`УдалитьВременныйКаталог(Путь)`** / **`УдалитьВременныйФайл(Путь)`** - temporary files/directories with proper cleanup.
  🚲 `ПолучитьИмяВременногоФайла()` + `СоздатьКаталог` + manual deletion in `Попытке`. ⚠ obsolete: `ОбщегоНазначения.СоздатьВременныйКаталог/УдалитьВременныйКаталог`.
- **`ФайловаяСистема.УникальноеИмяФайла(ИмяФайла)`** (also available on the client) - a unique name in a directory ("file (2).txt").
  🚲 Custom loop with existence check and increment.
- **`ФайловаяСистема.ОбщийКаталогВременныхФайлов(ВложенныйКаталог)`** - a shared network temporary files directory (for client-server).
- **`ФайловаяСистема.ЗапуститьПрограмму(КомандаЗапуска, ПараметрыЗапускаПрограммы)`** + **`ПараметрыЗапускаПрограммы()`** (also available on the client) - launching an external program/OS command.
  🚲 `Новый COMОбъект("WScript.Shell")`; the obsolete `ЗапуститьПриложение`. ⚠ obsolete: `ОбщегоНазначенияКлиентСервер.ЗапуститьПрограмму`.

### `ФайловаяСистемаКлиент` (client) - working with user files
- **`ЗагрузитьФайл(ОбработчикЗавершения, ПараметрыЗагрузки, ...)`** / **`ЗагрузитьФайлы(...)`** + **`ПараметрыЗагрузкиФайла()`** - file selection and placing into temporary storage.
  🚲 Manual combination of `НачатьПомещениеФайла`/`НачатьПомещениеФайлов` with a dialog.
- **`СохранитьФайл(ОбработчикЗавершения, РасположениеФайла, ...)`** / **`СохранитьФайлы(...)`** + parameter constructors - get and save to the user's file system.
- **`ОткрытьФайл(РасположениеФайла, ...)`** + **`ПараметрыОткрытияФайла()`** - open the file in an external program.
- **`ОткрытьПроводник(ПутьККаталогуИлиФайлу)`** / **`ОткрытьНавигационнуюСсылку(Ссылка, Оповещение)`** - file explorer / navigation link.
  🚲 ⚠ obsolete analogues in `ОбщегоНазначенияКлиент`.
- **`ВыбратьКаталог(ОбработчикЗавершения, Заголовок, Каталог)`** / **`ПоказатьДиалогВыбора(...)`** - dialogs.
- **`ПодключитьРасширениеДляРаботы1СПредприятия(...)`** - the file handling extension in the web client.
  🚲 ⚠ obsolete: `ПодключитьРасширениеДляРаботыСФайлами`, analogues in `ОбщегоНазначенияКлиент`.

---

## Attached files - `РаботаСФайлами` (server) / `РаботаСФайламиКлиент`

The "File management" subsystem (file catalogs, versions, volumes). Needed when
attaching files to objects.

- **`РаботаСФайлами.ДвоичныеДанныеФайла(ПрисоединенныйФайл, ВызыватьИсключение)`** / **`ДвоичныеДанныеФайлов(...)`** - get the binary data of a file.
  🚲 Manual reading from a volume/value storage.
- **`РаботаСФайлами.ДанныеФайла(ПрисоединенныйФайл, ...)`** - file information (structure).
- **`РаботаСФайлами.ДобавитьФайл(ПараметрыФайла, АдресФайлаВоВременномХранилище, ...)`** + **`ПараметрыДобавленияФайла(...)`** - create an attached file.
- **`РаботаСФайлами.ДобавитьФайлСДиска(ВладелецФайлов, ПутьКФайлуНаДиске)`** - add from the file system. ⚠ obsolete: `СоздатьФайлНаОсновеФайлаНаДиске`.
- **`РаботаСФайлами.ОбновитьФайл(ПрисоединенныйФайл, ИнформацияОФайле)`** - update data/text/date.
- **`РаботаСФайлами.СкопироватьПрисоединенныеФайлы(Источник, Получатель)`** - copy all files of an object.
- **`РаботаСФайлами.ПриСозданииНаСервере/ПриЗаписиНаСервере(...)`** - embedding file fields into a form (handlers).
- **`РаботаСФайламиКлиент.ОткрытьФайл(ДанныеФайла, ДляРедактирования)`** / **`ДобавитьФайлы(...)`** / **`СохранитьФайлКак(...)`** - interactive operations.

---

## Event log - `ЖурналРегистрации` (server) / `ЖурналРегистрацииКлиент`

- **`ЖурналРегистрации.ЗаписатьСобытияВЖурналРегистрации(СобытияДляЖурналаРегистрации)`** - **batch** writing of a set of events in one call.
  🚲 `ЗаписьЖурналаРегистрации(...)` in a loop per record (slow).
- **`ЖурналРегистрацииКлиент.ДобавитьСообщениеДляЖурналаРегистрации(ИмяСобытия, Уровень, Комментарий, ...)`** + **`ЗаписатьСобытияВЖурналРегистрации()`** - accumulate messages on the client and write them in a batch (one server call).
  🚲 A separate server call for each client log record.
- **`ЖурналРегистрацииКлиент.ОткрытьЖурналРегистрации(Отбор, Владелец)`** - open the log with a filter.

---

## Users - `Пользователи` (server) / `ПользователиКлиент`

- **`ТекущийПользователь()`** / **`АвторизованныйПользователь()`** (also available on the client) - the current user (the second one accounts for external users).
  🚲 `Пользователи.НайтиПоИмени(ИмяПользователя())`; custom search in the catalog.
- **`ЭтоПолноправныйПользователь(Пользователь, ПроверятьАдминистрирование, ...)`** (also available on the client) - whether the user has full rights.
  🚲 `РольДоступна("ПолныеПрава")`; check `ПривилегированныйРежим()`.
- **`РолиДоступны(ИменаРолей, Пользователь, ...)`** - whether at least one of the roles is available (or full rights).
  🚲 Several `РольДоступна(...)` via `ИЛИ`.
- **`ЭтоСеансВнешнегоПользователя()`** (also available on the client) - external user login.
- **`СвойстваПользователяИБ(ИмяИлиИдентификатор)`** / **`УстановитьСвойстваПользователяИБ(...)`** / **`НовоеОписаниеПользователяИБ(...)`** - infobase user properties as a structure.
  🚲 Direct work with `ПользователиИнформационнойБазы` and manual property assembly.
- **`НайтиПоИмени(ИмяДляВхода)`** / **`НайтиПоИдентификатору(Идентификатор)`** / **`НайтиПоСсылке(Пользователь)`** - link between the catalog and the infobase user.
- **`СоздатьПароль(СвойстваПароля, ...)`** + **`СвойстваПароля()`** - password generation according to complexity rules.
  🚲 Custom random password generator.
- **`ГруппаВсеПользователи()`**, **`СсылкаНеуказанногоПользователя(...)`**, **`ПолноеИмяНеуказанногоПользователя()`** - standard predefined values.

> ⚠ obsolete: the whole `ПользователиКлиентСервер` (`ТекущийПользователь`,
> `АвторизованныйПользователь` etc.) → `Пользователи`/`ПользователиКлиент`.

---

## Long operations - `ДлительныеОперации` (server) / `ДлительныеОперацииКлиент`

- **`ДлительныеОперации.ВыполнитьФункцию(ПараметрыВыполнения, ИмяФункции, Пар1…Пар7)`** / **`ВыполнитьПроцедуру(...)`** + **`ПараметрыВыполненияФункции(ИдентификаторФормы)`** / **`ПараметрыВыполненияПроцедуры()`** - launch in a background job.
  🚲 Direct `ФоновыеЗадания.Выполнить(...)` with a home-made state poll.
- **`ДлительныеОперации.ВыполнитьФункциюВНесколькоПотоков(...)`** / **`ВыполнитьПроцедуруВНесколькоПотоков(...)`** - multithreaded execution.
- **`ДлительныеОперации.СообщитьПрогресс(Процент, Текст, ...)`** / **`ПрочитатьПрогресс(Идентификатор)`** - operation progress.
- **`ДлительныеОперации.ЗаданиеВыполнено(Идентификатор, ...)`** / **`ОтменитьВыполнениеЗадания(Идентификатор)`** / **`СообщенияПользователю(...)`** - job control.
- **`ДлительныеОперацииКлиент.ОжидатьЗавершение(ДлительнаяОперация, ОповещениеОЗавершении, ПараметрыОжидания)`** + **`ПараметрыОжидания(ФормаВладелец)`** - waiting with a progress window.
  🚲 Custom `ПодключитьОбработчикОжидания` with background polling.

> ⚠ obsolete: `ВыполнитьВФоне` → `ВыполнитьФункцию`/`ВыполнитьПроцедуру`;
> `ДлительныеОперацииКлиент.ОткрытьФормуДлительнойОперации` and
> `ИнициализироватьПараметрыОбработчикаОжидания` → `ОжидатьЗавершение`.

---

## Change prohibition dates - `ДатыЗапретаИзменения` (server)

- **`ИзменениеЗапрещено(ДанныеИлиПолноеИмя, ИдентификаторДанных, ...)`** - whether data modification is prohibited by a prohibition date.
  🚲 Custom calculation and comparison with the "prohibition date" from settings.
- **`НайденЗапретИзмененияДанных(ДанныеДляПроверки, ...)`** + **`ШаблонДанныхДляПроверки()`** + **`ПараметрыСообщенияОЗапрете()`** - check by the table of dates/sections/objects.
- **`ПроверитьДатыЗапретаЗагрузкиДанных(Данные, Узел, Отказ, ...)`** - check when loading from an exchange node.
- **`ОтключитьПроверкуДатЗапрета(Отключить)`** / **`ПроверкаДатЗапретаОтключена()`** - temporarily disable the check (batch processing).
- Subscription handlers: `ПроверитьДатуЗапретаИзмененияПередЗаписью*` - connect as handlers, do not rewrite.

---

## Contact information - `УправлениеКонтактнойИнформацией` (server) / `*Клиент` / `*КлиентСервер`

The "Contact information" subsystem.

- **`УправлениеКонтактнойИнформацией.КонтактнаяИнформацияОбъекта(СсылкаИлиОбъект, ВидИлиТип, Дата, ТолькоПредставление)`** / **`КонтактнаяИнформацияОбъектов(...)`** / **`КонтактнаяИнформация(Источник, Отбор)`** - get contact information of the object(s).
  🚲 Custom query to the ContactInformation tabular section.
- **`ПредставлениеКонтактнойИнформацииОбъекта(СсылкаИлиОбъект, Вид, Разделитель, ...)`** - contact information presentation as a string.
- **`ДобавитьКонтактнуюИнформацию(СсылкаИлиОбъект, ЗначениеИлиПредставление, Вид, ...)`** / **`УстановитьКонтактнуюИнформациюОбъекта(СсылкаИлиОбъект, КИ, Замещать)`** - writing contact information.
- **`СведенияОбАдресе(Адрес, ...)`** / **`СведенияОбАдресах(Адреса, ...)`** - parsing an address into fields (city, street, postal code…).
  🚲 Custom address string parser.
- **`ПредставлениеАдреса(Адрес, ПараметрыПредставленияАдреса)`** + **`НовыеПараметрыПредставленияАдреса()`** - formatted address.
- **`СведенияОТелефоне(КИ)`** / **`НомерТелефонаКонтактнойИнформации(КИ)`** - phone parsing.
- **`*КлиентСервер.СформироватьПредставлениеТелефона(КодСтраны, КодГорода, Номер, Добавочный, Комментарий)`** - phone as a string.
  🚲 Manual gluing of number parts.
- **`ДанныеСтраныМира(КодСтраны, Наименование)`** / **`СтранаМираПоКодуИлиНаименованию(...)`** - country catalog/classifier.
- `*Клиент`: **`СоздатьЭлектронноеПисьмо(...)`** / **`СоздатьSMS(...)`** / **`ПозвонитьПоТелефону(Номер)`** / **`ПоказатьАдресНаКарте(Адрес, Сервис)`** - contact information actions.

---

## Downloading files from the internet - `ПолучениеФайловИзИнтернета` (server) / `*Клиент`

- **`СкачатьФайлНаСервере(URL, ПараметрыПолучения, ЗаписыватьОшибку)`** / **`СкачатьФайлВоВременноеХранилище(URL, ...)`** - download via http(s)/ftp.
  🚲 Custom `Новый HTTPСоединение` + `Получить` + proxy/error handling.
- **`*Клиент.СкачатьФайлНаКлиенте(URL, ...)`** - download on the client.
- **`НастройкиПроксиНаСервере()`** / **`НастройкиПроксиНаКлиенте()`** / **`ПолучитьПрокси(URLИлиПротокол)`** - proxy settings.
  🚲 Manual creation of `Новый ИнтернетПрокси`.
- **`ДиагностикаСоединения(URL, ...)`** - checking resource availability. ⚠ obsolete analogue in `ОбщегоНазначения`.

---

## Performance measurement - `ОценкаПроизводительности` (server) / `*Клиент`

- **`ОценкаПроизводительности.НачатьЗамерВремени()`** + **`ЗакончитьЗамерВремени(КлючеваяОперация, ВремяНачала, ...)`** - measuring a key operation on the server.
  🚲 Manual `ТекущаяУниверсальнаяДатаВМиллисекундах()` with subtraction and custom logging.
- **`ОценкаПроизводительностиКлиент.ЗамерВремени(КлючеваяОперация, ...)`** / **`ЗавершитьЗамерВремени(УИДЗамера, ...)`** - measurement on the client.
- **`НачатьЗамерДлительнойОперации(...)`** + **`ЗафиксироватьЗамерДлительнойОперации(...)`** + **`ЗакончитьЗамерДлительнойОперации(...)`** - step-by-step measurement.

> ⚠ obsolete: `ОценкаПроизводительностиКлиент.НачатьЗамерВремени` → `ЗамерВремени`.

---

## Loading/unloading data via files

- **`ЗагрузкаДанныхИзФайлаКлиент.ПоказатьФормуЗагрузки(ПараметрыЗагрузки, ОповещениеОЗагрузке)`** + **`ПараметрыЗагрузкиДанных()`** - the standard form for loading a tabular section from a file (Excel/CSV/mxl).
  🚲 Custom file parsing and tabular section filling.
- **`ЗагрузкаДанныхИзФайла.СформироватьОписаниеКолонок(Таблица, Колонки)`** / **`ТаблицаСопоставления(АдресРезультата)`** / **`НастройкиЗагрузкиДанных()`** - the server part of mapping.
- **`ВыгрузкаОбъектовВФайлы.СохранитьПоФорматуВФайл(КомандыВыгрузки, СписокОбъектов, НастройкиСохранения)`** - unloading objects to files (print forms/attachments).

---

## Safe mode / external resources - `РаботаВБезопасномРежиме` (server) / `*Клиент`

Permissions to use external resources (security profiles).

- **`РазрешениеНаИспользованиеКаталогаФайловойСистемы(...)`**, **`РазрешениеНаИспользованиеИнтернетРесурса(Протокол, Адрес, Порт, ...)`**, **`РазрешениеНаСозданиеCOMКласса(...)`**, **`РазрешениеНаИспользованиеПриложенияОперационнойСистемы(...)`**, **`РазрешениеНаИспользованиеВнешнейКомпоненты(...)`** and others - permission description constructors.
  🚲 Manual formation of permission requests.
- **`ЗапросНаИспользованиеВнешнихРесурсов(НовыеРазрешения, Владелец, РежимЗамещения)`** / **`ЗапросНаОтменуРазрешенийИспользованияВнешнихРесурсов(...)`** / **`ЗапросНаОчисткуРазрешений...(Владелец)`** - permission requests.
- **`УстановленБезопасныйРежим()`** - safe mode check.
- **`*Клиент.ПрименитьЗапросыНаИспользованиеВнешнихРесурсов(Идентификаторы, ФормаВладелец, Оповещение)`** - applying requests interactively.

---

## Banks and currency rates

### `РаботаСБанками` (server)
- **`СведенияБИК(БИК, КоррСчет, ТолькоАктуальные)`** - bank data from the BIK catalog.
  🚲 Custom query to `КлассификаторБанков`/`Банки`. ⚠ obsolete: `ПолучитьДанныеКлассификатора`.
- **`ПояснениеНедействительногоБанка(Банк)`** - the reason for invalidity.

### `РаботаСКурсамиВалют` (server)
- **`ПолучитьКурсВалюты(Валюта, ДатаКурса)`** - rate on a date.
  🚲 Custom query to the `КурсыВалют` register with a last slice.
- **`ПересчитатьВВалюту(Сумма, ИсходнаяВалюта, НоваяВалюта, Дата)`** - conversion between currencies.
  🚲 Manual conversion by rates and multiplicities.
- **`СформироватьСуммуПрописью(СуммаЧислом, Валюта, БезДробной, КодЯзыка, ...)`** - amount in words.
  🚲 Custom "amount in words" algorithm.
- **`ОписаниеТипаДенежногоПоля(ДопустимыйЗнакПоля)`** - type constructor for money fields.
- **`ДобавитьВалютыПоКоду(КодыВалют)`** - add currencies from the classifier (initial filling).
