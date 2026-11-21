---
name: skd-edit
description: Point editing of a 1C data composition schema (DCS). Use when you need to modify an existing DCS - add fields, totals, filters, parameters, change the query text
argument-hint: <TemplatePath> -Operation <op> -Value <value>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# /skd-edit - point editing of a DCS (Template.xml)

Atomic operations for modifying an existing data composition schema: adding, deleting and modifying fields, totals, filters, parameters, variant settings, structure management, query replacement.

## Parameters and command

| Parameter | Description |
|----------|----------|
| `TemplatePath` | Path to Template.xml (or to the folder - Ext/Template.xml autocompletion) |
| `Operation` | Operation (see the list below) |
| `Value` | Operation value (a shorthand string or query text) |
| `DataSet` | (optional) Data set name (default: the first) |
| `Variant` | (optional) Settings variant name (default: the first) |
| `NoSelection` | (optional) Do not add the field to the variant selection |

```bash
python "${CLAUDE_SKILL_DIR}/scripts/skd-edit.py" -TemplatePath "<path>" -Operation <op> -Value "<value>"
```

## Batch mode (batch)

Several values in one call via the `;;` separator:

```bash
-Operation add-field -Value "Цена: decimal(15,2) ;; Количество: decimal(15,3) ;; Сумма: decimal(15,2)"
```

Works for all operations except `set-query`, `set-structure` and `add-dataSet`.

## Report editing rules

Before editing a DCS report, read in full:
[DCS specifics](../bsl-coding-standards/reference/skd-specifics.md),
[accumulation registers](../bsl-coding-standards/reference/accumulation-registers.md),
[information registers](../bsl-coding-standards/reference/information-registers.md).

Remember: `add-field` and `add-calculated-field` add the field to the variant selection by default;
for a service field needed only by a formula, pass `-NoSelection`.
After edits - `skd-validate -ExpectedFields "<колонки ТЗ>"` and `skd-info -Mode variant`.

## Operations

### add-field - add a field to the data set

Shorthand: `"Имя [Заголовок]: тип @роль #ограничение"`.

```
"Цена: decimal(15,2)"
"Организация [Орг-ция]: CatalogRef.Организации @dimension"
"Служебное: string #noFilter #noOrder"
```

The field is added to the set and to the variant selection (unless `-NoSelection`). A duplicate dataPath - warning, skipped.

To make the field go into the selection of a specific structure grouping rather than the variant - use `-NoSelection` and then `add-selection "Имя @group=ИмяГруппы"`.

### add-total - add a total

Shorthand: `"<dataPath>: <выражение>"`. If the expression is a known aggregate function without parentheses (`Сумма`, `Количество`, `Минимум`, `Максимум`, `Среднее`), it is automatically wrapped in `Func(dataPath)`. If the function has parentheses or the expression is arbitrary - it is used as is.

```
"Цена: Среднее"                  # → Среднее(Цена)
"Стоимость: Сумма(Кол * Цена)"   # → как есть
"Проверка: Проверка"             # identity: выражение = Проверка
```

### add-calculated-field - add a calculated field

Shorthand: `"Имя [Заголовок]: тип = Выражение #noFilter #noOrder #noGroup"`.

```
"Маржа = Продажа - Закупка"
"Наценка [Наценка, %]: decimal(10,2) = Маржа / Закупка * 100"
"Служебное: string = \"\" #noFilter #noOrder #noGroup"
```

`#noFilter`, `#noOrder`, `#noGroup`, `#noField` -> `<useRestriction>` (similarly to add-field).

It is also added to the variant selection.

### add-parameter - add a parameter

```
"Период [Отчетный период]: StandardPeriod = LastMonth @autoDates"
"Организация: CatalogRef.Организации"
```

Shorthand: `"Имя [Заголовок]: тип = значение [availableValue=список] [@флаги]"`. `[Заголовок]` is optional - adds `<title>`.

