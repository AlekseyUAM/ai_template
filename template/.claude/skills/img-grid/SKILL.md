---
name: img-grid
description: Overlay a numbered grid on an image. Use when analyzing a screenshot of a template or print form - measure column proportions before generating a spreadsheet document
argument-hint: <ImagePath> [-c COLS]
allowed-tools:
  - Bash
  - Read
---

# /img-grid - Grid for template analysis

Overlays a numbered grid on a print form image. Lets you precisely determine column boundaries, their proportions and spans for generating a spreadsheet document template.

## Usage

```
/img-grid <ImagePath> [-c COLS] [-o OUTPUT]
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|:------------:|--------------|-----------------------------------------------|
| ImagePath | yes          | -            | Path to the image (PNG, JPG)                  |
| -c COLS   | no           | 50           | Number of vertical divisions                  |
| -r ROWS   | no           | auto         | Number of horizontal divisions (auto = square cells) |
| -o OUTPUT | no           | `<name>-grid.<ext>` | Path for the result                 |

## Command

```bash
python "${CLAUDE_SKILL_DIR}/scripts/overlay-grid.py" "<ImagePath>" [-c 50] [-o "<OutputPath>"]
```

Requires Python 3 with the Pillow library (`pip install Pillow`).

## What it does

1. Draws semi-transparent vertical (red) and horizontal (blue) lines
2. Numbers the lines in separate margins at the top and left (does not overlap the content)
3. Every 5th and 10th line is highlighted brighter for easier counting

## How to use the result

### 1. Determine column boundaries

Look at the image with the grid and record the coordinates of the vertical boundaries of each table column (in grid-line numbers).

### 2. Find the base grid

If the form has several tables with different layouts (for example, the document header and the main table), merge all boundary points. Each segment between adjacent boundaries is one MXL column.

Example for M-11:
- Header: boundaries 0, 2, 4, 9, 14, 21, 28, 34, 40, 48
- Table: boundaries 0, 2, 4, 11, 16, 19, 23, 28, 32, 36, 42, 48
- Union: 0, 2, 4, 9, 11, 14, 16, 19, 21, 23, 28, 32, 34, 36, 40, 42, 48
- Result: **16 base columns** with proportions 2, 2, 5, 2, 3, 2, 3, 2, 2, 5, 4, 2, 2, 4, 2, 6

### 3. Write to the JSON DSL

```json
{
  "columns": 16,
  "page": "A4-landscape",
  "columnWidths": {
    "1": "2x", "2": "2x", "3": "5x", "4": "2x", "5": "3x",
    "6": "2x", "7": "3x", "8": "2x", "9": "2x", "10": "5x",
    "11": "4x", "12": "2x", "13": "2x", "14": "4x", "15": "2x", "16": "6x"
  }
}
```

The `"page"` field lets the compiler automatically calculate absolute widths from the proportions.

### 4. Compile

`/mxl-compile` -> `/mxl-validate` -> `/mxl-info`
