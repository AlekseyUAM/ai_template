---
name: bsl-coding-standards
description: Manual code review checklist for 1C BSL code - standards requirements that cannot be checked automatically (task semantics, data flow analysis, knowledge of metadata/configuration composition, queries, TOTALS (ИТОГИ), DCS and registers are required). Use when reviewing a module after automatic checks.
allowed-tools:
  - Read
---

# bsl-coding-standards - manual review checklist for 1C BSL code

This file contains only standards requirements that **cannot be scripted** and are checked
manually. Check every item by eye. Items are grouped by topic; the checklist grows as
standards documents are analyzed.

The severity of each item follows the single scale `критичная`/`важная`/`минорная` (as in
bsl_ls / LSP static analysis); the rule for the final verdict on findings is in the reviewer checklist.

## Implicit queries in a loop

Explicit queries in a loop (`Запрос.Выполнить()`, `Новый Запрос`) and a query inside a local
module method called from the loop (depth 1) are caught automatically by `code-analyze`

- [important] **BSP standard functions in a loop** - calling in a loop
  `ОбщегоНазначения.ЗначениеРеквизитаОбъекта` / `ЗначенияРеквизитовОбъекта` (and analogues
  `КонтактнаяИнформацияОбъекта` etc.) is a **DB query on every iteration**: internally these
  functions run a query per object. `code-analyze` does not catch them (these are calls into a common
  module - cross-module). Replace with the "list" variant called once over the whole list of
  refs: `ЗначенияРеквизитовОбъектов(МассивСсылок, …)`, `КонтактнаяИнформацияОбъектов(…)` -
  one query instead of N.
- [important] **Dereferencing a ref via dot in the loop body** - find in the body of each loop
  identifiers with 1+ dot (`Ссылка.Реквизит`, `Ссылка.Реквизит.Реквизит`). If the base of the
  chain is a ref/object (and not a Structure, ValueTable, record set etc.), then
  **every** dot access is an implicit DB query for an attribute/presentation on
  each iteration. A ref cannot be automatically distinguished from a structure/collection (types are needed) -
  so this is checked by eye. Move attribute retrieval into one query over the list or
  `ОбщегоНазначения.ЗначенияРеквизитовОбъектов`.
- [important] **Getting a ref presentation in a loop** - `Строка(Ссылка)`, `Представление(...)`,
  implicit conversion of a ref to a string in a loop also hits the DB for the presentation; get
  presentations in advance with one query.
- [important] **Large call depth** - `code-analyze` expands only depth 1 and only within
  one module. If you suspect a query is hidden deeper (call chain, call
  into a common module), use `code_index` to analyze the **call graph**: walk the
  methods called from the loop (including cross-module) and check whether they access the DB.

## Search in value collections

- [important] **Column indexing on repeated searches** - if a `ТаблицаЗначений`
  with many rows (guideline - 1000+, or fewer with frequent search)
  is searched two or more times, make sure the search columns
  are indexed (`ТЗ.Индексы.Добавить(...)`); index only
  selective columns (few rows per value), otherwise there will be no effect.
- [important] **Index must match the `НайтиСтроки` structure** - when searching by several
  columns with `НайтиСтроки`, check that an index exists whose field list
  EXACTLY matches the search structure (field order does not matter). Otherwise
  the index is not used and the search is a scan. The same limitation applies to the
  `Скопировать` method with the `ПараметрыОтбора` parameter.
- [important] **Sorting `ТаблицаЗначений` by reference columns** - when sorting with `Сортировать` by
  a column with reference values, the system queries the IB for the presentation of
  each row. Check: if sorting by name is needed, add a column with the presentation
  when filling and sort by it; otherwise sort "by ref" via the `СравнениеЗначений` object.
- [important] **Search in a large `Массив`** - when searching an array with many elements
  (1000+, or fewer when searching in a loop), replace the array with `Соответствие` (if
  order does not matter) or an indexed `ТаблицаЗначений` (if order matters):
  array search is a scan.
- [important] **Uniqueness of a large array** - to ensure uniqueness of elements
  of a large array, use a single call to `ОбщегоНазначения.СвернутьМассив`
  or `ДополнитьМассив(..., ТолькоУникальныеЗначения = Истина)` at the end of the
  algorithm, not an element-by-element check in a loop.
- [important] **`ДеревоЗначений` and search** - `ДеревоЗначений` has no indexes (search
  is a scan); if frequent search over a large volume is required, replace it with an
  indexed `ТаблицаЗначений`.

## Pre-initialization of local variables

