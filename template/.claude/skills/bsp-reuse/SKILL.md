---
name: bsp-reuse
description: Review of BSL code for "reinventing the wheel" - a custom implementation where a ready public BSP function exists (ОбщегоНазначения, СтроковыеФункции, ФайловаяСистема, Пользователи etc.). Use during code review to suggest replacing manual code with a BSP call.
allowed-tools:
  - Read
  - Grep
  - Glob
---

# /bsp-reuse - review for "reinventing the wheel" instead of BSP functions

Tells the reviewer that the developer wrote a **custom** implementation where
the Standard Subsystems Library (BSP) already has a ready **public**
function. Example: instead of `ОбщегоНазначения.ЗначениеРеквизитаОбъекта(Ссылка,
"Склад")` a separate query for one attribute is written, or `Ссылка.Склад` is accessed
in a loop.

This is a manual review skill: a script cannot reliably detect a "wheel" (this is
semantics). The skill provides a catalog of the public BSP API by topic and
a method for finding a ready replacement from the developer's code.

## Finding severity

A single scale (as in `bsl_ls`: critical/important/minor). A bsp-reuse finding is
**minor** by default - duplication/readability, phrase it as "consider
replacing". A finding is **important** if the manual implementation hurts performance -
extra DBMS queries: reading attributes/presentations in a loop over refs, a custom
query for 1-2 attributes by one ref instead of a list function
(`ЗначенияРеквизитовОбъектов`), writing to the log/creating objects in a loop. Calling
an **obsolete** BSP function is minor (suggest the current replacement). The verdict
rule (critical|important → rework) is in the `reviewer` checklist.

## How to apply during review

1. Walk the diff and pick out two kinds of candidates:
   - **Developer's own helper functions** (`Функция МойРазбор...`,
     `ЗначениеПоСсылке`, `РазбитьСтроку`, `УдалитьДубли`, structure copying
     etc.) - check whether they already exist in BSP.
   - **Inline constructs**: loops, accumulation into an array/string, manual queries
     for one attribute, string parsing, work with files/dates - for many of these
     there is a single BSP function.
2. Determine the **topic** of the code (object attributes, collections, strings, files,
   users, prohibition dates etc.) and open the needed catalog section:
   - `reference/obshego.md` - the **ОбщегоНазначения** module and its client-server
     variants (the main source of "wheels", look here first).
   - `reference/modules.md` - the remaining 15 module groups.
3. For a match found, issue a finding: what is written manually → which
   BSP function to call. **Specify the exact signature** from the catalog.

Read the catalogs **on demand** (only the needed section) so as not to inflate the
context.

## Three rules without which the finding will be false

1. **Public interface only.** Recommend functions from modules like
   `ОбщегоНазначения`, `СтроковыеФункцииКлиентСервер`, `ФайловаяСистема` etc.
   **Never** recommend `*Служебный*`, `*СлужебныйКлиент*`,
   `*ВызовСервера*`, `*ПовтИсп`, `*Локализация`, `*Переопределяемый`,
   `*Глобальный` modules - this is BSP internal kitchen, they must not be called from application code.
   The catalog lists only public functions.

2. **Client/server context.** Many functions have a server and a client
   module with the same name (`ОбщегоНазначения` / `ОбщегоНазначенияКлиент`,
   `ФайловаяСистема` / `ФайловаяСистемаКлиент`). Recommend the one available
   in the code context: a server module is not visible from `&НаКлиенте`, and vice versa.
   `*КлиентСервер` modules are available everywhere.

3. **Do not suggest obsolete functions.** Functions marked in the catalog `⚠ устар.`
   must not be recommended - the current replacement is given for them. If the developer
   calls an obsolete BSP function themselves, that is also a finding: suggest switching to the
   current one.

## How a match is found

- By the **name of the developer's helper function**: estimate the purpose and find the topic in
  the catalog. `ПолучитьЗначениеРеквизита`, `РеквизитПоСсылке` → object attributes;
  `РазбитьСтроку`, `СтрокаВМассив` → strings; `КопияТаблицы` → collections.
- By an **inline pattern**. Common "wheel" markers (detectable among others
  by the `code-analyze` skill):

