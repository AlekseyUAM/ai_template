# 1C database table indexes (local reference)

Local copy of the index reference that the 1C:Enterprise 8 platform
(format version 8.3.27) creates for database tables automatically when
configuration objects are created and under certain object settings. Used
by the `query-review` skill when checking "is the query condition covered by a suitable
index" - without access to external resources.

Legend (as in the "Query tables" documentation section):

- `Измерение1`, `Реквизит1`, etc. - conventional names of dimensions/attributes.
- `ОРНР` - common separator attribute in "independent" mode (`ОРНР1`, `ОРНР2`…).
- `ОРСР` - separator in "independent and shared" mode.
- `ОРР` - separator when the mode does not matter.
- `ОРРХ` - field with the hash value of the separator value set.
- `[...]` - optional index field; `[... +...]` - a set of same-type fields.

---

Database table indexes
This section lists database table indexes that the 1C:Enterprise 8 system creates. Table indexes are created implicitly when configuration objects are created, as well as under certain configuration object settings. For cases where index creation depends on configuration object settings, the index creation conditions are given.
In the tables below, index field names are given as described in the "Query tables" documentation section.
For dimensions, attributes, etc., conventional names Измерение1, Реквизит1, etc. are used.
For common attributes that are separators in "independent" mode, we use the names ОРНР (ОРНР1, ОРНР2, etc.).
For common attributes that are separators in "independent and shared" mode, we use the names ОРСР.
If the separation mode does not matter, then for common attributes that are separators we use the names ОРР.
If separators are defined in the configuration, an index may include a field that contains the hash value of the separator value set. Such a field is denoted by the name ОРРХ.
Index fields that are not mandatory are given in square brackets, and if the index contains a set of same-type fields, this is described by an ellipsis, e.g.: Реквизит + Измерение1 + [Измерение2 +...].
This material should be used when writing query texts to optimize their execution time.


## Catalog (Справочник)

Main indexes
Index

Condition

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that
separate this catalog.

[ОРРХ | ОРНР1 +] Код + Ссылка

Property "Длина кода" is not 0.
If the catalog is separated by one independent
separator whose type is not Строка, the index contains
the field of that separator.
If the separator type is Строка, or the separator
is independent and shared, or there is more than one
separator, the index contains the field of the hash value
of separator values.
This rule applies to all indexes that
specify [ОРРХ | ОРНР1 +].

[ОРРХ | ОРНР1 +] Наименование
+ Ссылка

Property "Длина наименования" is not 0.