Flags:
- `@autoDates` - generates a pair of hidden parameters `ДатаНачала`/`ДатаОкончания` for a StandardPeriod parameter.
- `@hidden` - hides the parameter from user settings (for constant parameters used in the query).
- `@always` - the parameter is always substituted into the query. Often together with `@hidden`, but also used separately (for visible required parameters such as the report period).
- `@valueList` - allows passing a value list into the parameter (for a list value below it is implied automatically, no need to specify it separately).

List value: several default values are set comma-separated in `значение`. For a comma inside one value - quotes `'...'`.

```
"Виды [Виды субконто]: ChartOfCharacteristicTypesRef.ВидыСубконтоХозрасчетные = ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Контрагенты, ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Договоры"
```

```
"ПС: CatalogRef.Контрагенты = Справочник.Контрагенты.ПустаяСсылка @hidden"
"Период: StandardPeriod = LastMonth @always"
"ПСчет: ChartOfAccountsRef.Хозрасчетный = ПланСчетов.Хозрасчетный.X @hidden @always"
"Округление: EnumRef.Округления = Окр1 availableValue=Перечисление.Округления.Окр1: руб., Перечисление.Округления.Окр1000: тыс."
```

`availableValue=` sets the initial list of allowed values. List format: `v1[: p1], v2[: p2], ...` - elements separated by `,`, presentation after `:`. If `,` or `:` occurs in a value or presentation - wrap it in single quotes `'...'`:

```
"Округление: ... = Окр1 availableValue=Окр1_00: 'руб., коп.', Окр1: руб."
```

### modify-parameter - modify an existing parameter

Shorthand: `"ИмяПараметра [Заголовок] [ключ=значение]... [@флаги]"`. Finds the parameter by name, updates the specified properties.

```
"ПорядокОкругления use=Always"
"ПорядокОкругления [Округление сумм] denyIncompleteValues=true"
"ПериодОтчета [Отчетный период]"                                  # только title
"ПорядокОкругления availableValue=Перечисление.Округления.Окр1: руб., Перечисление.Округления.Окр1000: тыс."
"СчетПС value=ПланСчетов.Хозрасчетный.КассаПредприятия"
"Виды value=ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Контрагенты, ПланВидовХарактеристик.ВидыСубконтоХозрасчетные.Договоры"
"Контрагент @hidden @always"
```

`[Заголовок]` is optional - sets or replaces `<title>`. Can be called without other kv pairs to update only the title.

`availableValue=` **replaces the whole list** of allowed values (old ones are deleted). Format and quotes are the same as in `add-parameter`.

`value=` replaces the parameter value. Several values comma-separated -> a **value list** (replaces all previous ones); for a comma inside a value - quotes `'...'`.

The `@hidden` / `@always` flags are the same as in `add-parameter`. Idempotent.

### rename-parameter - rename a parameter

Shorthand: `"OldName => NewName"`. Atomically updates the parameter name, `&Имя` references in expressions of other parameters (full matches only, `&ПериодX` is not affected), and entries in `dataParameters` of all variants. It does not touch the query text - renaming is strictly within the parameters area.

```
"Период => ПериодОтчета"
```

### reorder-parameters - reorder parameters in the given order

Shorthand: `"Имя1, Имя2, Имя3"`. A partial list - the specified parameters go first in the given order, the rest keep their original order and go at the end. Parameters from the list that are absent in the schema - warning, skipped.

```
"ПериодОтчета, НачалоПериода, КонецПериода"
```

### add-filter - add a filter to the variant

Shorthand: `"Поле оператор значение @флаги"`. Flags: `@off` (use=false), `@user` (userSettingID=auto), `@quickAccess`, `@normal`, `@inaccessible`.

```
"Номенклатура = _ @off @user"
"Дата >= 2024-01-01T00:00:00"
"Статус filled"
```

### add-dataParameter - add a data parameter to the variant

Shorthand: `"Имя [= значение] @флаги"`.

```
"Период = LastMonth @user"
"Организация @off @user"
```

### add-order - add sorting

Shorthand: `"Поле [desc]"`. asc by default. `Auto` - an auto item.

```
"Количество desc"
"Auto"
```

### add-selection - add a selection item

```
"Номенклатура"
"Auto"
"Folder(Поступление: ПолеА, ПолеБ, ПолеВ)"
```