| Pattern in code | Probable BSP replacement |
|---|---|
| `Запрос` selecting 1-2 attributes by one ref | `ОбщегоНазначения.ЗначениеРеквизитаОбъекта` / `ЗначенияРеквизитовОбъекта` |
| `Ссылка.Реквизит` in a loop over an array of refs | `ОбщегоНазначения.ЗначенияРеквизитовОбъектов` (one query) |
| `Если Структура.Свойство("К") Тогда Знач = Структура.К …` | `ОбщегоНазначенияКлиентСервер.СвойствоСтруктуры` |
| `М = Новый Массив; М.Добавить(Знач)` for a single value | `ОбщегоНазначенияКлиентСервер.ЗначениеВМассиве` |
| manual removal of duplicates from an array by a loop | `ОбщегоНазначенияКлиентСервер.СвернутьМассив` |
| loop over a VT collecting a column into an array | `ОбщегоНазначения.ВыгрузитьКолонку` |
| manual recursive copying of a structure/VT | `ОбщегоНазначения.СкопироватьРекурсивно` |
| string splitting by a delimiter via `СтрНайти`/`Сред` | platform `СтрРазделить` (not BSP) |
| concatenation `"" + А + " из " + Б` for a template | platform `СтрШаблон` (not BSP) |
| `Метаданные().Имя = "Документ…"` to determine the kind | `ОбщегоНазначения.ЭтоДокумент` / `ЭтоСправочник` / … |
| `Лев(СтрокаСоединения…)`, custom file path parsing | `ОбщегоНазначенияКлиентСервер.РазложитьПолноеИмяФайла` and related |
| `ПолучитьИмяВременногоФайла` + manual deletion | `ФайловаяСистема.СоздатьВременныйКаталог` / `УдалитьВременныйФайл` |
| custom `HTTPСоединение` for downloading a file | `ПолучениеФайловИзИнтернета.СкачатьФайлНаСервере` |
| `ЗаписьЖурналаРегистрации(...)` in a loop | `ЖурналРегистрации.ЗаписатьСобытияВЖурналРегистрации` (batch) |
| `Пользователи.НайтиПоИмени(ИмяПользователя())` | `Пользователи.ТекущийПользователь` / `АвторизованныйПользователь` |
| manual check of the "Full rights" role | `Пользователи.ЭтоПолноправныйПользователь` / `РолиДоступны` |
| custom `ФоновыеЗадания.Выполнить` + state polling | `ДлительныеОперации.ВыполнитьФункцию` / `ВыполнитьПроцедуру` |
| manual timing with `ТекущаяУниверсальнаяДатаВМиллисекундах` | `ОценкаПроизводительности.НачатьЗамерВремени` / `ЗакончитьЗамерВремени` |
| manual amount allocation with "cents" | `ОбщегоНазначения.РаспределитьСуммуПропорциональноКоэффициентам` |
| custom email parsing/validation | `ОбщегоНазначенияКлиентСервер.АдресЭлектроннойПочтыСоответствуетТребованиям` |
| comparing versions `"1.2.3"` by parsing into parts | `ОбщегоНазначенияКлиентСервер.СравнитьВерсии` |

Full lists and signatures - in the `reference/` catalogs.

## Boundaries and false positives

- **Not every match is a wheel.** If the developer's function does
  more/less than the BSP function, the finding is optional. Describe it as
  "consider replacing", not as an error.
- **Performance.** Reading attributes in a loop over refs is not only
  duplication but also extra DBMS queries; emphasize this (optimality).
- **Subsystem availability.** Functions of the "Files", "Contact information",
  "Currency rates", "Banks", "Performance measurement" topics are available only if
  the corresponding BSP subsystem is deployed. If in doubt, phrase it
  conditionally.
- **The platform is more important than the BSP wrapper.** Some BSP functions are
  merely wrappers over platform methods. Where the platform method fully covers the task,
  recommend the **platform** method, and do **not** suggest the BSP wrapper (and mark it
  as redundant if the developer calls it):
  - string splitting → `СтрРазделить` (not `РазложитьСтрокуВМассивПодстрок`);
  - template substitution → `СтрШаблон` (not `ПодставитьПараметрыВСтроку`).
- The skill covers only 16 module groups from the catalog; other BSP subsystems
  (mail, EDI, printing etc.) are not covered here.

## Related skills

- `code-analyze` - finds some inline patterns automatically (type via metadata
  name, column copying by loop etc.).
- `query-review` - query review; overlaps on
  `СформироватьСтрокуДляПоискаВЗапросе` (escaping `ПОДОБНО`).