[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
[ОРРХ | ОРНР1 +] Реквизит + Код
упорядочиванием" and at the same time the property "Длина кода" is not
+ Ссылка
0, and the property "Основное представление" is "В виде
кода".

[ОРРХ | ОРНР1 +] Реквизит +
Наименование + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина
наименования" is not 0, and the property "основное
представление" is "В виде наименования".

[ОРРХ | ОРНР1 +] Реквизит

The catalog is included in the filter criterion via the attribute
"Реквизит".

[ОРРХ | ОРНР1 +] PredefinedID

Index by the ID of a predefined metadata
object.

Additional indexes for a subordinate catalog (regardless of
whether the catalog is hierarchical)
Index

Condition

[ОРРХ | ОРНР1 +] Владелец +
Ссылка

Property "Длина кода" is 0.

[ОРРХ | ОРНР1 +] Владелец +
Код + Ссылка

Property "Длина кода" is not 0.

[ОРРХ | ОРНР1 +] Владелец +
Наименование + Ссылка

Property "Длина наименования" is not 0.

[ОРРХ | ОРНР1 +] Владелец +
Реквизит + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Владелец +
Реквизит + Код + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина кода" is not
0, and the property "Основное представление" is "В виде
кода".

[ОРРХ | ОРНР1 +] Владелец +
Реквизит + Наименование +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина
наименования" is not 0, and the property "основное
представление" is "В виде наименования".

Additional indexes for a hierarchical non-subordinate catalog
If the catalog has the property "Размещать группы сверху" set, the field ЭтоГруппа participates in the indexes along with
the field Родитель. The index composition corresponds to the table below.
Index

Condition

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Ссылка

Property "Длина кода" is 0 and the property "Длина
наименования" is 0.

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Код + Ссылка

Property "Длина кода" is not 0.

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Наименование +
Ссылка

Property "Длина наименования" is not 0.

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Реквизит + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Реквизит + Код +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина кода" is not
0, and the property "Основное представление" is "В виде
кода".

[ОРРХ | ОРНР1 +] Родитель +
ЭтоГруппа + Реквизит +
Наименование + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина
наименования" is not 0, and the property "основное
представление" is "В виде наименования".

For catalogs without groups on top, the index composition corresponds to the table above,
but the field ЭтоГруппа is not included in the indexes.

Additional indexes for a hierarchical subordinate catalog
If the catalog has the property "Размещать группы сверху" set, the field ЭтоГруппа participates in the indexes along with
the field Родитель. The index composition corresponds to the table below.
Index

Condition

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа + Ссылка

Property "Длина кода" is 0 and the property "Длина
наименования" is 0.

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа + Код +
Ссылка

Property "Длина кода" is not 0.

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа +
Наименование + Ссылка

Property "Длина наименования" is not 0.

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа + Реквизит
+ Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа + Реквизит
+ Код + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина кода" is not
0, and the property "Основное представление" is "В виде
кода".

[ОРРХ | ОРНР1 +] Владелец +
Родитель + ЭтоГруппа + Реквизит
+ Наименование + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина
наименования" is not 0, and the property "основное
представление" is "В виде наименования".

For catalogs without groups on top, the index composition corresponds to the table above,
but the field ЭтоГруппа is not included in the indexes.

Catalog options table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
(Clustered)


## Document (Документ)

Index

Condition

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that
separate this document.

[ОРРХ | ОРНР1 +] Дата + Ссылка

Always.

[ОРРХ | ОРНР1 +] Номер +
Ссылка

Property "Длина номера" is not 0.

[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Реквизит +
Дата + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием".

[ОРРХ | ОРНР1 +] Реквизит

The document is included in the filter criterion via the attribute
"Реквизит".

[ОРРХ | ОРНР1 +]
ПрефиксНомера + Номер + Ссылка

Property "Длина номера" is not 0.

Document journal
Index

Condition

[ОРРХ | ОРНР1 +] Ссылка
(Clustered)

Always.

[ОРРХ | ОРНР1 +] Дата + Ссылка

Always.

[ОРРХ | ОРНР1 +] Графа +
Ссылка

For the journal column "Графа" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Графа + Дата
+ Ссылка

For the journal column "Графа" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием".

Chart of characteristic types
See the description of catalog indexes, with the only correction that the code length and
name length of a chart of characteristic types cannot be zero and, in addition, a chart of
characteristic types cannot be subordinate.

Chart of characteristic types options table
Index

Condition

Идентификатор Always.

Chart of accounts
Index

Condition

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that
separate this chart of accounts.

[ОРРХ | ОРНР1 +] Код + Ссылка

Always.

[ОРРХ | ОРНР1 +] Родитель + Код
Always.
+ Ссылка
[ОРРХ | ОРНР1 +] Наименование
+ Ссылка

Always.

[ОРРХ | ОРНР1 +] Родитель +
Наименование + Ссылка

Always.

[ОРРХ | ОРНР1 +] Порядок +
Ссылка

Property "Длина порядка" is not 0.

[ОРРХ | ОРНР1 +] Родитель +
Порядок + Ссылка

Property "Длина порядка" is not 0.

[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Родитель +
Реквизит + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Реквизит +
Порядок + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина порядка" is not
0.

[ОРРХ | ОРНР1 +] Родитель +
Реквизит + Порядок + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина порядка" is not
0.

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
[ОРРХ | ОРНР1 +] Реквизит + Код
упорядочиванием" and at the same time the property "Длина порядка"
+ Ссылка
is 0, and the property "Основное представление" - "В виде
кода".

[ОРРХ | ОРНР1 +] Родитель +
Реквизит + Код + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина порядка"
is 0, and the property "Основное представление" - "В виде
кода".

[ОРРХ | ОРНР1 +] Реквизит +
Наименование + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина порядка"
is 0, and the property "Основное представление" - "В виде
наименования".

[ОРРХ | ОРНР1 +] Родитель +
Реквизит + Наименование +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием" and at the same time the property "Длина порядка"
is 0, and the property "Основное представление" - "В виде
наименования".

[ОРРХ | ОРНР1 +] Реквизит

The chart of accounts is included in the filter criterion via the attribute
"Реквизит".

[ОРРХ | ОРНР1 +] PredefinedID

Index by the ID of a predefined metadata
object.

Chart of accounts options table

Index

Condition

Идентификатор Always.

Chart of calculation types
See the description of catalog main indexes.

Chart of calculation types options table
Index

Condition

Идентификатор Always.

Exchange plan
See the description of catalog main indexes, with the only correction that the code length and
name length of an exchange plan cannot be zero.

Tabular section
Index

Condition

[ОРНР1 + ... +] Ссылка + Ключ
(Clustered)

Always.
The index includes fields of independent separators
that separate the object to which the tabular section
belongs.

[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

The configuration object is included in the filter criterion via the
tabular section attribute "Реквизит", or the tabular section attribute
has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] PredefinedID

Index by the ID of a predefined metadata
object.

For all tables that provide access to object tabular sections.

Information register
Non-periodic information register
Index

Condition and description

[ОРРХ | ОРНР1 +] Измерение1 +
[Измерение2 +...] (Clustered)

The register has at least one dimension.
An index including all dimensions in the order
in which they are defined at configuration time.
The index is clustered if the register is independent.

[ОРРХ | ОРНР1 +] ИзмерениеN +
Измерение1 + [Измерение2 +...]

The dimension "ИзмерениеN" has the property "Индексировать" set
or the property "Ведущее", and it is not the first and not the
only dimension.
An index including all dimensions. The first field is ИзмерениеN, then all other dimensions in the order
in which they are defined at configuration time.

[ОРРХ | ОРНР1 +] Реквизит +
Измерение1 + [Измерение2 +...]

The attribute "Реквизит" has the property "Индексировать" set.
An index in which the first field is Реквизит, then all
dimensions in the order in which they are defined at
configuration time.

[ОРРХ | ОРНР1 +] Ресурс +
Измерение1 + [Измерение2 +...]

The resource "Ресурс" has the property "Индексировать" set.
An index in which the first field is Ресурс, then all dimensions
in the order in which they are defined at configuration time.

Periodic information register
Index

Condition and description

[ОРРХ | ОРНР1 +] Период +
[Измерение1 + ...]

Always.

[ОРРХ | ОРНР1 +] Измерение1 +
[Измерение2 +...] + Период
(Clustered)

The register has at least one dimension.
An index including all dimensions in the order
in which they are defined at configuration time, and the field Период.

[ОРРХ | ОРНР1 +] ИзмерениеN +
Период + Измерение1 +
[Измерение2 +...]

The dimension "ИзмерениеN" has the property "Индексировать" set
or the property "Ведущее", and it is not the only
dimension.
An index including the field Период and all dimensions. The first
field is ИзмерениеN, then the field Период, then all other
dimensions in the order in which they are defined at
configuration time.

[ОРРХ | ОРНР1 +] Реквизит +
Период + [Измерение1 + ...]

The attribute "Реквизит" has the property "Индексировать" set.
An index in which the first field is Реквизит, then the field
Период, then all dimensions in the order in which they are
defined at configuration time.

[ОРРХ | ОРНР1 +] Ресурс +
Период + [Измерение1 + ...]

The resource "Ресурс" has the property "Индексировать" set.
An index in which the first field is Ресурс, then the field Период,
then all dimensions in the order in which they are defined
at configuration time.

Additional index for an information register subordinate to a registrar
Index
[ОРНР1 + ... +] Регистратор +
НомерСтроки (Clustered)

Condition and description
Always.
The index includes fields of independent separators that
separate this register.
The index is clustered if the register is non-periodic.

Information register with periodicity "By registrar position"
Index

Condition and description

[ОРРХ | ОРНР1 +] Период +
Регистратор + НомерСтроки

Always.

[ОРНР1 + ... +] Регистратор +
НомерСтроки

Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +] Измерение1 +
[Измерение2 + ...] + Период +
Регистратор + НомерСтроки
(Clustered)

The register has at least one dimension.
An index including all dimensions in the order in which
they are defined at configuration time, the field Период and
the field Регистратор.

[ОРРХ | ОРНР1 +] Измерение +
Период + Регистратор +
НомерСтроки

The dimension "Измерение" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Реквизит +
Период + Регистратор +
НомерСтроки

The attribute "Реквизит" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Ресурс +
Период + Регистратор +
НомерСтроки

The resource "Ресурс" has the property "Индексировать" set.

ИтогиСрезПервых
Index

Condition and description

[ОРРХ | ОРНР1 +] Измерение1 +
[Измерение2 + ...] + Период
(Clustered)

The register has at least one dimension.
An index including all dimensions in the order
in which they are defined at configuration time.

[ОРРХ | ОРНР1 +] Реквизит +
[Измерение1 + ...]

The attribute "Реквизит" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Ресурс +
[Измерение1 + ...]

The resource "Ресурс" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] ИзмерениеN +
Измерение1 + [Измерение2 +...]

The dimension "ИзмерениеN" has the property "Индексировать" set
or the property "Ведущее", and it is not the only
dimension.
An index including all dimensions. The first field is ИзмерениеN, then all other dimensions in the order
in which they are defined at configuration time.

ИтогиСрезПоследних
Index

Condition and description

[ОРРХ | ОРНР1 +] Измерение1 +
[Измерение2 + ...] + Период
(Clustered)

The register has at least one dimension.
An index including all dimensions in the order
in which they are defined at configuration time

[ОРРХ | ОРНР1 +] Реквизит +
[Измерение1 + ...]

The attribute "Реквизит" has the property "Индексировать" set

[ОРРХ | ОРНР1 +] Ресурс +
[Измерение1 + ...]

The resource "Ресурс" has the property "Индексировать" set

[ОРРХ | ОРНР1 +] ИзмерениеN +
Измерение1 + [Измерение2 +...]

The dimension "ИзмерениеN" has the property "Индексировать" set
or the property "Ведущее", and it is not the only
dimension.
An index including all dimensions. The first field is ИзмерениеN, then all other dimensions in the order
in which they are defined at configuration time.

Accumulation register
Main register table

Index

Condition

[ОРРХ | ОРНР1 +] Период +
Регистратор + НомерСтроки
(Clustered)

Always.

[ОРНР1 + ... +] Регистратор +
НомерСтроки

Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +] Измерение +
Период + Регистратор +
НомерСтроки