- [critical] **Initialize before branching** - if the value of a local variable
  is computed in large `Если…ИначеЕсли…Иначе` blocks, check that the variable
  is pre-initialized with a default value BEFORE the block. Otherwise, on an
  uncovered branch the variable ends up `Неопределено`, and subsequent code that
  expects a concrete type fails at runtime.

## Variable names

- [minor] **Meaningful name** - the variable name is derived from domain
  terms and reflects its purpose (`ДиалогРаботыСКаталогом`, not `масРеквизитов`,
  `соотвВидИмя`, `новСтр`).
- [minor] **CamelCase without abbreviations** - every word in the name starts with a capital letter, spaces
  removed; one-letter prepositions and pronouns are capitalized too. Prefix
  abbreviations like `мас…`, `соотв…`, `нов…` are not allowed.
- [minor] **Flag variable names** - name a variable that reflects flag state
  so that its true value reads naturally (`ЕстьОшибки`, `ЭтоТоварТара`).

## Mass string concatenation

- [minor] **Assess "massiveness"** - assess whether the concatenation volume is really massive (guideline - 1000+ operations, fewer
  for longer strings). For known-small volumes outside universal mechanisms,
  replacement with `СтрСоединить` is not mandatory - do not hurt readability for a
  micro-optimization.

## Encoding and BSL symbols

- [important] **ASCII hyphen `-` only** - in BSL code and comments, `—` (U+2014) and `–`
  (U+2013) cause `InvalidCharacterInFile` in `bsl_ls` and break the build. Before delivery,
  search for them in changed modules (`grep -nE '–|—'`; without `-P` - works in both GNU and BSD/macOS grep).

## Raising exceptions in code

- [minor] **Is an exception needed at all** - in the general case, raising an exception is not required:
  on errors the platform itself outputs a message, writes the stack to the event log and
  sends it to the error reporting service. Check that `ВызватьИсключение`
  appears for a justified reason.
- [minor] **Error category** - for business-logic exceptions shown to the user,
  do not specify a category (the default is `ИсключениеВызванноеИзВстроенногоЯзыка`).
  For others, specify a suitable one (`ОшибкаСети`, `НарушениеПравДоступа` etc.)
  so that the user gets standard recommendations. For diagnosing program
  errors (invalid parameter, wrongly integrated subsystem) use the category
  `ОшибкаКонфигурации`.
- [critical] **Rights check** - in most cases use
  `ВыполнитьПроверкуПравДоступа`; a programmatic exception with the category
  `НарушениеПравДоступа` - only to check for a specific role.
- [minor] **Error codes as strings, not numbers** - if business logic needs to analyze the error
  type, use string codes (3rd parameter of `ВызватьИсключение` or the return
  code) with a subsystem prefix; numeric codes are not allowed (unreadable).

## Catching exceptions in code

- [minor] **Catch only when necessary** - do not wrap code in
  `Попытка…Исключение` without a reason: an unhandled exception is output, logged and
  sent to the error reporting service as designed. Catching is justified only
  when you need to refine the technical text with application information or run your own
  diagnostics (e.g., in IB update handlers).
- [important] **Locality of the `Попытка` block** - do not open large `Попытка…Исключение` blocks;
  place them precisely around a specific potentially problematic call so as not to
  catch unrelated errors of neighboring code.
- [critical] **Do not interpret the exception text** - do not analyze the error text to
  determine the cause (the text depends on localization/version); use error
  categories (`ИнформацияОбОшибке.ЯвляетсяОшибкойКатегории`) or error codes.
- [important] **Correct error representation functions** - for the event log use
  `ОбработкаОшибок.ПодробноеПредставлениеОшибки` (returns the stack), for the message
  to the user - `ОбработкаОшибок.СообщениеОбОшибкеДляПользователя` (preserves
  refinements when rethrown).

## Structure-type objects

- [minor] **Structure with default values at once** - do not add properties to a structure
  in different parts of the code with a later `Свойство("…")` check; create the structure
  with a full set of default properties in one place (usually a constructor function).
  Exception - structures with an unfixed format (data from external sources,
  system form parameters).

## Structures and value tables as procedure and function parameters

- [minor] **Parameter constructor function** - for a function with a `Структура`/
  `ТаблицаЗначений`/`ДеревоЗначений` parameter, define a constructor function nearby that
  returns a blank structure with properties (or an empty typed VT);
  the calling code fills it and passes it to the called function. Parameters with
  default values must be explicitly initialized in the constructor.
  Exception for VT - when the table is the result of calculations (the constructor is
  optional).
