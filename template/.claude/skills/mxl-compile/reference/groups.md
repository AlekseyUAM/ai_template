# Row and column groups

A range of rows or columns that collapses with a button in the margins. Set as a flat list;
nesting is expressed by one range being contained in another:

```json
"rowGroups": [
  { "rows": "2-4" },
  { "rows": 3 },
  { "rows": 5, "name": "Итоговая", "collapsed": true, "titleLocation": "begin" }
],
"columnGroups": [
  { "cols": "2-3", "name": { "ru": "Показатели", "en": "Values" } },
  { "cols": 3 }
]
```

| Field | Required | Default | Description |
|------|:-----:|-----------|----------|
| `rows` / `cols` | yes | - | Range, 1-based: a number or `"N-M"` |
| `name` | no | - | Group name: a string or a "language -> text" object |
| `collapsed` | no | `false` | Whether the group is collapsed on open |
| `titleLocation` | no | `auto` | Title position: `begin`, `end`, `auto` |

Ranges are either nested or non-overlapping: partial overlap is an error. Order in the list
does not matter; the number of nesting levels is calculated automatically.