The dimension "Измерение" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Реквизит +
Период + Регистратор +
НомерСтроки

The attribute "Реквизит" has the property "Индексировать" set.

Balances table
Index

Condition

[ОРРХ | ОРНР1 +] Период +
Измерение1 + ... + ИзмерениеN +
[DimHash] + [Splitter]
(Clustered)

For registers of kind "Остатки".

[ОРРХ | ОРНР1 +] Период +
Измерение

The dimension "Измерение" has the property
"Индексировать" set (starting from the second dimension).

Turnovers table
Index

Condition

[ОРРХ | ОРНР1 +] Период +
Измерение1 + ... + ИзмерениеN +
[DimHash] + [Splitter]
(Clustered)

For registers of kind "Обороты".

[ОРРХ | ОРНР1 +] Измерение +
Период

The dimension "Измерение" has the property "Индексировать" set.
(starting from the second dimension).

Период + DimHash

For registers where the number of dimensions does not allow
organizing a unique index over dimensions

Accumulation register options table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
(Clustered)

Accumulation register aggregates
Aggregates table
Index
[ОРРХ | ОРНР1 +] Период +
Измерение1 + ... + ИзмерениеN
(Clustered)

Condition
Always.

Accumulation register statistics table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
+ Период + Splitter (Clustered)
Map of used dimensions