- [minor] **Do not change the parameter structure composition in calling code** - do not initialize
  the parameter structure manually, do not add properties, do not change the composition/types of VT columns;
  all allowed parameters are defined only in the constructor function.
- [minor] **Describe structure properties and VT columns** - in the program interface of libraries,
  all functions returning structures/VTs (including constructors) must have
  a description of the return type listing properties/columns, starting on
  a new line with the `*` prefix (nesting - more asterisks).

## Procedure and function names

- [minor] **"Speaking" names** - the method name is derived from domain terms and
  is clear without a description (not `ВыполнитьПроверку(Параметр1, Рекв, ТЗ)`).
- [minor] **No types in the name** - do not describe parameter/return
  types in the name (`ИменаРолейСПравомДобавления`, not `ПолучитьМассивРолей…`).
- [minor] **Procedures - from a verb** - the procedure name is an infinitive verb describing
  the action (`ЗагрузитьКонтрагента`, not `ЗагрузкаКонтрагента`).
- [minor] **Functions - from the result** - the function name describes the return value
  (`ПолноеИмяПользователя`); for object-creating ones - from the word "New"
  (`НовоеПолеФормы`); for condition checks - from the word "Is" or a participle
  (`ДокументПроведён`).
- [minor] **CamelCase** - as for variable names.

## Description of procedures and functions

- [minor] **Section format** - the comment before the declaration: "Description" (starts with
  a verb, not with "Procedure…"/the method name and does not repeat the name), "Parameters:"
  (each: name - type - text; the type is mandatory and only one that exists in the platform),
  "Return value:", "Example:".
- [minor] **References and collections in the description** - for Structure/VT parameters specify the reference
  `см. Модуль.ФункцияКонструктор`; for Arrays - `Массив из <тип>`.
- [important] **Only in headers** - BSL comments are allowed only in the module header
  and in the method description before the declaration. In the body of `Процедура`/`Функция`,
  between statements and inside query text we do not write comments. Do not delete existing
  comments.
- [minor] **No useless comments** - do not retell the code and do not write
  descriptions that add no information (e.g., "Event handler procedure …"
  for an obvious handler).

## Procedure and function parameters

- [minor] **Meaningful parameter names** - from domain terms.
- [minor] **Do not substitute parameters** - do not use module variables,
  form attributes etc. instead of parameters.
- [minor] **Logical order** - parameters follow "general to specific" (the main
  object first).
- [minor] **Grouping with many parameters** - with many parameters
  group same-type ones into a `Структура` parameter or split the function into
  several simple ones.
- [minor] **No spaces in calls** - do not put spaces before `(`, after `(`, before `)`
  and before commas (when parameters are on one line and not omitted).

## Code duplication

- [minor] **Avoid duplication** - do not copy fragments/procedures with logically identical
  functionality; move reusable algorithms from object and form modules
  into common modules. Duplication is justified only if the code branches will diverge
  significantly in the future.

## Getting object metadata

- [important] **Metadata via the object, not globally** - when the type is known, get
  metadata via `Объект.Метаданные()` / `Ссылка.Метаданные()`, and not via
  `Метаданные.Справочники[Имя]` or `Метаданные.НайтиПоПолномуИмени(...)` (the second
  way is significantly slower). When the type is unknown in advance - `Метаданные.НайтиПоТипу(ТипЗнч(Ссылка))`.
  (Contextually: `НайтиПоПолномуИмени`/`НайтиПоТипу` are appropriate when the type is unknown -
  that is why this is checked by eye.)

## Variables in program modules

- [minor] **Prefer built-in facilities** - instead of module variables use more
  suitable platform facilities (the scope of module variables is hard to
  control).
- [minor] **Passing between handlers** - to pass parameters to object event handlers
  from external code use `ДополнительныеСвойства`, not export module variables; for internal
  passing between handlers - non-export module variables of the object.
- [minor] **Return codes as strings** - for error/return codes use string
  constants, not numeric module variables.
- [important] **Caching - via repeated use** - cache long-computed frequently
  used values with reusable modules, not with module
  variables; do not cache static data (predefined values -
  `ПредопределённоеЗначение`).

## Compilation directives and preprocessor instructions

- [critical] **`#Если Сервер/Клиент` directives in client-server common modules** - do not
  use preprocessor instructions to check client/server
  context in common modules with the `КлиентСервер` postfix (the context is not reliably
  determined); move methods with different behavior into `Клиент` and
  `Сервер` modules. (Branching by client mode - `#Если ВебКлиент` - is allowed.)