`Folder(Название: поле1, поле2)` - a field group (SelectedItemFolder) with a title and `placement=Auto`.

`@group=ИмяГруппировки` - add to the selection of a named grouping (instead of the variant level):

```
"Folder(Поступление: ПолеА, ПолеБ) @group=ДанныеОтчета"
```

### add-dataSetLink - add a data set link

Shorthand: `"Источник > Приёмник on ВырИсточника = ВырПриёмника [param Имя]"`.

```
"Набор1 > Набор2 on Поле1 = Поле2"
"Набор1 > Набор2 on Поле1 = Поле2 [param Связь]"
```

### add-dataSet - add a data set

Shorthand: `"Имя: ТЕКСТ_ЗАПРОСА"` or `"ТЕКСТ_ЗАПРОСА"` (auto name `НаборДанныхN`).

```
"Доп: ВЫБРАТЬ 1 КАК Тест"
"ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура"
"Продажи: @queries/sales.sql"
```

`dataSource` is taken from the first existing one. A duplicate name - warning, skipped. Does not support batch mode (the query may contain `;;`).

### add-variant - add a settings variant

Shorthand: `"Имя [Представление]"`. The presentation is optional, defaults to the name.

```
"Детальный"
"Детальный [Детальный отчёт]"
```

Creates a variant with Auto selection + detail group. A duplicate name - warning, skipped.

### add-conditionalAppearance - add conditional appearance

Shorthand: `"Параметр = значение [when условие] [for Поле1, Поле2]"`. The `when` block uses the `add-filter` syntax (field operator value).

```
"ЦветТекста = web:Red when Сумма < 0"
"ЦветФона = web:LightGreen when Статус = Одобрен for Статус"
"МинимальнаяШирина = 50 for Организация"
"Формат = ЧДЦ=2 for Цена, Сумма"
```

Appearance value types (auto-detected): `web:*`/`style:*`/`win:*` -> Color, `true`/`false` -> Boolean, the `Формат`/`Текст`/`Заголовок` parameter -> LocalStringType, otherwise String.

Filter value types (auto-detected): `Перечисление.*`/`Справочник.*`/`ПланСчетов.*`/`Документ.*` -> DesignTimeValue, `true`/`false` -> Boolean, date -> DateTime, numbers -> Decimal, otherwise String.

OrGroup: several conditions via ` or ` in `when` are combined into FilterItemGroup/OrGroup:

```
"Формат = ЧЦ=15; ЧДЦ=0 when ПараметрыДанных.Округление = Перечисление.Округления.Окр1 or ПараметрыДанных.Округление = Перечисление.Округления.Окр1000"
```

**Important**: for data parameters use the `ПараметрыДанных.` prefix in the filter field.

### add-drilldown - connect decryption to resources in templates

Value - resource names (as in DCS fields/calculated fields), comma-separated.

```
"ПоступлениеИзПроизводства, ВыбытиеПрочее"
"Сумма_Дт83, Сумма_Дт99, Сумма_68, Сумма_84"
```

Connects DrillDown by `ИмяРесурса` to all templates containing the specified resources. Idempotent.

### set-query - replace the query text

Does not support batch mode. Value - the full query text or `@path/to/file.sql` (a reference to an external file). The path is resolved relative to Template.xml, then CWD.

When to use what: **substantial rework** (add fields, joins, rewrite a batch) -> dump the query via `/skd-info <tpl> -Mode query -Name <набор> -Raw -OutFile file.sql`, edit the file, return `set-query @file`. `-Raw` returns the query in full without decorations, so dump <-> return are exact (including multi-batch queries). **Point replacement** (rename an identifier, replace a substring) -> no dump needed, use `patch-query` below.

### patch-query - point replacement in the query text

Shorthand: `"старое => новое [@once]"`. Replaces all occurrences of the substring by default. Supports batch mode and `-DataSet`.

```
"СубконтоДт1) В => СубконтоКт1) В"
"КАК ВТ_СтароеИмя => КАК ВТ_НовоеИмя @once"
```