Always

Aggregate network options table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
(Clustered)

Buffer table of new accumulation register turnovers
Index
[ОРРХ | ОРНР1 +] Период +
Измерение1 + ... + ИзмерениеN
(Clustered)

Condition
Always.

New turnovers table of the accumulation register
Index
[ОРРХ | ОРНР1 +] Период +
Измерение1 + ... + ИзмерениеN
(Clustered) + Splitter

Condition
Always.

Dimension codes table of the accumulation register
Index
[ОРРХ | ОРНР1 +] Период + UUID
измерения 1 + ... + UUID
измеренияN (Clustered)

Condition
Always.

Aggregate network table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
+ UUID измерения 1 + ... + UUID
Always.
измеренияN (Clustered)

Accounting register
Main register table without correspondence
Index
[ОРРХ | ОРНР1 +] Период +
Регистратор + НомерСтроки
(Clustered)

Condition and description
Always.

[ОРНР1 + ... +] Регистратор +
НомерСтроки

Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +] Счет + Период
+ Регистратор

A chart of accounts is assigned to the register.

[ОРРХ | ОРНР1 +] Измерение +
Период + Регистратор +
НомерСтроки

The dimension "Измерение" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Реквизит +
Период + Регистратор +
НомерСтроки

The attribute "Реквизит" has the property "Индексировать" set.