- [minor] **Do not break constructs** - do not split
  individual expressions, grammatical constructs, declarations and method calls with preprocessor instructions/regions.

## Movement activity

- [critical] **Account for activity in queries** - if the configuration uses switching of
  register movement activity (manual adjustment), all queries/reports against
  REAL tables of such a register must have the condition `ГДЕ Активность = ИСТИНА`
  (virtual tables account for activity automatically). Pay special attention to
  universal reports and business logic working with arbitrary registers.
- [critical] **Unposting - disable activity, do not delete** - for documents with
  manual movement adjustment, when unposting disable the activity of
  movements instead of deleting records.

## Using the event log

- [minor] **Event type "Group.Event"** - group the string event type identifier
  by functional attribute ("Document posting. Failed to cancel posting");
  do not include specific IB/external system data in the type
  (put them in the `Метаданные` and `Данные` parameters of the `ЗаписьЖурналаРегистрации` method).
- [minor] **Importance level** - critical errors → "Error", potential problems →
  "Warning", successful completion → "Information".
- [minor] **Comment - one event per record** - do not put information about several events into one
  comment; do not write data of unknown/large size
  (guideline - up to 10 KB). For exceptions - `ОбработкаОшибок.ПодробноеПредставлениеОшибки(ИнформацияОбОшибке())`.
- [important] **Do not read from the log in high-speed tasks** - with large volumes, reading from
  the event log is slow; for logging, create a separate register or use
  specialized platform objects.

## Spreadsheet document - reference value presentations

- [important] **No refs in cell parameters** - when building a spreadsheet document,
  do not specify reference values in cell parameters (fill type "Parameter") -
  this causes repeated DB calls for presentations; pass the
  presentations themselves. Exception - when getting presentations in advance itself requires
  similar repeated calls (including because of implicit joins with
  `Представление()` in a query and the MS SQL limit of 256 tables).
- [important] **Reference presentations - in the report query** - when outputting reference fields to
  a report, get the presentation field (and the needed attributes) right in the query, and do not
  dereference the ref "via dot" at output time (slows output); put the
  ref itself into the cell decryption.

## General requirements for building built-in language constructs

- [minor] **Intermediate variables for comparison** - do not embed a call expression
  directly into a comparison condition (`Если Вопрос(...) = КодВозвратаДиалога.Да Тогда`);
  assign the result to an intermediate variable and compare it.

## Working with the "Cancel" parameter in event handlers

- [important] **Do not report cancellation silently** - in the `ПриЗаписи`, `ПередЗаписью`,
  `ПередУдалением`, `ОбработкаПроведения`, `ОбработкаПроверкиЗаполнения` events do not
  set `Отказ = Истина` without informing the user of the reason
  (with a message `ОбщегоНазначения.СообщитьПользователю(..., Отказ)` or an exception) -
  otherwise "Failed to write…" hides the true cause.

## Module structure

- [minor] **Module header content** - at the start of the module, a comment with a brief
  description of purpose and application conditions (for form modules - a description
  of form parameters).
- [minor] **Splitting sections into subsections** - split large sections into regions by
  functional attribute; region names follow variable naming rules.
- [minor] **Correct method placement** - put only methods called from outside the object
  into "Program interface"; methods called only from the object itself and
  its forms - into "Service procedures and functions".

## Module texts

- [minor] **Russian language, tabs** - module texts in Russian (exceptions - web services
  and external system identifiers); syntax indent - with tabs (4), not
  spaces.

## Placing functionality across modules

- [minor] **Object / manager / common module** - put instance logic into the object module
  (work with `ЭтотОбъект`, event handlers, filling); "static" logic independent of the
  instance into the manager module (work by ref,
  printing a list, IB update); logic common to several objects - into common
  modules. Avoid `ПолучитьОбъект` just to call an object module method
  (loads the whole object).

## Programmatic creation of application objects

- [critical] **Call Fill on creation** - when creating an object programmatically
  (`СоздатьЭлемент`/`СоздатьДокумент`…) explicitly call `Заполнить(Неопределено)`
  (if there is no data - pass `Неопределено`): "Fill value", the
  `ОбработкаЗаполнения` handler and subscriptions will work correctly. Exception - full
  load from exchange/XML.

## Document posting and movements

- [important] **Movement writing - implicitly by the system** - in `ОбработкаПроведения` do not write
  record sets explicitly (`.Записать()`), except when the written data is needed by
  subsequent posting steps; otherwise there is a risk of mutual locks.
