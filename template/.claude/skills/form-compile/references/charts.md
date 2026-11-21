# Charts, Gantt chart, planner

A chart field (`chart` / `ganttChart`), a planner field (`planner`) and a dendrogram output a value from an attribute of the corresponding type. The construct is always double:

1. **Attribute** of a chart/planner type (carries data and, if needed, design-time config).
2. Form **element** bound to the attribute via `path`.

The minimum is an attribute of the required type plus an element with the same `path`:

```json
"attributes": [ { "name": "Диаграмма", "type": "d5p1:Chart" } ],
"items":      [ { "chart": "ПолеДиаграммы", "path": "Диаграмма" } ]
```

An attribute filled in code (without built-in settings) is enough to declare with a type - the element binds and works.

## Attribute and element types

| Element | Type key | Attribute type | What the element carries additionally |
|---------|-----------|---------------|---------------------------------|
| Chart | `chart` | `d5p1:Chart` | - |
| Gantt chart | `ganttChart` | `d5p1:GanttChart` | `ganttTable` - nested table (see below) |
| Planner | `planner` | `pl:Planner` | - |
| Flowchart | `graphicalSchema` | `d5p1:FlowchartContextType` | `edit`, `warningOnEditRepresentation` |
| Period | `periodField` | `v8:StandardPeriod` | - |
| Dendrogram | `dendrogram` | - | - |

The element name is the key value (`"chart": "ПолеДиаграммы"`); `path` is the short attribute name.

### Gantt chart element (`ganttTable`)

A Gantt field contains a full-fledged table inside - set via the `ganttTable` key (same grammar as a regular `table`):

```json
{ "ganttChart": "Ганта", "path": "Ганта",
  "ganttTable": { "table": "ТаблицаГанта", "path": "Ганта", "height": 3 } }
```

## Chart design-time config (`chart`)

An attribute of type `d5p1:Chart` / `d5p1:GanttChart` can carry built-in chart settings - a `chart` object on the attribute. The platform always writes the full set of properties (~127: type, series, legend, title, scales, colors, fonts, axes), so **authoring from scratch is impractical** - take a working chart as a base and edit the semantic core.

`chart` keys = canonical chart property names; set only those you change:

```json
{ "name": "Диаграмма", "type": "d5p1:Chart", "chart": {
  "chartType": "Line",
  "isSeriesDesign": true, "realSeriesCount": "2",
  "realSeriesData": [
    { "id": "1", "color": "auto", "line": {"width":2,"gap":false,"style":"Solid"},
      "marker": "Auto", "text": "Серия 1", "strIsChanged": false, "isExpand": false,
      "isIndicator": false, "colorPriority": false }
  ],
  "isShowTitle": true, "title": "Продажи",
  "isShowLegend": true, "legendPlacement": "Bottom",
  "paletteKind": "Auto"
} }
```

The semantic core for editing:

| Key | Purpose |
|------|------------|
| `chartType` | Type: `Line` / `Pie` / `Bar` / `Histogram` / `Column` / `Area` / … |
| `realSeriesData` | Array of series - objects `{ id, text, color, line, marker, … }` |
| `isShowTitle` + `title` | Showing and text of the title |
| `isShowLegend` + `legendPlacement` | Showing and placement of the legend (`Bottom` / `Right` / …) |
| `paletteKind` | Palette (`Auto` / …) |
| `bkgColor` / `labelsColor` / … | Base colors |

Value forms inside `chart`:

- **Colors** - verbatim: `auto`, `style:ИмяСтиля`, `web:Red`, `#hex`.
- **`line`** - `{ width, gap, style }` (line style: `Solid` / …).
- **`border`** - `{ width, style }`.
- **`font`** - `{ kind: "AutoFont" }` or font attributes.
- **Localizable strings** (`title`, `vsFormat`, `lbFormat`, `labelFormat`, series `text`, …) - a bare string or `{ "ru": "…", "en": "…" }`.
- **Areas** (`elementsChart` / `elementsLegend` / `elementsTitle`) - `{ left, right, top, bottom }`.
- **Series** (`realSeriesData` / `realExSeriesData`) - arrays of objects.

Any of the ~127 properties is overridden by its canonical name; leave the rest at defaults (do not specify - taken from the base).

### Gantt chart (`d5p1:GanttChart`)

An attribute of type `d5p1:GanttChart` uses the **same** `chart` key. Inside is a nested full `chart` block plus Gantt specifics (`points` / `series` / `timeScale` / `drawEmpty` / …). Also take a working Gantt chart as a base.