Main register table with correspondence
It differs from the index composition above only in that instead of the account index
two indexes are created: by debit account and by credit account.
Index

Condition

[ОРРХ | ОРНР1 +] СчетДт +
Период + Регистратор

A chart of accounts is assigned to the register.

[ОРРХ | ОРНР1 +] СчетКт +
Период + Регистратор

A chart of accounts is assigned to the register.

Account totals table
Index
[ОРРХ | ОРНР1 +] Период
[+ Счет]
+ ИзмерениеБезПризнакаУчета1 +
...
+ ДополнительноеИзмерение1 + ...
+ ИзмерениеСПризнакомУчета1 +
...
[+ ХэшИзмерений]
[+ РазделительИтогов]

Condition
The field "Счет" is added if a chart of accounts is defined
for the register.

The field "ХэшИзмерений" is added when the number of other fields
is greater than 15.
The field "РазделительИтогов" is added if totals splitting is enabled.

Inter-account totals table
Only for registers supporting correspondence
Index
[ОРРХ | ОРНР1 +]
ИзмерениеДт1 + ИзмерениеКт1 +
...
Измерение1 + ...
[+ ХэшИзмерений]
[+ РазделительИтогов]

Condition
For non-balance dimensions.
For balance dimensions.
The field "ХэшИзмерений" is added when the number of other fields
is greater than 15.
The field "РазделительИтогов" is added if totals splitting is enabled.

Table with subconto values

Index

Condition

[ОРРХ | ОРНР1 +] Регистратор +
НомерСтроки + Корреспонденция

Always.

[ОРРХ | ОРНР1 +] Период +
Регистратор + НомерСтроки +
ВидСубконто + Корреспонденция
(Clustered)

Always.

[ОРРХ | ОРНР1 +] ВидСубконто +
Значение

Always.

Accounting register options table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
(Clustered)

Calculation register
Main calculation register table
Index

Condition and description

[ОРРХ | ОРНР1 +]
ПериодРегистрации + Регистратор
+ НомерСтроки

Always.

[ОРНР1 + ... +] Регистратор +
НомерСтроки

Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +]
ПериодРегистрации +
[БазовоеИзмерение1 +...]

Always.
Index by the field ПериодРегистрации and all base
dimensions, i.e. dimensions with the property "Базовое" set.
Base dimensions follow in the order
in which they are defined at configuration time.