- [important] **Posting - the main way to reflect in accounting** - most documents
  must be posted (`Проведение = Разрешить`); do not replace posting
  with disabled posting. Even a document without movements must be posted (difference
  from a "draft").
- [critical] **Unposted/marked for deletion - no active movements.**
- [critical] **Posting result immutability** - re-posting without changes to data
  affecting movements must not change movements; movement formation must
  not depend on the state of accounting registers (balances), except justified
  cases (batch accounting). External data affecting movements must be stored in the
  document or protected from change (attribute edit prohibition).
- [important] **Posting service data - via `ДополнительныеСвойства`** - values
  computed in `ПередЗаписью` and needed only in `ОбработкаПроведения`/`ПриЗаписи`
  within the write (date shift flag, need to clear movements etc.)
  pass via the `ДокументОбъект.ДополнительныеСвойства` structure (`Вставить` in
  `ПередЗаписью`, `Получить`/`Свойство` in `ОбработкаПроведения`). Do not create document
  attributes for such flags (extra entity in metadata/form/reports) or
  module variables (conflict with attributes and survive the write). Checked by eye.

## Boundary and point in time

> Domain rule (why they are needed, use in documents and reports, typical errors):
> [Boundary and point in time](reference/boundary-and-moment.md). Below - manual check.

- [important] **Boundary correctness when controlling own movements** - when controlling balances of your
  document after writing movements, make sure balances are read at
  `Новый Граница(МоментВремени(), ВидГраницы.Включая)` (own movements included); when reading
  before own movements - `Исключая`/`МоментВремени()`. The choice of boundary is determined by semantics and
  is not scripted.
- [critical] **Moment instead of date in virtual tables** - make sure `МоментВремени`/`Граница` is passed
  in the VT parameters, not `Дата` (where ordering within a second matters).
- [critical] **Period boundary mirroring** - for reports check the correctness of the inclusive/exclusive
  boundary at the start and end of the period (the boundary document is neither doubled nor lost).

## Movement deletion

> Domain rule (3 modes, differences in implementation and locks, the "Write" flag):
> [Movement deletion](reference/movements-deletion.md). Below - manual check.

- [critical] **Mode matches the scenario** - make sure the document movement deletion mode
  (property "Movement deletion", metadata in `code_index`) matches the scenario: for
  normal posting "Delete automatically on unpost" is preferred;
  "Do not delete automatically" - only when movements are formed not only by posting.
  The mode choice is task semantics, not scripted.
- [critical] **Overwriting old movements on re-posting** - with "on unpost"/
  "do not delete" modes, check that `Движения.<Регистр>.Записывать = Истина` is set and the
  set is written, otherwise old movements remain.

## Register self-sufficiency

- [critical] **Register independent of the recorder** - register logic and reports must not
  access recorder fields "via dot" (implicit join; in a distributed infobase
  the recorder may be absent). The register must have enough own data -
  move the needed attributes into dimensions/resources/register attributes.

## Exchange plans with filters

- [critical] **Registration logic in `ПередЗаписью`/`ПередУдалением`** - determine
  recipient nodes in these events; data involved in exchange must be
  self-sufficient (contain everything needed for the registration logic, not
  access related table fields "via dot").
- [critical] **Registration logic robustness** - take into account that data is loaded in
  arbitrary order (the needed data may not be loaded yet), the
  `ОбменДанными.Загрузка` flag is ignored during registration, and registration errors
  interrupt the exchange message load.

## DCS reports

> Full checklist (field composition, names, report form, `GROUP BY` over VT, checks) -
> [DCS specifics](reference/skd-specifics.md). Read the reference in full before
> designing, developing and reviewing a report.

## Report parameters in DCS

- [minor] **Avoid extra parameters** - do not use DCS query parameters where
  ordinary filter item management is enough (`ГДЕ Организация =
  &Организация` → give the user the "Organization" filter).
- [important] **Optional conditions via `{ГДЕ ...}`** - instead of mandatory parameters
  use the DCS query language extension `{ГДЕ ...}` so that when the user disables
  the parameter the condition fragment is disabled too (without the "Report parameter not set"
  error).

## Transactions

- [important] **Minimum actions and duration** - perform in a transaction only actions indivisible by
  business logic; move heavy calculations, fill checks, queries that do not require
  locks outside the transaction; split long mass operations into
  portions (guideline - portion write ≤ 20 sec). Do not combine logically independent actions
  into one transaction.
