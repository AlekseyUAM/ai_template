# Form command interface

The form key `commandInterface` controls the placement of commands on two form panels:

- `commandBar` - form command bar;
- `navigationPanel` - navigation panel.

Specify **only commands whose default placement changes** (visibility, group, order). Commands that the platform places automatically and without changes are not included in the block.

```json
"commandInterface": {
  "commandBar": [
    { "command": "Form.Command.Печать", "defaultVisible": false, "group": "FormCommandBarImportant",
      "visible": { "common": false, "roles": { "Бухгалтер": true } } },
    "CommonCommand.История"
  ],
  "navigationPanel": {
    "important": [ { "command": "CommonCommand.СвязанныеДокументы", "defaultVisible": false, "visible": false } ],
    "seeAlso":   [ { "command": "CommonCommand.Заметки", "defaultVisible": false, "visible": false } ]
  }
}
```

## Command element

Each panel element is an object, or a shorthand string (= a bare `command` with all other properties at defaults):

```json
"CommonCommand.История"
```

| Key | Type | Purpose |
|------|-----|-----------|
| `command` | string | Command reference verbatim: `CommonCommand.X`, `Document.X.StandardCommand.Y`, `Form.Command.X`, `Form.StandardCommand.OK`, `"0"` (empty / separator) |
| `type` | string | `Auto` (default, optional) or `Added` |
| `defaultVisible` | bool | Default visibility. In practice only `false` is set - to hide a command that is otherwise visible |
| `visible` | bool / object | Visibility with role exceptions: `bool` or `{ "common": bool, "roles": { "Имя": bool } }` |
| `group` | string | Placement group verbatim: predefined (`FormCommandBarImportant`, `FormNavigationPanelGoTo`, …), named (`CommandGroup.X`) or an extension GUID group |
| `index` | int | Command order inside the group |
| `attribute` | string | Attribute path for a navigation panel element |

## Two panel notation forms

A panel can be described as a **flat array** or a **tree by groups** - choose either.

**Flat array** - each element optionally carries its own `group`:

```json
"commandBar": [
  { "command": "Form.Command.Печать", "group": "FormCommandBarImportant", "defaultVisible": false },
  { "command": "CommonCommand.История", "group": "FormCommandBarImportant", "index": 1 }
]
```

**Tree** - an object `{ группа: [команды] }`; the group is taken from the key, the elements do not repeat it:

```json
"navigationPanel": {
  "important": [ "CommonCommand.СвязанныеДокументы" ],
  "goTo":      [ { "command": "Document.Заказ.StandardCommand.Movements", "defaultVisible": false, "visible": false } ],
  "seeAlso":   [ "CommonCommand.Заметки" ]
}
```

The tree group keys depend on the panel:

- `navigationPanel`: `important`, `goTo`, `seeAlso` (can be in Russian - `важное`, `перейти`, `смТакже`);
- `commandBar`: `important`, `createBasedOn`;
- any other key (`CommandGroup.X` or a GUID) is substituted into the group verbatim.

## Hide a visible command

The most common case - remove a command that the platform shows by default:

```json
"commandBar": [
  { "command": "Form.Command.Печать", "defaultVisible": false, "visible": false }
]
```

Show a command only to some roles:

```json
{ "command": "Form.Command.Печать", "defaultVisible": false,
  "visible": { "common": false, "roles": { "Бухгалтер": true } } }
```