[ОРРХ | ОРНР1 +]
[БазовоеИзмерение1 +...] +
ПериодРегистрации

There is at least one base dimension.
Index by all base dimensions, i.e. dimensions with the property
"Базовое" set, and the field
ПериодРегистрации.

[ОРРХ | ОРНР1 +]
ПериодДействия +
[БазовоеИзмерение1 +...]

The calculation register property "ПериодДействия" is set.
Index by the field ПериодДействия and all base
dimensions, i.e. dimensions with the property "Базовое" set.
Base dimensions follow in the order
in which they are defined at configuration time.

[ОРРХ | ОРНР1 +]
[БазовоеИзмерение1 +...] +
ПериодДействия

The calculation register property "ПериодДействия" is set and
there is at least one base dimension.
Index by all base dimensions, i.e. dimensions with the property
"Базовое" set, and the field
ПериодРегистрации.

[ОРРХ | ОРНР1 +] Измерение +
ПериодРегистрации + Регистратор
+ НомерСтроки

The dimension "Измерение" has the property "Индексировать" set.

[ОРРХ | ОРНР1 +] Реквизит +
ПериодРегистрации + Регистратор
+ НомерСтроки

The attribute "Реквизит" has the property "Индексировать" set.

Recalculation table
Index
[ОРРХ | ОРНР1 +]
Регистратор +
ВидРасчета +
[Измерение1 + ...]

Condition and description
Always.
Index by the field Регистратор, the field ВидРасчета and all recalculation
dimension fields in the sequence in which they are
configured.

Table of actual action periods
Index
[ОРРХ | ОРНР1 +]
Регистратор +
НомерСтроки

Condition and description
Always.
The index includes fields of independent separators that separate
this register.

Calculation register options table
Index

Condition

[ОРРХ | ОРНР1 +] Идентификатор
Always.
(Clustered)

Sequences
Main sequence table
Index

Condition and description

[ОРРХ | ОРНР1 +]
Регистратор

Always.

[ОРРХ | ОРНР1 +]
[Измерение1 + ...] +
Период + Регистратор

Always.
Index by all dimension fields, the field Период and the field Регистратор.
Dimension fields follow in the order in which they are defined at
configuration time.

Sequence boundary table
Index
[ОРРХ | ОРНР1 +] [Измерение1 +
...] + Период + Регистратор

Condition and description
Always.
Index by all dimension fields, the field Период and the field
Регистратор. Dimension fields follow in the order in
which they are defined at configuration time.

Enums

Index

Condition and description

[ОРРХ | ОРНР1 +] Порядок +
Ссылка

Always.
The order field of enum tables corresponds to the order in
which enum values are located in the configuration
tree.

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that
separate this register.

Business processes
Main business process table
Index

Condition

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +] Дата + Ссылка

Always.

[ОРРХ | ОРНР1 +] Номер +
Ссылка

Property "Длина номера" is not 0.

[ОРРХ | ОРНР1 +] Завершен +
Дата + Ссылка

Always

[ОРРХ | ОРНР1 +] Стартован +
Дата + Ссылка

Always