- [important] **Do not call external resources in a transaction** - network folders, HTTP/FTP/web,
  mail services etc. (slow, may be unavailable, timeouts).
- [minor] **Do not open a transaction for a single write** - do not call `НачатьТранзакцию`
  explicitly when there are no other DB actions besides writing an object/set (the platform will open
  the transaction itself) and responsible reading is not required.
- [critical] **Nested transactions** - when using a nested transaction, add `ВызватьИсключение` at the end of the
  `Исключение` block (otherwise the outer transaction will not be
  rolled back - "An error occurred in this transaction"). Inside an active transaction,
  after an error do not access the DB (including implicitly - for a ref presentation).
- [critical] **Disabling totals - in a transaction** - perform `УстановитьИспользованиеИтогов(Ложь)` with
  writing and re-enabling in a transaction (otherwise other sessions get an
  error when getting the latest slice).

## Locks and responsible data reading

> Domain rule (lock types, managed/automatic,
> exclusive/shared, `ИсточникДанных`/`ИспользоватьИзИсточникаДанных`, the
> `Диапазон` object, examples): [Locks](reference/locks.md). Balance control methodology and
> lock order: [Balance control methodology](reference/balance-control-methodology.md).
> Below - manual check items that cannot be scripted.

- [important] **Object lock before modification** - before modifying an existing
  object from code call `Заблокировать()` / `ЗаблокироватьДанныеДляРедактирования`
  (pessimistic lock for concurrent work). Do not check the lock
  during exchange load and in guaranteed exclusive operations (IB update).
- [important] **Responsible reading - in a transaction with a managed lock** - reading whose
  results are used to modify data or make decisions (reading during
  posting for movements, consistent transfer to another system, group
  processing/IB update) must be performed in a transaction, after setting a
  managed lock (`БлокировкаДанных`). Responsible reading is not required
  for dynamic lists, search, most reports, conditionally constant data
  and exclusive operations.
- [critical] **Exclusive/shared lock** - when reading followed by modification,
  set an exclusive lock before reading (otherwise deadlock); when reading
  without modification (e.g., to form movements) - shared on the read
  data, exclusive on the modified data.
- [important] **Managed lock mode** - use the lock control mode
  "Managed"; lock only records actually processed; do not use the
  `ДЛЯ ИЗМЕНЕНИЯ` construct in queries (meaningless in managed mode).
- [important] **Redundant locks - design** - minimize redundant locks
  at the metadata structure design stage; pay special attention to
  sequences, accounting and accumulation registers.

## Writing registers and reading attributes

- [important] **Write a register with one set** - do not rewrite a large set in which
  ≤30% of records change (write only the changes); use substitution modes
  (Merge/Delete/Update) and change computation by query.
- [important] **Reading individual attributes - by query or BSP** - to read individual
  attributes do not use `Ссылка.ПолучитьОбъект()` and dot dereferencing
  `Ссылка.Реквизит` (they load the whole object with tabular sections);
  use a query or `ОбщегоНазначения.ЗначениеРеквизитаОбъекта` /
  `ЗначенияРеквизитовОбъекта`.
- [important] **Blocking balance reading - closer to the transaction end** - perform balance control
  (totals reading) as close to the transaction end as possible: first write
  movements of registers that do not require control (in a stable order, with
  `БлокироватьДляИзменения = Ложь`), at the end - registers requiring control
  (`БлокироватьДляИзменения = Истина`) and the negative balance control query.
  Do not control balances where it is not needed (receipt document,
  re-posting without increasing write-off).

## Accumulation registers and virtual tables

> Full checklist (storage, "Turnovers"/"Balances"/"Balances and turnovers", aggregates, typical
> query errors) - [Accumulation registers](reference/accumulation-registers.md).
> Read the reference in full before writing a query/report for an accumulation register.

## Totals in queries (ИТОГИ)

- [critical] **Non-aggregated fields in TOTALS** - a field that is not included in the
  `ИТОГИ` grouping and not wrapped in an aggregate equals `NULL` on total rows. This is caught by
  `query-analyze` (`totals-field-not-aggregated`, error), but also check by eye:
  every "bare" field of the select list must be either in `ПО` or in an aggregate.

## Information registers

> Full checklist (architecture, "SliceLast"/"SliceFirst", write modes) -
> [Information registers](reference/information-registers.md). Read the reference in full
> before querying or writing an information register.

## Register totals split mode

- [important] **Totals split does not help with balance control** - if balance
  control is used, splitting totals has no effect; move balance control
  as close to the transaction end as possible.