> **Limitation.** Charts (Chart/Gantt) with filled **points/axes** (`realPointData` / `realDataItems`, filled `valuesAxis` / `pointsAxis`) are not supported by the generic engine - this is a rare variant. Common dashboard charts and Gantt charts (series / legend / appearance / scales) are fully supported.

## Planner design-time config (`planner`)

An attribute of type `pl:Planner` carries built-in planner settings - a `planner` object. The compiler substitutes defaults for missing keys, so authoring can be brief:

```json
{ "name": "Планировщик", "type": "pl:Planner", "planner": {
  "items": [
    { "text": "Встреча", "begin": "2026-06-09T01:00:00", "end": "2026-06-09T04:00:00",
      "borderColor": "auto", "backColor": "auto", "deleted": false, "editMode": "EnableEdit" }
  ],
  "period": { "begin": "2026-06-09T00:00:00", "end": "2026-06-09T23:59:59" },
  "displayCurrentDate": true, "itemsTimeRepresentation": "BeginTime",
  "timeScale": { "placement": "Left", "levels": [ { "measure": "Hour", "interval": 1 } ] }
} }
```

The minimum is one `item`:

```json
"planner": { "items": [ { "text": "Встреча", "begin": "2026-06-09T01:00:00", "end": "2026-06-09T04:00:00" } ] }
```

| `planner` key | Type | Purpose |
|----------------|-----|------------|
| `items` | array | Schedule items. Item fields: `text`, `tooltip`, `begin`, `end`, `value`, `borderColor`, `backColor`, `textColor`, `font`, `border`, `replacementDate`, `deleted` (bool), `editMode` (`EnableEdit` / …), `id` (optional - auto-GUID), `textFormatted` |
| `dimensions` | array | Planner dimensions (sections). Fields: `value` (section object - reference `Enum.X.EnumValue.Y` / `Справочник.X`; omit -> empty), `text` (title), `borderColor`, `backColor`, `textColor`, `font`, `textFormatted`, `elements`. `elements` - dimension elements, recursive (can carry nested `elements`): `value`, `text`, colors, `font`, `showOnlySubordinatesAreas` (bool), `textFormatted` |
| `period` | object | Displayed period `{ begin, end }` (optional) |
| `timeScale` | object | Time scale (see below) |
| `borderColor` / `backColor` / `textColor` / `lineColor` | color | Colors (default `auto`) |
| `font` | font | Font (default `{ kind: "AutoFont" }`) |
| `border` | border | Border `{ width, style }` |
| `beginOfRepresentationPeriod` / `endOfRepresentationPeriod` | dateTime | Representation period |
| `displayCurrentDate` / `displayWrapHeaders` / `displayTimeScaleWrapHeaders` / `alignElementsOfTimeScale` | bool | Display flags |
| `timeScaleWrapHeadersFormat` | ML | Format of wrapped scale headers |
| `timeScaleWrapBeginIndent` / `timeScaleWrapEndIndent` | int | Scale wrap indents |
| `periodicVariantUnit` / `periodicVariantRepetition` | value / int | Unit and multiplicity of the periodic variant |
| `itemsTimeRepresentation` | value | Time representation of items (`BeginTime` / …) |
| `itemsBehaviorWhenSpaceInsufficient` / `newItemsTextType` / `fixDimensionsHeader` / `fixTimeScaleHeader` | value | Behavior of items and headers |
| `autoMinColumnWidth` / `autoMinRowHeight` | bool | Auto minimum sizes |
| `minColumnWidth` / `minRowHeight` | int | Minimum sizes |

Time scale (`timeScale`):

```json
"timeScale": {
  "placement": "Left",
  "levels": [ { "measure": "Hour", "interval": 1 } ]
}
```

Keys: `placement`, `levels` (array of levels), `transparent`, `backColor`, `textColor`, `currentLevel`. A level: `measure` (`Hour` / `Day` / …), `interval`, `show`, `line` (`{ width, gap, style }`), `scaleColor`, `dayFormatRule`, `format` (ML), `labels` (`{ ticks }`), `backColor`, `textColor`, `showPereodicalLabels`.

Value forms in `planner` are the same as in the chart: colors verbatim (`auto` / `style:X` / `web:Red` / `#hex`); font `{ kind: "AutoFont" }` or a ref string; border `{ width, style }`; ML formats - a string or `{ "ru": …, "en": … }`.

> **Limitation.** Binding a schedule item to dimension elements (`item.dimensionValues`) is still always empty. The dimensions themselves (`dimensions`) can be set.
