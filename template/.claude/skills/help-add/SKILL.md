---
name: help-add
description: Add built-in help to a 1C object (data processor, report, catalog, document, etc.). Use when the user asks to add help, built-in help to an object
argument-hint: <ObjectName>
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

# /help-add - Add help

Adds built-in help to an object: metadata file `Help.xml`, HTML page, and if needed updates form metadata.

## Usage

```
/help-add <ObjectName> [Lang] [SrcDir]
```

| Parameter  | Required | Default | Description                         |
|------------|:--------:|---------|-------------------------------------|
| ObjectName | yes      | -       | Object path relative to SrcDir (for example `Catalogs/МойСправочник`, `DataProcessors/МояОбработка`) |
| Lang       | no       | `ru`    | Help language code                  |
| SrcDir     | no       | `src`   | Source directory                    |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/help-add.py" -ObjectName "<ObjectName>" [-Lang "<Lang>"] [-SrcDir "<SrcDir>"]
```

## What the script does

- Creates `Ext/Help.xml` and `Ext/Help/ru.html` - the help template
- If the object has forms - adds `<IncludeHelpInContents>` to form metadata (if missing)
- Help is **not registered** in `ChildObjects` - the presence of files is enough

## After the run

Edit `Ext/Help/ru.html` - fill it with help content (standard HTML: `<h1>`..`<h4>`, `<p>`, `<ul>`, `<table>`, etc.). The help button appears automatically via `Autofill` in the form's AutoCommandBar.
