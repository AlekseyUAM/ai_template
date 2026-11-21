# Appearance

Two independent mechanisms: **element appearance** (permanent colors/font/border on a specific element) and **conditional form appearance** (`conditionalAppearance` - rules applied when a condition holds).

## Element appearance (colors / fonts / border)

Properties are set directly on the element. Applies to fields (`input`/`check`/`radio`/`labelField`/`picField`/`calendar`), decorations (`label`/`picture`), buttons (`button`), groups (`group`/`columnGroup`), pages (`page`/`pages`), popups (`popup`) and tables (`table`). Each property is optional.

| Key | What it sets |
|------|-----------|
| `textColor` | Text color |
| `backColor` | Background color |
| `borderColor` | Border color |
| `font` | Font |
| `border` | Border |
| `titleTextColor` / `titleBackColor` / `titleFont` | Column title text color / background color / font (`labelField`, table columns); for `page`/`pages`/`popup` - `titleTextColor`/`titleFont` of the page/popup title |
| `footerTextColor` / `footerBackColor` / `footerFont` | Column footer text color / background color / font |

The same properties are also available via the element's `appearance` dictionary - under the Russian platform parameter names: `ЦветТекста`, `ЦветФона`, `ЦветРамки`, `Шрифт`, `Граница`, `ЦветТекстаЗаголовка`, `ЦветФонаЗаголовка`, `ШрифтЗаголовка`, `ЦветТекстаПодвала`, `ЦветФонаПодвала`, `ШрифтПодвала`. This is the same record as in the conditional appearance rules (below) and in the `appearance` of a dynamic list field.

### Color

A string in one of the forms:

| Form | Value |
|-------|----------|
| `web:Имя` | Color from the web palette, e.g. `web:Red`, `web:FireBrick`, `web:HoneyDew` |
| `win:Имя` | Windows system color, e.g. `win:MenuBar`, `win:ButtonText`, `win:DisabledText` |
| `style:ИмяСтиля` | Reference to a configuration/platform style item, e.g. `style:FormBackColor`, `style:BorderColor` |
| `#RRGGBB` | RGB hex, e.g. `#FF0000` |

The name must exist in its palette (a nonexistent web-/win-color or a reference to a missing `style:` item is a form load error).

### Font (`font` / `titleFont` / `footerFont`)

- The string `"style:ИмяСтиля"` - a font from a style item. Minimal form.
- An object - only the needed attributes are set:

| Key | Purpose |
|------|-----------|
| `ref` | Reference to a style (`"style:X"`) or a system font (`"sys:…"`) |
| `faceName` | Typeface name (for a custom font) |
| `height` | Size |
| `bold` / `italic` / `underline` / `strikeout` | `true`/`false` - style |
| `scale` | Scale, % |
| `kind` | `Absolute` (custom font - with `faceName`+`height`) / `WindowsFont` (system - with `ref:"sys:…"`) |

```json
{ "label": "Внимание!", "textColor": "web:FireBrick",
  "font": { "faceName": "Arial", "height": 12, "bold": true, "kind": "Absolute", "scale": 100 } }
```

### Border (`border`)

- The string `"style:ИмяСтиля"` (or the object `{ "ref": "style:X" }`) - a border from a style.
- The object `{ "width": N, "style": "..." }` - a custom border. `style` - one of: `Single`, `Double`, `Underline`, `DoubleUnderline`, `Overline`, `Embossed`, `Indented`, `WithoutBorder`.

```json
{ "input": "Цена", "path": "Объект.Цена", "textColor": "#FF0000",
  "borderColor": "style:BorderColor", "border": { "width": 1, "style": "Single" } }
{ "labelField": "Код", "titleTextColor": "web:HoneyDew", "border": "style:ControlBorder" }
```

## Conditional form appearance (`conditionalAppearance`)

The top-level form key is an array of rules. Each rule applies appearance to the listed fields when its condition holds.

```json
"conditionalAppearance": [
  { "selection": ["ОбычноеПоле"], "filter": ["ЧисловоеПоле > 100"],
    "appearance": { "ЦветФона": "style:FormBackColor" },
    "presentation": { "ru": "Подсветка", "en": "Highlight" } }
]
```

| Key | Type | Purpose |
|------|-----|-----------|
| `selection` | array | Names of the form fields to format |
| `filter` | array | Application condition (grammar below) |
| `appearance` | object | "platform parameter: value" dictionary |
| `presentation` | string / object | Rule caption in the settings list |
| `use` | bool | `false` - the rule is disabled |
| `viewMode` | string | Setting display mode |
| `userSettingID` | string | Custom setting ID; `"auto"` - generate |

### filter

The same grammar as in a list filter - shorthand `"Поле оператор значение @флаги"` or an object:

```json
"filter": [
  "Статус = 3",
  { "field": "Сумма", "op": ">=", "value": 1000 },
  { "group": "Or", "items": [ "Просрочено = true", "Заблокирован = true" ] }
]
```

- **Operators:** `=` `<>` `>` `>=` `<` `<=`, `in` / `notIn`, `inHierarchy`, `contains` / `notContains`, `beginsWith` / `notBeginsWith`, `like` / `notLike` (`%` pattern), `filled` / `notFilled`.
- **Flags:** `@off` (disabled), `@user`, `@quickAccess`; `_` = empty value.
- **Group:** `{ "group": "And"|"Or"|"Not", "items": [...], "use"? }`.
- **Date value:** ISO date `"2024-01-01T00:00:00"` - a fixed date; a named relative period - by the string `"BeginningOfThisWeek"` with `"valueType": "v8:StandardBeginningDate"` (options `BeginningOfThisDay`/`BeginningOfThisWeek`/`BeginningOfThisMonth`/`BeginningOfThisYear`/…).

### appearance

"platform parameter: value" dictionary. Parameter names are Russian: `ЦветТекста`, `ЦветФона`, `Шрифт`, `Граница`, `Текст`, `Заголовок`, `Формат`, `ВидимостьЭлемента`, `Доступность` and other layout appearance parameters.

Values:
- **Color** (`ЦветТекста`/`ЦветФона`/…) and **font** (`Шрифт`) - the same forms as in element appearance above (`web:`/`win:`/`style:`/`#RRGGBB`; font - the string `"style:X"` or an object).
- **Text parameters** (`Текст`/`Заголовок`/`Формат`) - depending on the value form:
  - a bare string -> a non-localized literal (`""` -> empty value);
  - the object `{ "ru": "...", "en": "..." }` -> a localizable string;
  - the object `{ "field": "путь" }` -> a reference to a layout field.

```json
"conditionalAppearance": [
  { "selection": ["Остаток"], "filter": ["Остаток < 0"],
    "appearance": { "ЦветТекста": "web:Red", "Шрифт": { "bold": true } } },
  { "selection": ["Комментарий"], "filter": ["Комментарий notFilled"],
    "appearance": { "Текст": { "ru": "— нет данных —" }, "ЦветТекста": "win:DisabledText" } }
]
```

> Conditional appearance of the **dynamic list itself** is set not here but in `settings.conditionalAppearance` of the list attribute - see `references/dynamic-list.md`.
