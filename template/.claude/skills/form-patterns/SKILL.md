---
name: form-patterns
description: Reference of managed form layout patterns for 1C. Use as a reference when designing forms - archetypes, conventions, advanced techniques
argument-hint: (no arguments)
allowed-tools: []
---

# /form-patterns - form layout patterns

A reference of typical design patterns for 1C managed forms. Call it **before** designing a form via `/form-compile`, when the user requirements do not detail the element layout.

**How to use:** choose a suitable archetype, apply naming conventions, use advanced patterns when needed.

---

## Form archetypes

### Document form

```
Шапка (horizontal, 2 колонки)
├─ Левая (vertical): НомерДата (H: Номер + Дата "от"), Контрагент, Договор
├─ Правая (vertical): Организация, Подразделение, ЦеныИВалюта (надпись-ссылка)
Страницы (pages)
├─ Товары: таблица Объект.Товары
├─ Услуги: таблица Объект.Услуги (опционально)
└─ Дополнительно: прочие реквизиты
Подвал (vertical)
├─ Итоги (horizontal): Всего, НДС, Скидка
└─ КомментарийОтветственный (horizontal): Комментарий + Ответственный
```

**Events:** OnCreateAtServer, OnReadAtServer, OnOpen, BeforeWriteAtServer, AfterWriteAtServer, AfterWrite, NotificationProcessing
**Properties:** autoTitle=false

### Data processor form (DataProcessor)

```
Параметры (vertical)
├─ Группа полей ввода (Организация, Период, режимы работы)
├─ Информационные надписи (label, hyperlink)
Рабочая область
├─ Таблица данных или Pages с вкладками
Главная АКП формы (autoCmdBar)
├─ Выполнить / Применить (defaultButton: true)
└─ Закрыть (stdCommand: Close)
```

**Events:** OnCreateAtServer, OnOpen, NotificationProcessing
**Properties:** windowOpeningMode=LockOwnerWindow (if a dialog), autoTitle=false

### List form

```
Отборы (group: alwaysHorizontal)
├─ ГруппаОтбор[Поле] (H): Флажок + Поле ввода (для каждого фильтра)
Список (table, DynamicList)
├─ Колонки: labelField (не input — данные только для чтения)
```

**Events:** OnCreateAtServer, OnOpen, NotificationProcessing, OnLoadDataFromSettingsAtServer
**Properties:** autoSaveDataInSettings=Use
**Filters:** a pair of attributes for each - `Отбор[Поле]` (value) + `Отбор[Поле]Использование` (boolean)

### Catalog item form

**Simple:**
```
ГруппаРеквизитов (horizontal)
├─ Наименование -> Объект.Description
└─ Код -> Объект.Code (если нужен)
```

**Complex:**
```
Главное (vertical)
├─ Наименование -> Объект.Description
├─ Параметры (horizontal, 2 колонки)
│  ├─ Левая: основные реквизиты
│  └─ Правая: дополнительные реквизиты
└─ КонтактныеДанные / Дополнительно (vertical)
```

**Events:** OnCreateAtServer, OnReadAtServer, BeforeWriteAtServer, NotificationProcessing

### Wizard

```
Страницы (pages, OnCurrentPageChange)
├─ Шаг1: описание + параметры
├─ Шаг2: основная работа
└─ Шаг3: результат
Главная АКП формы (autoCmdBar)
├─ Назад, Далее (defaultButton: true), Выполнить
└─ Закрыть (stdCommand: Close)
```

**Properties:** windowOpeningMode=LockOwnerWindow

---

## Naming conventions

### Groups

| Purpose | Name | Type |
|-----------|-----|-----|
| Header | `ГруппаШапка` | horizontal |
| Left column | `ГруппаШапкаЛевая` | vertical |
| Right column | `ГруппаШапкаПравая` | vertical |
| Number+Date | `ГруппаНомерДата` | horizontal |
| Footer | `ГруппаПодвал` | vertical |
| Totals | `ГруппаИтоги` | horizontal |
| Main form command bar | `ФормаКоманднаяПанель` | autoCmdBar |
| Pages | `ГруппаСтраницы` / `Страницы` | pages |
| Warning | `ГруппаПредупреждение` | horizontal, visible:false |
| Extra section | `ГруппаДополнительно` / `ГруппаПрочее` | vertical, collapse |

### Elements

| Purpose | Name |
|-----------|-----|
| Field in a table | `[Таблица][Поле]` |
| Total | `Итоги[Поле]` |
| Link label | `[Поле]Надпись` |
| Filter | `Отбор[Поле]` |
| Filter checkbox | `Отбор[Поле]Использование` |
| Command button | `[Команда]Кнопка` |
| Banner picture | `[Баннер]Картинка` |
| Banner label | `[Баннер]Надпись` |
| Submenu | `Подменю[Действие]` |

### Event handlers

Name = element name + suffix in Russian:

| Event | Suffix | Example |
|---------|---------|--------|
| OnChange | ПриИзменении | `ОрганизацияПриИзменении` |
| StartChoice | НачалоВыбора | `КонтрагентНачалоВыбора` |
| Click | Нажатие | `ЦеныИВалютаНажатие` |
| OnEditEnd | ПриОкончанииРедактирования | `ТоварыПриОкончанииРедактирования` |
| OnStartEdit | ПриНачалеРедактирования | `ТоварыПриНачалеРедактирования` |

Form handlers: `ПриСозданииНаСервере`, `ПриОткрытии`, `ПередЗакрытием`, `ОбработкаОповещения`.

---

## Layout principles

1. **Reading order.** Top to bottom, left to right. The most important things go on top.
2. **Two-column header.** Main attributes on the left (counterparty, warehouse), organizational ones on the right (organization, department).
3. **Action buttons go on the main form command bar** (`autoCmdBar`), not in a separate group on the form. The main button is `defaultButton: true`. Close is always last.
4. **Tables are the main area.** Tabular sections take most of the form, usually on Pages.
5. **Totals next to the table.** In the footer, a horizontal group, all fields readOnly.
6. **Filters are a separate zone.** Above the list, alwaysHorizontal, a "checkbox + field" pair per filter.
7. **Hidden elements for states.** Banners, warnings - `visible: false`, shown programmatically.
8. **Link labels for dialogs.** `labelField` with `hyperlink: true` and the Click event.

---

## Advanced patterns (ERP)

### Collapsible groups

For optional sections (signatures, additional, other):

```json
{ "group": "collapsible", "name": "ГруппаПодписи", "title": "Подписи",
  "collapsed": true, "children": [...] }
```

### Warning banner

A "picture + label" group, hidden by default, shown programmatically:

```json
{ "group": "horizontal", "name": "ГруппаПредупреждение", "showTitle": false,
  "visible": false, "children": [
    { "picture": "ПредупреждениеКартинка" },
    { "label": "ПредупреждениеНадпись", "title": "Текст", "maxWidth": 76, "autoMaxWidth": false }
]}
```

### Popup menu in the command bar

Group related commands (print, send) into one button with an icon:

```json
{ "cmdBar": "КоманднаяПанель", "children": [
    { "popup": "ПодменюПечать", "title": "Печать",
      "picture": "StdPicture.Print", "representation": "Picture", "children": [
        { "button": "ПечатьНакладная", "command": "Печать" },
        { "button": "ПечатьСчёт", "command": "ПечатьСчёт" }
    ]}
]}
```

### Form without the standard command bar

For modal dialogs and wizards:

```json
{ "properties": { "commandBarLocation": "None", "windowOpeningMode": "LockWholeInterface" } }
```

### Hyperlink label

Instead of a button to open subforms (ЦеныИВалюта, УчётнаяПолитика):

```json
{ "labelField": "ЦеныИВалютаНадпись", "path": "ЦеныИВалюта", "hyperlink": true, "on": ["Click"] }
```

---

## Example: data processor form (full DSL)

```json
{
  "title": "Загрузка данных из CSV",
  "properties": { "autoTitle": false, "windowOpeningMode": "LockOwnerWindow" },
  "events": { "OnCreateAtServer": "ПриСозданииНаСервере" },
  "elements": [
    { "group": "vertical", "name": "ГруппаПараметры", "children": [
      { "input": "ФайлЗагрузки", "path": "ФайлЗагрузки", "title": "Файл", "clearButton": true, "horizontalStretch": true, "on": ["StartChoice"] },
      { "input": "Кодировка", "path": "Кодировка" },
      { "input": "Разделитель", "path": "Разделитель", "title": "Разделитель колонок" }
    ]},
    { "table": "Данные", "path": "Объект.Данные", "on": ["OnStartEdit"], "columns": [
      { "input": "ДанныеНомерСтроки", "path": "Объект.Данные.LineNumber", "readOnly": true, "title": "№" },
      { "input": "ДанныеНаименование", "path": "Объект.Данные.Наименование" },
      { "input": "ДанныеКоличество", "path": "Объект.Данные.Количество", "on": ["OnChange"] },
      { "input": "ДанныеСумма", "path": "Объект.Данные.Сумма", "readOnly": true }
    ]},
    { "autoCmdBar": "ФормаКоманднаяПанель", "children": [
      { "button": "Загрузить", "command": "Загрузить", "title": "Загрузить из файла", "defaultButton": true },
      { "button": "Очистить", "command": "Очистить", "title": "Очистить таблицу" },
      { "button": "Закрыть", "stdCommand": "Close" }
    ]}
  ],
  "attributes": [
    { "name": "Объект", "type": "ExternalDataProcessorObject.ЗагрузкаИзCSV", "main": true },
    { "name": "ФайлЗагрузки", "type": "string" },
    { "name": "Кодировка", "type": "string(20)" },
    { "name": "Разделитель", "type": "string(5)" }
  ],
  "commands": [
    { "name": "Загрузить", "action": "ЗагрузитьОбработка" },
    { "name": "Очистить", "action": "ОчиститьОбработка" }
  ]
}
```