`@once` - fail with an error if the query does not have **exactly one** occurrence. Protects against accidental replacements in comments and similar identifiers.

Multiline substrings are supported.

### set-outputParameter - set an output parameter

```
"Заголовок = Мой отчёт"
"ВыводитьЗаголовок = true"
```

If the parameter already exists - replaces the value.

### set-structure - set the variant structure

Shorthand: `"Поле1 > Поле2 > details"`. `>` - a nested grouping level, `,` - several fields in one level, `details` - detail records. **Replaces the whole structure entirely** (including Selection/order/filter/conditionalAppearance of each group). For point modification of grouping fields while preserving settings - use `modify-structure`. Does not support batch mode.

```
"Организация > Номенклатура > details"
"Валюта, НаименованиеБанка, ИНН"
"details"
"СчетМеждународногоУчета @name=ДанныеОтчета"
```

`@name=Имя` - assigns a name to the grouping (`<dcsset:name>`). Used for binding templates via `groupName`.

### modify-structure - change the grouping fields of an existing group

The same shorthand as `set-structure`. Finds the group by `@name=`, replaces only `<groupItems>` (grouping fields). The group's Selection/order/filter/conditionalAppearance/outputParameters are preserved. Without `@name=` - an error.

```
"Валюта @name=ДанныеОтчета"
"Валюта, НаименованиеБанка @name=ДанныеОтчета"
"details @name=ДанныеОтчета"
```

### modify-field - modify an existing field

The same shorthand as `add-field`. Finds by dataPath, merges properties (non-empty ones override), preserves the position.

```
"Цена [Цена USD]: decimal(10,4) @dimension"
```

### set-field-role - set the field role

Shorthand: `"<dataPath> [@флаги] [kv=значение]"`. **Fully replaces** the field role. If the value contains only dataPath without flags/kv - removes the role.

```
"Сумма"                                                                 # снять роль полностью
"СуммаОстаток @balance"                                                 # простая балансовая роль
"СуммаНач @balance balanceGroupName=Сумма balanceType=OpeningBalance"   # с уточнением
"Контрагент @dimension parentDimension=Группа"
"Период @period"                                                        # роль периода
```

Flags: `@balance`, `@dimension`, `@account`, `@period`, `@required`, `@autoOrder`, `@ignoreNullValues`.
KV: `balanceGroupName`, `balanceType` (OpeningBalance/ClosingBalance), `parentDimension`, `accountTypeExpression`, `orderType` (Asc/Desc), `expression`, `periodNumber`, `periodType`.

Supports batch mode (`;;`).

### modify-filter - modify an existing filter

The same shorthand as `add-filter`. Finds by field, updates the operator/value/flags. See the `<use>` rule below.

### modify-dataParameter - modify a data parameter

The same shorthand as `add-dataParameter`. Finds by name, updates the value/flags. See the `<use>` rule below.

#### `<use>` rule for modify-filter / modify-dataParameter

Unlike `add-*`, in `modify-*` the `<use>` field is updated **only if a flag is set explicitly**:
- `@off` - set `<use>false</use>`
- `@on` - remove the existing `<use>false</use>` (enable the parameter)
- neither `@off` nor `@on` is set - `<use>` is not touched, the existing value is preserved (important: this means a disabled parameter will remain disabled after modifying other properties)

### remove-* and clear-*

| Operation | Value | Action |
|----------|-------|----------|
| `remove-field` | dataPath | Removes the field from the set + from the variant selection |
| `remove-total` | dataPath | Removes the total |
| `remove-calculated-field` | dataPath | Removes the calculated field + from selection |
| `remove-parameter` | name | Removes the parameter |
| `remove-filter` | field | Removes the first filter with the specified field |
| `clear-selection` | `*` | Clears all selection items |
| `clear-order` | `*` | Clears all order items |
| `clear-filter` | `*` | Clears all filter items |
| `clear-conditionalAppearance` | `*` | Clears all conditional appearance rules |

## Verification

```
/skd-validate <TemplatePath>    — валидация структуры после редактирования
/skd-info <TemplatePath>        — визуальная сводка
```