[ОРРХ | ОРНР1 +] ВедущаяЗадача
Always
+ Ссылка
[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Реквизит +
Дата + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием".

[ОРРХ | ОРНР1 +] Реквизит

The business process is included in the filter criterion via the attribute
"Реквизит".

Table of business process route points
Index

Condition and description

[ОРНР1 + ... +] Ссылка
(Clustered)

Always.
The index includes fields of independent separators that separate
this register.

[ОРРХ | ОРНР1 +]
Порядок + Ссылка

Always.
The order field of point tables corresponds to the order in which route
points were entered into the business process flowchart.

Tasks
Index
[ОРНР1 + ... +] Ссылка
(Clustered)

Condition
Always.
The index includes fields of independent separators that
separate this register.

[ОРРХ | ОРНР1 +] Дата + Ссылка

Always.

[ОРРХ | ОРНР1 +] Номер +
Ссылка

Property "Длина номера" is not 0.

[ОРРХ | ОРНР1 +] Наименование
+ Ссылка

Always

[ОРРХ | ОРНР1 +] Выполнена +
Наименование + Ссылка

Always

[ОРРХ | ОРНР1 +] Выполнена +
Дата + Ссылка

Always

[ОРРХ | ОРНР1 +] БизнесПроцесс
+ ТочкаМаршрута + Ссылка

Always

[ОРРХ | ОРНР1 +] Выполнена +
БизнесПроцесс + ТочкаМаршрута + Always
Ссылка
[ОРРХ | ОРНР1 +] БизнесПроцесс
+ Дата + Ссылка

Always

[ОРРХ | ОРНР1 +] Реквизит +
Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать".

[ОРРХ | ОРНР1 +] Реквизит +
Дата + Ссылка

For the attribute "Реквизит" the property "Индексировать"
is set to "Индексировать с доп.
упорядочиванием".

[ОРРХ | ОРНР1 +] Реквизит

The task is included in the filter criterion via the attribute
"Реквизит".

Integration services
Integration service settings table
Index
[ОРРХ | ОРНР1 +] (Clustered)

Condition
Always.
The index includes fields of independent separators that
separate this chart of accounts.

Integration service channel send queue table
Index

Condition

Always.
[ОРРХ | ОРНР1 +] Идентификатор
The index includes fields of independent separators that
сообщения (Clustered)
separate this integration service.
Позиция сообщения

Always.

Integration service channel receive queue table
Index

Condition

Always.
[ОРРХ | ОРНР1 +] Идентификатор
The index includes fields of independent separators that
сообщения (Clustered)
separate this integration service.
Позиция сообщения

Always.

Change registration tables
Change registration tables for different metadata objects differ only in the composition
and types of data key fields - a set of fields that uniquely identify data. For object
data types (Справочник, Документ, ПланСчетов, etc.) it is "Ссылка"; for registers
subordinate to a registrar (РегистрНакопления, РегистрБухгалтерии, РегистрСведений
subordinate to a registrar, etc.) - "Регистратор"; for information registers not subordinate
to a registrar - the fields corresponding to changes included in the main register filter; for
constants - the ID of the metadata object Константы.
Index
[ОРРХ | ОРНР1 +] Узел + Номер
сообщения + Ключ данных

Condition and description
Always.

[ОРРХ | ОРНР1 +] Ключ данных +
Always.
Узел + Номер сообщения

User list table
Index

Condition and description

Unique user ID
(Clustered)

Always.

Role set ID

Always.

OS user name

Always.

[ОРРХ +] OS user name

At least one separator is defined in the configuration.

User name

Always.

[ОРРХ +] User name

At least one separator is defined in the configuration.

[ОРРХ +] Full user name

Always.
The index includes the hash value of the separator value set
if at least one separator is defined in the configuration.

Show user in the list
for the authentication dialog

Always.

Authentication by 1C:Enterprise means
is allowed

Always.

User activity history table
Index

Condition and description

[ОРРХ +] Unique
record ID

Always.
The index includes the hash value of the separator value set
if at least one separator is defined in the configuration.

[ОРРХ +] Unique
user ID +
Date time

Always.
The index includes the hash value of the separator value set
if at least one separator is defined in the configuration.

[ОРРХ +] Unique
user ID +
Hash by URL

Always.
The index includes the hash value of the separator value set
if at least one separator is defined in the configuration.

ОРРХ +
ИспользованиеРазделителя1 + ...

At least one separator is defined in the configuration.

System settings storage table
Report settings storage table
Report variant settings storage table
Common settings storage table
Form data settings storage table
Dynamic list settings storage table
Error handling settings storage table
Navigation link external data storage table
Internal settings storage table
OData standard interface settings storage table
Index

Condition and description

[ОРРХ +] Hash of unique
user ID +
Setting subject name + Hash of
multiple (named) setting name + Setting
version

Always.
The index includes the hash value of the separator value
set if at least one separator is defined in the configuration.

ОРРХ +
ИспользованиеРазделителя1 + ...

At least one separator is defined in the configuration.

Data history queue table
Index
Metadata object ID
+ Data ID + Message position in
queue (Clustered)

Condition and description

Always.

Data history data versions table
Index
Data ID + Data
version number (Clustered)

Condition and description
Always.

Data history latest versions tables

Index

Condition and description

[ОРР1 + … + ] + Metadata
object ID +
Data ID
(Clustered)

Always.
The index includes separator fields

Data history metadata versions table
Index

Condition and description

[ОРНР1 + … + ] + Metadata
object ID + Metadata version
formed flag on settings change + Metadata version
is current flag +
Current metadata version
number (Clustered)

Always.
The index includes fields of independent separators

Metadata object ID
+ Current metadata
version number

Always.

Data history settings table
Index

Condition and description

[ОРНР1 + … + ] + Metadata
object ID (Clustered)

Always.
The index includes fields of independent separators

Post-write processing queue table of a data history version
Index

Condition and description

[ОРР1 + … + ] + Metadata
object ID +
Data ID + Version
number (Clustered)

Always.
The index includes separator fields

Database copies
Copies table
Index

Condition

Copy ID + Copy name
(Clustered)

Always.

Copy settings table
Index
Copy ID
(Clustered)

Condition and description
Always.

Copy table states table

Index

Condition and description

Copy ID +
Table name
(Clustered)

Always.

Changes during initial copy table
Index
Copy ID +
Table name
(Clustered)

Condition and description
Always.

Change objects table
Index
Object ID
(Clustered)

Condition and description
Always.

Table with information on initial copy blocks
Index
Copy ID +
Table name + Block
number (Clustered)

Condition and description
Always.

Transaction journals table
Index

Condition and description

Transaction number
(Clustered)

Always.

Transaction ID

Always.

Table of tables changed in transactions
Index

Condition and description

Transaction number +
Table name
(Clustered)

Always.

Table name

Always.

Transferred transactions table
Index
Copy ID +
Transaction number
(Clustered)

Condition and description
Always.

Temp files table for exchange with the offline mobile client

Index
Record ID

Condition and description
Always.

Database tablespaces table
Index

Condition and description

Tablespace
name
(Clustered)

Always.

Tablespace ID

Always.

Database tablespace composition elements table
Index
Metadata object ID + Element
purpose flag +
Data placement
flag (Clustered)

Condition and description

Always.

Tablespace ID + Element
purpose flag
Always.

Additional indexes
For all objects of the metadata tree of the object type, document journals and registers, the
additional indexes functionality is available (provided a CORP license is present).
The source of additional index fields can be either a metadata object,
or a tabular section of a metadata object, or a virtual table of a metadata object.
Mixing fields from different sources in one index is not allowed, however there is
the possibility of adding several indexes using fields from different sources.
For example, you cannot create an index including fields of a metadata object and fields of a tabular section
of this object at the same time, but you can add two (or more) different indexes, one of which
will include object fields and the other - tabular section fields of the object.
Adding metadata object fields to an additional index creates an index on
the main table of the metadata object.
Adding tabular section fields of a metadata object to an additional index creates
an index on the table storing the tabular section data.
Adding virtual table fields of a metadata object to an additional index generally
creates several indexes covering the tables that participate in
forming the virtual table. For example, creating an additional index with
the use of fields of the "Остатки" virtual table of an accumulation register creates
two indexes - an index on the main table of the accumulation register and an index on the totals table
of the accumulation register.
Metadata object fields included in additional indexes can be
"Indexable" - such fields are included in the key columns of the index, or
"Additional" - such fields are added to the index as included columns, and if
the DBMS does not support included columns, such fields are ignored.
All fields of the selected source are available for indexing, except fields with the type
"Двоичные данные" and with the type "Строка" of unlimited length.
The 1C:Enterprise 8 platform does not impose restrictions on the number of additional

indexes, while each index can contain no more than 16 physical columns.
