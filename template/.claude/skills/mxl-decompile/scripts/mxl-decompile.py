#!/usr/bin/env python
# mxl-decompile v1.31 — Decompile 1C spreadsheet to JSON
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills

import argparse
import os
import sys
from collections import OrderedDict
from lxml import etree

# Case-insensitive input: parameter names and choices values are accepted
# in any case (argparse matches exactly by default).
def ci_parse_args(parser, argv=None):
    """parse_args: parameter names and choices values are accepted in any case."""
    argv = list(sys.argv[1:] if argv is None else argv)
    names = {s.lower(): s for a in parser._actions for s in a.option_strings}
    for i, tok in enumerate(argv):
        if tok.startswith('-') and tok.lower() in names:
            argv[i] = names[tok.lower()]
    # choices mirrors [ValidateSet]; canonicalize BEFORE parsing, otherwise argparse rejects the case
    choice_map = {}
    for a in parser._actions:
        if a.choices:
            for s in a.option_strings:
                choice_map[s] = {str(c).lower(): c for c in a.choices}
    for i in range(len(argv) - 1):
        m = choice_map.get(argv[i])
        if m and argv[i + 1].lower() in m:
            argv[i + 1] = m[argv[i + 1].lower()]
    return parser.parse_args(argv)


# --- Namespace map ---

NSMAP = {
    "d": "http://v8.1c.ru/8.2/data/spreadsheet",
    "v8": "http://v8.1c.ru/8.1/data/core",
    "v8ui": "http://v8.1c.ru/8.1/data/ui",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def find(node, xpath):
    return node.find(xpath, NSMAP)


def findall(node, xpath):
    return node.findall(xpath, NSMAP)


def text_of(node):
    if node is not None and node.text:
        return node.text
    return None


def to_font_size(raw):
    """Font size may be fractional (8.3, 11.3 - in the ERP corpus this is a third of templates).
    int() failed on such a value - round the fractional size. Keep integers integer, otherwise "10" -> "10.0"."""
    s = str(raw).strip() if raw is not None else ''
    if not s:
        return 0
    try:
        d = float(s)
    except (TypeError, ValueError):
        return 0
    return int(d) if d == int(d) else d


def format_tag_kind():
    """Value type of each tag - derived from the corpus, not written by eye.
    line - reference to the <line> palette; color - #RRGGBB / style: / web: / win:
    ml - multilingual string; enum - closed list (see format_enum_values).
    containsValue / valueType / controlType are NOT included here: these are properties of a specific cell,
    while style is a shared entity, one for many cells."""
    return {
        'autoIndent': 'int', 'autoMarkIncomplete': 'bool', 'autoWidthCalculation': 'bool',
        'backColor': 'color', 'border': 'line', 'borderColor': 'color',
        'bottomBorder': 'line', 'bySelectedColumns': 'bool', 'columnSizeChange': 'enum',
        'detailsUse': 'enum', 'drawingBorder': 'line',
        'drawingHaveBottomBorder': 'bool', 'drawingHaveLeftBorder': 'bool',
        'drawingHaveRightBorder': 'bool', 'drawingHaveTopBorder': 'bool',
        'editFormat': 'ml', 'fillType': 'enum', 'font': 'int', 'format': 'ml',
        'height': 'int', 'hidden': 'bool', 'horizontalAlignment': 'enum',
        'hyperLink': 'bool', 'indent': 'int', 'leftBorder': 'line',
        'markNegatives': 'bool', 'mask': 'ml', 'pattern': 'enum', 'patternColor': 'color',
        'picHorizontalAlignment': 'enum', 'picIndex': 'int', 'picVerticalAlignment': 'enum',
        'pictureSizeMode': 'enum', 'print': 'bool', 'protection': 'bool',
        'rightBorder': 'line', 'textColor': 'color', 'textOrientation': 'int',
        'textPlacement': 'enum', 'textPosition': 'enum', 'topBorder': 'line',
        'verticalAlignment': 'enum', 'width': 'int', 'widthWeightFactor': 'int',
    }


RU_NAME = 'Русский'


def format_ml_tags():
    """Tags whose value is a multilingual string (<v8:item> per language), not a scalar."""
    return {'format': True, 'editFormat': True, 'mask': True}


def color_to_dsl(node, val):
    """The platform stores color as a value with a namespace prefix. style: is declared at the document
    root and is read as is; web/win are declared directly on the node with a generated prefix
    (d3p1), so it must be resolved into a URI and the usual web:/win: returned."""
    if ':' not in val or val.startswith('style:'):
        return val
    prefix, name = val.split(':', 1)
    uri = node.nsmap.get(prefix)
    if uri == 'http://v8.1c.ru/8.1/data/ui/colors/web':
        return 'web:' + name
    if uri == 'http://v8.1c.ru/8.1/data/ui/colors/windows':
        return 'win:' + name
    return val


CFG_NS = 'http://v8.1c.ru/8.1/data/enterprise/current-config'

# Cell control element: in the export this is a GUID, the platform has no names in XML.
VALUE_CONTROL_NAMES = {
    '381ed624-9217-4e63-85db-c4c3cb87daae': 'input',
    '35af3d93-d7c7-4a2e-a8eb-bac87a1a3f26': 'checkbox',
}


def value_type_to_dsl(node):
    """Inverse of the compiler's type emitter: <valueType> -> DSL string in the SHORTEST
    form (Boolean, String, String(10,fixed), Number(15,3,nonneg), DateTime, CatalogRef.X,
    AnyRef), from which the compiler will restore the same XML. Empty tag -> empty string:
    "contains value" without a type specified is a standalone state.
    Resolve the prefix of a reference type by URI, not by name: the platform names a local
    declaration with a generated dNpM. Leave a foreign namespace as is."""
    types = []
    quals = {}
    for child in node:
        tag = etree.QName(child).localname
        if tag in ('Type', 'TypeSet'):
            types.append((tag, child, (child.text or '').strip()))
        elif tag.endswith('Qualifiers'):
            quals[tag[:-len('Qualifiers')]] = child

    def qual(kind, name, default=''):
        el = quals.get(kind)
        if el is None:
            return default
        sub = find(el, 'v8:' + name)
        val = text_of(sub)
        return val.strip() if val else default

    parts = []
    for tag, child, val in types:
        if ':' in val:
            prefix, name = val.split(':', 1)
            uri = child.nsmap.get(prefix)
            if uri == CFG_NS:
                val = name
            elif uri == 'http://www.w3.org/2001/XMLSchema':
                val = 'xs:' + name
        if val == 'xs:boolean':
            parts.append('Boolean')
        elif val == 'xs:string':
            length = qual('String', 'Length', '0')
            fixed = qual('String', 'AllowedLength', 'Variable') == 'Fixed'
            if fixed:
                parts.append(f'String({length},fixed)')
            elif length != '0':
                parts.append(f'String({length})')
            else:
                parts.append('String')
        elif val == 'xs:decimal':
            digits = qual('Number', 'Digits', '0')
            fraction = qual('Number', 'FractionDigits', '0')
            nonneg = qual('Number', 'AllowedSign', 'Any') == 'Nonnegative'
            if nonneg:
                parts.append(f'Number({digits},{fraction},nonneg)')
            elif digits != '0' or fraction != '0':
                parts.append(f'Number({digits},{fraction})')
            else:
                parts.append('Number')
        elif val == 'xs:dateTime':
            parts.append(qual('Date', 'DateFractions', 'DateTime'))
        else:
            parts.append(val)
    return ' + '.join(parts)


def value_to_dsl(xsi_type, text):
    """Input field cell value -> DSL literal. The value type is expressed by the literal itself:
    number -> number, boolean -> true/false, string and date -> string. Write an empty value
    as is (0, false, empty date) rather than collapsing it: that way it is rebuilt by the same
    type regardless of the type declared for the cell."""
    text = text or ''
    if xsi_type == 'xs:boolean':
        return text.strip() == 'true'
    if xsi_type == 'xs:decimal':
        s = text.strip()
        try:
            return int(s) if '.' not in s else float(s)
        except ValueError:
            return s
    return text


def int_of(node, default=0):
    if node is not None and node.text:
        return int(node.text)
    return default


# Custom JSON serializer - compact, 2-space indent, primitive arrays inline.
# Unlike ConvertTo-Json (PS5.1):
#   - does not align object keys to the longest one
#   - does not unfold primitive arrays onto separate lines
#   - Cyrillic in UTF-8 (without \uXXXX escapes)
def convert_string_to_json_literal(s):
    if s is None:
        return 'null'
    out = ['"']
    for ch in s:
        code = ord(ch)
        if code == 0x22:
            out.append('\\"')
        elif code == 0x5C:
            out.append('\\\\')
        elif code == 0x08:
            out.append('\\b')
        elif code == 0x09:
            out.append('\\t')
        elif code == 0x0A:
            out.append('\\n')
        elif code == 0x0C:
            out.append('\\f')
        elif code == 0x0D:
            out.append('\\r')
        elif code < 0x20:
            out.append('\\u%04x' % code)
        else:
            out.append(ch)
    out.append('"')
    return ''.join(out)


def _fmt_number(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        # Invariant culture: '.' decimal sep
        if v == int(v):
            # Preserve float-ness: 5.0 → "5"
            # String representation under invariant culture: 5.0 -> "5"
            return str(int(v))
        return repr(v)
    return str(v)


def try_inline_json(obj):
    if obj is None:
        return 'null'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, str):
        return convert_string_to_json_literal(obj)
    if isinstance(obj, (int, float)):
        return _fmt_number(obj)
    if isinstance(obj, dict):
        if len(obj) == 0:
            return '{}'
        parts = []
        for k, v in obj.items():
            vs = try_inline_json(v)
            if vs is None:
                return None
            parts.append(convert_string_to_json_literal(str(k)) + ': ' + vs)
        return '{ ' + ', '.join(parts) + ' }'
    if isinstance(obj, (list, tuple)):
        if len(obj) == 0:
            return '[]'
        parts = []
        for it in obj:
            vs = try_inline_json(it)
            if vs is None:
                return None
            parts.append(vs)
        return '[' + ', '.join(parts) + ']'
    return None


def convert_to_compact_json(obj, depth=0, indent_unit='  ', line_limit=400):
    indent = indent_unit * depth
    child_indent = indent_unit * (depth + 1)

    if obj is None:
        return 'null'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, str):
        return convert_string_to_json_literal(obj)
    if isinstance(obj, (int, float)):
        return _fmt_number(obj)

    # Try inline for objects and arrays with objects - if it fits in lineLimit given the current indent.
    is_container = isinstance(obj, (dict, list, tuple))
    if is_container:
        inline_attempt = try_inline_json(obj)
        if inline_attempt is not None and (len(indent) + len(inline_attempt)) <= line_limit:
            return inline_attempt

    if isinstance(obj, dict):
        if len(obj) == 0:
            return '{}'
        parts = []
        for k, v in obj.items():
            val = convert_to_compact_json(v, depth + 1, indent_unit, line_limit)
            parts.append(child_indent + convert_string_to_json_literal(str(k)) + ': ' + val)
        return "{\n" + ",\n".join(parts) + "\n" + indent + "}"
    if isinstance(obj, (list, tuple)):
        if len(obj) == 0:
            return '[]'
        parts = [child_indent + convert_to_compact_json(it, depth + 1, indent_unit, line_limit) for it in obj]
        return "[\n" + ",\n".join(parts) + "\n" + indent + "]"
    return convert_string_to_json_literal(str(obj))


# --- Main ---

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Decompile 1C spreadsheet to JSON", allow_abbrev=False)
    parser.add_argument("-TemplatePath", "-Path", required=True, help="Path to Template.xml")
    parser.add_argument("-OutputPath", default=None, help="Output JSON path (stdout if omitted)")
    args = ci_parse_args(parser)

    template_path = args.TemplatePath
    output_path = args.OutputPath

    # --- 1. Load and parse XML ---

    if not os.path.isfile(template_path):
        print(f"File not found: {template_path}", file=sys.stderr)
        sys.exit(1)

    parser_xml = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(template_path, parser_xml)
    root = tree.getroot()

    # --- 2. Extract font palette ---

    raw_fonts = []
    for f_node in findall(root, "d:font"):
        raw_fonts.append({
            # A font may be a reference to a style element (style:) or a system font (sys:) -
            # then it has no attributes of its own, and without this it turned into an empty entry.
            "Ref": f_node.get("ref", ""),
            "Face": f_node.get("faceName", ""),
            "Size": to_font_size(f_node.get("height", "0")),
            "Bold": f_node.get("bold") == "true",
            "Italic": f_node.get("italic") == "true",
            "Underline": f_node.get("underline") == "true",
            "Strikeout": f_node.get("strikeout") == "true",
        })

    # --- 3. Extract line palette ---

    raw_lines = []
    for l_node in findall(root, "d:line"):
        st = find(l_node, "v8ui:style")
        raw_lines.append({
            "Width": int(l_node.get("width", "0")),
            "Gap": l_node.get("gap", "false"),
            "Style": (text_of(st) or "Solid") if st is not None else "Solid",
        })

    # --- 4. Extract format palette ---

    # Read the format in full - "tag -> value", not a selection of nine fields. Take the value
    # type from the shared table, the same one the compiler uses.
    kinds = format_tag_kind()
    ml_tags = format_ml_tags()

    raw_formats = []
    for fmt_node in findall(root, "d:format"):
        # Compatibility with the previous fields: they are used by column width, row height and
        # the fill flag - they are not part of the style.
        fmt = {
            "FontIdx": -1, "Width": 0, "Height": 0, "FillType": "", "Props": OrderedDict(),
        }
        for child in fmt_node:
            tag = etree.QName(child).localname
            if tag in ml_tags:
                item = find(child, "v8:item/v8:content")
                val = text_of(item) if item is not None else None
                if val:
                    fmt["Props"][tag] = val
                continue
            # Cell value type is the only tag with its OWN structure: parse it before
            # both cutoffs below. An empty <valueType/> is also meaningful - it is "contains value"
            # with no type specified.
            if tag == "valueType":
                fmt["Props"][tag] = value_type_to_dsl(child)
                continue
            # A nested element is not a scalar: .text would give emptiness, so collect
            # the whole text of the subtree (concatenation), otherwise the content would be lost.
            if len(child):
                continue
            val = (child.text or "").strip()
            if not val:
                continue
            if kinds.get(tag) == "color":
                val = color_to_dsl(child, val)
            fmt["Props"][tag] = val

        if "font" in fmt["Props"]:
            fmt["FontIdx"] = int(fmt["Props"]["font"])
        if "width" in fmt["Props"]:
            fmt["Width"] = int(fmt["Props"]["width"])
        if "height" in fmt["Props"]:
            fmt["Height"] = int(fmt["Props"]["height"])
        if "fillType" in fmt["Props"]:
            fmt["FillType"] = fmt["Props"]["fillType"]

        raw_formats.append(fmt)

    def get_format(idx):
        if idx <= 0 or idx > len(raw_formats):
            return None
        return raw_formats[idx - 1]

    # --- 4-bis. Picture palette and drawings ---
    # A picture is stored as a library reference or as base64 data; references to the palette (a drawing's
    # pictureIndex, a cell's picIndex) are 1-based, while <index> itself is 0-based.
    pictures_out = OrderedDict()
    picture_key = {}
    for pic_i, pic_node in enumerate(findall(root, "d:picture"), start=1):
        inner = find(pic_node, "d:picture")
        if inner is None:
            continue
        name = f'pic{pic_i}'
        entry = OrderedDict()
        if inner.get("ref"):
            entry["ref"] = inner.get("ref")
        elif (inner.text or "").strip():
            entry["data"] = (inner.text or "").strip()
        # Transparency also exists on a referenced picture (in Accounting 8.3.27 there are 67 such entries), so
        # read it outside the branching. The transparent color pixel is a coordinate inside the picture.
        if entry and inner.get("t") is not None:
            entry["transparent"] = inner.get("t") == "true"
        if entry and inner.get("tx") is not None:
            entry["transparent"] = OrderedDict([("x", int(inner.get("tx"))),
                                                ("y", int(inner.get("ty") or 0))])
        pictures_out[name] = entry
        picture_key[pic_i] = name

    drawing_names = {}
    for ni_node in findall(root, "d:namedItem"):
        if (ni_node.get(f'{{{XSI_NS}}}type') or '') == 'NamedItemDrawing':
            drawing_names[text_of(find(ni_node, "d:drawingID")) or ''] = text_of(find(ni_node, "d:name")) or ''

    drawings_out = []
    for dr_i, dr in enumerate(findall(root, "d:drawing"), start=1):
        item = OrderedDict()
        item["type"] = text_of(find(dr, "d:drawingType")) or "Picture"
        did = text_of(find(dr, "d:id")) or str(dr_i)
        if did != str(dr_i):
            item["id"] = int(did)
        zorder = text_of(find(dr, "d:zOrder")) or str(dr_i)
        if zorder != str(dr_i):
            item["zOrder"] = int(zorder)
        if did in drawing_names:
            item["name"] = drawing_names[did]
        pic_ref = text_of(find(dr, "d:pictureIndex"))
        if pic_ref and int(pic_ref) in picture_key:
            item["picture"] = picture_key[int(pic_ref)]
        detail = text_of(find(dr, "d:detailParameter"))
        if detail:
            item["detail"] = detail
        t_el = find(dr, "d:text")
        if t_el is not None:
            by_lang = OrderedDict()
            for it in findall(t_el, "v8:item"):
                by_lang[text_of(find(it, "v8:lang")) or ''] = text_of(find(it, "v8:content")) or ''
            item["text"] = by_lang
        # Formatting is parsed later: the line must be expanded into a description, and the helper
        # for that appears together with the style palette.
        fmt_idx = int_of(find(dr, "d:formatIndex"))

        def anchor(prefix, off_row, off_col):
            return OrderedDict([("row", int_of(find(dr, f'd:{prefix}Row')) + 1),
                                ("col", int_of(find(dr, f'd:{prefix}Column')) + 1),
                                ("dy", int_of(find(dr, f'd:{off_row}'))),
                                ("dx", int_of(find(dr, f'd:{off_col}')))])
        item["begin"] = anchor("begin", "beginRowOffset", "beginColumnOffset")
        item["end"] = anchor("end", "endRowOffset", "endColumnOffset")
        psize = text_of(find(dr, "d:pictureSize"))
        if psize and psize != "Stretch":
            item["pictureSize"] = psize
        item["_fmt"] = fmt_idx
        drawings_out.append(item)

    # --- 4a. Headers/footers and print settings ---
    # A header/footer slot is arranged like a cell: a format reference plus text. Read the output flag and the start
    # page only from the entry that has <height>: the palette is deduplicated, and a header/footer without
    # its own settings references another entry where <width> is the column width, not the page number.
    def read_header_part(suffix):
        slots = OrderedDict()
        fmt_idx = None
        for slot in ('left', 'center', 'right'):
            el = find(root, f'd:{slot}{suffix}')
            if el is None:
                continue
            if fmt_idx is None:
                fmt_idx = int_of(find(el, 'd:f'))
            for text_tag in ('tl', 'tfl'):
                t = find(el, 'd:' + text_tag)
                if t is None:
                    continue
                by_lang = OrderedDict()
                for it in findall(t, 'v8:item'):
                    lang = text_of(find(it, 'v8:lang')) or ''
                    by_lang[lang] = text_of(find(it, 'v8:content')) or ''
                value = get_dsl_text(by_lang)
                slots[slot] = OrderedDict([('formatted', value)]) if text_tag == 'tfl' else value
                break
        if not slots and fmt_idx is None:
            return None
        fmt = get_format(fmt_idx) if fmt_idx else None
        if not fmt:
            return slots
        head = OrderedDict()
        if fmt["FontIdx"] >= 0:
            head["font"] = font_names.get(fmt["FontIdx"], "default")
        props = fmt["Props"]
        if 'height' in props:
            if str(props['height']) == '-1':
                head["show"] = False
            width = int(props.get('width', 1))
            if width != 1:
                head["startPage"] = width
        if 'verticalAlignment' in props:
            head["verticalAlignment"] = props['verticalAlignment']
        head.update(slots)
        return head

    print_settings = None
    ps_node = find(root, 'd:printSettings')
    if ps_node is not None:
        print_settings = OrderedDict()
        for c in ps_node:
            name = etree.QName(c).localname
            v = (c.text or '').strip()
            if v == 'true':
                print_settings[name] = True
            elif v == 'false':
                print_settings[name] = False
            else:
                try:
                    print_settings[name] = int(v)
                except ValueError:
                    print_settings[name] = v

    # --- 4b. Row and column groupings ---
    # The platform stores them as a flat list of ranges, parent before children. Do not read the level count
    # (<vgLevels>): it is derived from nesting - it matched in all 1797 templates.
    def read_groups(tag, axis):
        out = []
        for g in findall(root, "d:" + tag):
            b = int_of(find(g, "d:b"))
            e_node = find(g, "d:e")
            e = int_of(e_node, b) if e_node is not None else b
            item = OrderedDict()
            item[axis] = (b + 1) if e == b else f'{b + 1}-{e + 1}'
            t_el = find(g, "d:t")
            if t_el is not None:
                by_lang = OrderedDict()
                for it in findall(t_el, "v8:item"):
                    lang = text_of(find(it, "v8:lang")) or ''
                    by_lang[lang] = text_of(find(it, "v8:content")) or ''
                if by_lang:
                    item["name"] = by_lang
            if (text_of(find(g, "d:o")) or 'true').strip() == 'false':
                item["collapsed"] = True
            place = text_of(find(g, "d:g"))
            if place:
                item["titleLocation"] = place.strip().lower()
            out.append(item)
        return out

    row_groups = read_groups("vg", "rows")
    col_groups = read_groups("hg", "cols")

    # --- 5. Extract columns and default width ---

    # Column layout ("individual column width" for a row group) is the <columns> element.
    # There may be several of them: the layout WITHOUT <id> is the default (exactly one in every template of the corpus),
    # the rest are addressed by the GUID from <id>, which rows (<row><columnsID>) and
    # areas (<area><columnsID>) reference. Previously only the first <columns> was read - hence widths
    # were lost and columns: 0 appeared.

    default_fmt_idx = 0
    n = find(root, "d:defaultFormatIndex")
    if n is not None and n.text:
        default_fmt_idx = int(n.text)

    default_width = 10
    if default_fmt_idx > 0:
        def_fmt = get_format(default_fmt_idx)
        if def_fmt and def_fmt["Width"] > 0:
            default_width = def_fmt["Width"]

    def read_column_set(node):
        by_idx = {}
        for ci in findall(node, "d:columnsItem"):
            by_idx[int_of(find(ci, "d:index"))] = int_of(find(ci, "d:column/d:formatIndex"))
        # Width map (1-based column -> width), only those different from the default.
        widths = OrderedDict()
        for col0 in sorted(by_idx.keys()):
            fmt = get_format(by_idx[col0])
            if fmt and fmt["Width"] > 0 and fmt["Width"] != default_width:
                widths[str(col0 + 1)] = fmt["Width"]
        id_node = find(node, "d:id")
        size_node = find(node, "d:size")
        return {
            "Id": (text_of(id_node) or None) if id_node is not None else None,
            "Size": int_of(size_node) if size_node is not None else 0,
            "Widths": widths,
            # A column format carries more than width - the style name is substituted below, once styles
            # are named.
            "FmtIdx": {str(c0 + 1): by_idx[c0] for c0 in sorted(by_idx.keys())},
        }

    column_sets = [read_column_set(cn) for cn in findall(root, "d:columns")]

    default_set = next((c for c in column_sets if not c["Id"]), None)
    if default_set is None and column_sets:
        default_set = column_sets[0]
    total_columns = default_set["Size"] if default_set else 0
    col_width_map = default_set["Widths"] if default_set else OrderedDict()

    # --- 6. Extract merges ---

    merge_map = {}
    for m_node in findall(root, "d:merge"):
        r = int_of(find(m_node, "d:r"))
        c = int_of(find(m_node, "d:c"))
        w = int_of(find(m_node, "d:w"))
        h_node = find(m_node, "d:h")
        h = int_of(h_node) if h_node is not None else 0
        merge_map[f"{r},{c}"] = {"W": w, "H": h}

    # --- 7. Extract named items ---

    # Capture areas of ALL types. Previously there was `if area_type != "Rows": continue`,
    # which lost Rectangle and Columns - and they exist in 61% of the corpus templates.
    named_areas = []
    for ni_node in findall(root, "d:namedItem"):
        xsi_type = ni_node.get(f"{{{XSI_NS}}}type", "")
        if xsi_type != "NamedItemCells":
            continue

        area_node = find(ni_node, "d:area")
        if area_node is None:
            continue

        def coord(tag, node=area_node):
            n = find(node, "d:" + tag)
            return int_of(n) if n is not None else -1

        named_areas.append({
            # Order in the source is an explicit sort key: sorted is stable here, and
            # sort explicitly, otherwise the order would be unstable.
            "Ord": len(named_areas),
            "Name": text_of(find(ni_node, "d:name")) or "",
            "Type": text_of(find(area_node, "d:type")) or "",
            "BeginRow": coord("beginRow"),
            "EndRow": coord("endRow"),
            "BeginCol": coord("beginColumn"),
            "EndCol": coord("endColumn"),
            # Binding of the area to the column layout: 913 483 rectangular areas of the corpus
            # have it, and it is not always derived from the covered rows.
            "ColumnsId": text_of(find(area_node, "d:columnsID")) or "",
        })

    # --- 8. Extract rows ---

    row_data = {}
    # Languages in which the template has any text at all. Order - first appearance.
    doc_langs = OrderedDict()
    for ri_node in findall(root, "d:rowsItem"):
        row_idx = int_of(find(ri_node, "d:index"))
        row_node = find(ri_node, "d:row")

        index_to = row_idx
        it_node = find(ri_node, "d:indexTo")
        if it_node is not None and it_node.text:
            index_to = int(it_node.text)

        row_fmt_idx = 0
        fmt_node = find(row_node, "d:formatIndex")
        if fmt_node is not None and fmt_node.text:
            row_fmt_idx = int(fmt_node.text)

        is_empty = False
        empty_node = find(row_node, "d:empty")
        if empty_node is not None and empty_node.text == "true":
            is_empty = True

        cells = []
        if not is_empty:
            col = -1
            for c_group in findall(row_node, "d:c"):
                i_node = find(c_group, "d:i")
                if i_node is not None and i_node.text:
                    col = int(i_node.text)
                else:
                    col += 1

                c_content = find(c_group, "d:c")
                if c_content is None:
                    continue

                cell_fmt_idx = 0
                f_node = find(c_content, "d:f")
                if f_node is not None and f_node.text:
                    cell_fmt_idx = int(f_node.text)

                param = None
                p_node = find(c_content, "d:parameter")
                if p_node is not None and p_node.text:
                    param = p_node.text

                detail = None
                d_node = find(c_content, "d:detailParameter")
                if d_node is not None and d_node.text:
                    detail = d_node.text

                # The parameter name used to substitute a picture. The picture itself sits in
                # the formatting (picIndex), so this tag lives separately from it.
                pic_param = None
                pp_node = find(c_content, "d:pictureParameter")
                if pp_node is not None and pp_node.text:
                    pic_param = pp_node.text

                # Input field cell value. The value type is its own and is not derived from the declared one,
                # so read it too: an empty value collapses to "", the rest travel as is.
                value = None
                v_node = find(c_content, "d:v")
                if v_node is not None:
                    value = (v_node.get(f'{{{XSI_NS}}}type') or '', (v_node.text or ''))

                # Cell note. Do not read anchors as data: the end is the coordinates of the cell
                # itself, the beginning is 1/1 in 1085 notes of the 1087 in the corpus; the rest is authored.
                note = None
                note_node = find(c_content, "d:note")
                if note_node is not None:
                    g = {etree.QName(ch).localname: ch for ch in note_node}
                    def _txt(name, default=''):
                        el = g.get(name)
                        return (el.text or default).strip() if el is not None else default
                    note_text = OrderedDict()
                    t_el = g.get('text')
                    if t_el is not None:
                        for it in findall(t_el, "v8:item"):
                            lang = text_of(find(it, "v8:lang")) or ''
                            note_text[lang] = text_of(find(it, "v8:content")) or ''
                    note = {
                        "FormatIdx": int(_txt('formatIndex', '0') or 0),
                        "Text": note_text,
                        "AutoSize": _txt('autoSize', 'true') == 'true',
                        "Box": OrderedDict([
                            ("top", int(_txt('beginRowOffset', '0') or 0)),
                            ("left", int(_txt('beginColumnOffset', '0') or 0)),
                            ("bottom", int(_txt('endRowOffset', '0') or 0)),
                            ("right", int(_txt('endColumnOffset', '0') or 0)),
                        ]),
                        "AnchorRow": int(_txt('beginRow', '1') or 1),
                        "AnchorCol": int(_txt('beginColumn', '1') or 1),
                    }

                # Control settings - serialized base64 at the cell itself.
                # Do not parse the structure, carry it verbatim.
                control = None
                ctl_node = find(c_content, "d:control")
                if ctl_node is not None and ctl_node.text:
                    # Normalize line breaks inside the blob to LF: XML parsers normalize them
                    # differently, and without this ports produced different JSON on the same file.
                    control = ctl_node.text.replace('\r\n', '\n')

                # The platform stores cell text as one element per language. Previously the FIRST was taken, and everything
                # else was lost - in the ERP corpus 98% of templates hold text both under ru and under en.
                # Here "language -> text" is collected as is; it will collapse into a string later, once
                # the language set of the whole template is known (get_dsl_text).
                text = None
                has_text = False
                # An empty <tl/> is a separate state: the text tag exists, but has no languages. Without
                # this branch such a cell lost text altogether (1 of 15 cells with a text tag).
                tl_node = find(c_content, "d:tl")
                items = findall(c_content, "d:tl/v8:item")
                if tl_node is not None and not items:
                    text = OrderedDict()
                    has_text = True
                elif items:
                    by_lang = OrderedDict()
                    for it in items:
                        lang_node = find(it, "v8:lang")
                        content_node = find(it, "v8:content")
                        lang = (text_of(lang_node) or '') if lang_node is not None else ''
                        by_lang[lang] = (text_of(content_node) or '') if content_node is not None else ''
                        doc_langs[lang] = True
                    text = by_lang
                    # A single empty Russian text is not considered content - such a cell
                    # goes into the row fillers.
                    has_text = not (len(by_lang) == 1 and by_lang.get('ru') == '')

                cells.append({
                    "Col": col,
                    "FormatIdx": cell_fmt_idx,
                    "Param": param,
                    "Detail": detail,
                    "PictureParam": pic_param,
                    "Value": value,
                    "Control": control,
                    "Note": note,
                    "Text": text,
                    "HasText": has_text,
                })

        # Row reference to the column layout; empty = default layout.
        cid_node = find(row_node, "d:columnsID")
        row_columns_id = text_of(cid_node) if cid_node is not None else None

        for r in range(row_idx, index_to + 1):
            row_data[r] = {
                "FormatIdx": row_fmt_idx,
                "Cells": cells,
                "Empty": is_empty,
                "ColumnsId": row_columns_id,
            }

    # Template text languages and languages declared in the configuration are different things: in standard ones they
    # do not match. Write text as a string when it is the same across the WHOLE language set of the template; otherwise
    # as an object.
    text_languages = list(doc_langs.keys())

    def get_dsl_text(by_lang):
        if not isinstance(by_lang, dict):
            return by_lang
        # Empty text (<tl/>) is written to DSL as an empty string - the same form as
        # the authored one. Without this branch a template where there is NO OTHER text at all returned null,
        # and a cell with empty text lost its content.
        if not by_lang:
            return ''
        if len(by_lang) != len(text_languages):
            return by_lang
        common = None
        for lang in text_languages:
            if lang not in by_lang:
                return by_lang
            if common is None:
                common = by_lang[lang]
            elif by_lang[lang] != common:
                return by_lang
        return common

    # --- 9. Build style key (ignoring fillType) ---

    # Format properties that are NOT style: width belongs to the column, height to
    # the row, the fill type is derived from what the cell content is set by.
    # containsValue/valueType/controlType are properties of the cell VALUE, not of formatting: style is
    # shared by many cells, while they are individual. The compiler does not know such keys, so
    # in DSL they were pure noise.
    NON_STYLE_TAGS = ("width", "height", "fillType", "font",
                      "containsValue", "valueType", "controlType",
                      # Drawing line and its sides are properties of the drawing, not of shared formatting:
                      # in the corpus all 2 135 entries with them belong only to drawings.
                      "drawingBorder", "drawingHaveLeftBorder", "drawingHaveTopBorder",
                      "drawingHaveRightBorder", "drawingHaveBottomBorder")
    BORDER_TAGS = ("border", "leftBorder", "topBorder", "rightBorder", "bottomBorder")

    def line_to_dsl(idx):
        """Expand a palette reference into a line description. Width 1 is implied,
        so an ordinary line is written simply as the style name."""
        i = int(idx)
        if i < 0 or i >= len(raw_lines):
            return "Solid"
        ln = raw_lines[i]
        out = OrderedDict()
        out["style"] = ln["Style"]
        if ln["Width"] != 1:
            out["width"] = ln["Width"]
        if ln["Gap"] == "true":
            out["gap"] = True
        if len(out) == 1:
            return out["style"]
        return out

    def style_props(fmt):
        """Format properties that go into the style - in canonical tag order."""
        if not fmt:
            return OrderedDict()
        out = OrderedDict()
        for tag, val in fmt["Props"].items():
            if tag in NON_STYLE_TAGS:
                continue
            if tag in BORDER_TAGS:
                out[tag] = line_to_dsl(val)
            elif kinds.get(tag) == "bool":
                out[tag] = (val == "true")
            elif kinds.get(tag) == "int":
                out[tag] = int(val)
            else:
                out[tag] = val
        return out

    def get_style_key(fmt):
        if not fmt:
            return "empty"
        # "no font" and "font with index 0" are different formats: font zero is not at all
        # obliged to be regular, in a template it may be italic or bold.
        parts = ["f=" + (str(fmt["FontIdx"]) if fmt["FontIdx"] >= 0 else "none")]
        for tag, val in style_props(fmt).items():
            parts.append(f"{tag}={val}")
        return "|".join(parts)

    # --- 10. Name fonts ---

    font_names = {}
    font_defs = OrderedDict()

    if len(raw_fonts) > 0:
        font_names[0] = "default"
        font_defs["default"] = raw_fonts[0]

    def get_font_key(f):
        # Distinguish a reference by the reference itself: such a font has no attributes of its own,
        # and without this two DIFFERENT references collapsed into one as "empty".
        if f.get("Ref"):
            return "ref=" + f["Ref"]
        return f"{f['Face']}|{f['Size']}|{f['Bold']}|{f['Italic']}|{f['Underline']}|{f['Strikeout']}"

    font_key_map = {}
    if len(raw_fonts) > 0:
        font_key_map[get_font_key(raw_fonts[0])] = "default"

    for i in range(1, len(raw_fonts)):
        f = raw_fonts[i]
        df = raw_fonts[0]

        # Dedup: if identical font already named, reuse
        f_key = get_font_key(f)
        if f_key in font_key_map:
            font_names[i] = font_key_map[f_key]
            continue

        name = None

        if f.get("Ref"):
            # A name from the reference: nothing more readable than the reference itself can be devised.
            name = f["Ref"].split(":", 1)[1].lower()
        elif f["Face"] == df["Face"] and f["Size"] == df["Size"]:
            if f["Bold"] and not df["Bold"] and not f["Italic"] and not f["Underline"] and not f["Strikeout"]:
                name = "bold"
            elif f["Italic"] and not df["Italic"] and not f["Bold"]:
                name = "italic"
            elif f["Underline"] and not df["Underline"] and not f["Bold"] and not f["Italic"]:
                name = "underline"
        elif f["Face"] == df["Face"] and f["Size"] > df["Size"] and f["Bold"]:
            name = "header"
        elif f["Face"] == df["Face"] and f["Size"] < df["Size"]:
            name = "small"

        if not name:
            parts = []
            if f["Face"] and f["Face"] != df["Face"]:
                parts.append(f["Face"].lower())
            parts.append(str(f["Size"]))
            if f["Bold"]:
                parts.append("bold")
            if f["Italic"]:
                parts.append("italic")
            if f["Underline"]:
                parts.append("underline")
            if f["Strikeout"]:
                parts.append("strikeout")
            name = "-".join(parts)

        base_name = name
        suffix = 2
        while name in font_defs:
            name = f"{base_name}{suffix}"
            suffix += 1

        font_names[i] = name
        font_defs[name] = f
        font_key_map[f_key] = name

    # --- 11. Collect and name styles ---

    style_keys = OrderedDict()
    format_to_style_key = {}

    for rd in row_data.values():
        for cell in rd["Cells"]:
            fmt = get_format(cell["FormatIdx"])
            if not fmt:
                continue
            key = get_style_key(fmt)
            if key not in style_keys:
                style_keys[key] = fmt
            format_to_style_key[cell["FormatIdx"]] = key
            # The note format lives in the same palette and also deserves a name: otherwise
            # the tooltip formatting would be lost on rebuild.
            if cell.get("Note"):
                nfmt = get_format(cell["Note"]["FormatIdx"])
                if nfmt:
                    nkey = get_style_key(nfmt)
                    if nkey not in style_keys:
                        style_keys[nkey] = nfmt
                    format_to_style_key[cell["Note"]["FormatIdx"]] = nkey

    # The drawing format is another owner of a palette entry, along with a cell, row, column
    # and note: without this the drawing formatting lost its name and was cut as unused.
    for _item in drawings_out:
        _fi = _item.get("_fmt") or 0
        if not _fi:
            continue
        _fmt = get_format(_fi)
        if _fmt and (style_props(_fmt) or _fmt["FontIdx"] >= 0):
            _key = get_style_key(_fmt)
            if _key not in style_keys:
                style_keys[_key] = _fmt
            format_to_style_key[_fi] = _key

    def row_style_fmt(fmt):
        """Row formatting without its own properties: hiding goes inline to height,
        so it must not get into a named style."""
        if not fmt:
            return None
        props = style_props(fmt)
        props.pop("hidden", None)
        # Font is not included in style_props (it is addressed by name), so a row format
        # carrying ONLY a font looked empty here and was lost.
        if not props and fmt["FontIdx"] < 0:
            return None
        reduced = OrderedDict()
        for tag, raw in fmt["Props"].items():
            if tag != "hidden":
                reduced[tag] = raw
        return {"FontIdx": fmt["FontIdx"], "Width": 0, "Height": 0,
                "FillType": "", "Props": reduced}

    # A row is also a format owner: its formatting becomes a named style.
    for rd in row_data.values():
        rf = row_style_fmt(get_format(rd["FormatIdx"])) if rd["FormatIdx"] > 0 else None
        if not rf:
            continue
        key = get_style_key(rf)
        if key not in style_keys:
            style_keys[key] = rf

    # A column is the third format owner; its formatting also becomes a named style.
    for cs in column_sets:
        for fi in cs["FmtIdx"].values():
            fmt = get_format(fi)
            if not fmt or not style_props(fmt):
                continue
            key = get_style_key(fmt)
            if key not in style_keys:
                style_keys[key] = fmt
            format_to_style_key[fi] = key

    def name_style(fmt):
        """Style name - a readable label from the most noticeable properties. Completeness is not needed here:
        the key distinguishes styles, the name only helps the author navigate."""
        if not fmt:
            return "default"
        parts = []
        props = style_props(fmt)

        fi = fmt["FontIdx"]
        if fi >= 0 and font_names.get(fi, "default") != "default":
            parts.append(font_names[fi])

        if "border" in props:
            parts.append("bordered")
        else:
            sides = [s[:-6] for s in ("leftBorder", "topBorder", "rightBorder", "bottomBorder")
                     if s in props]
            if sides:
                parts.append("border-" + ",".join(sides))

        ha = props.get("horizontalAlignment")
        if ha == "Center":
            parts.append("center")
        elif ha == "Right":
            parts.append("right")
        va = props.get("verticalAlignment")
        if va == "Center":
            parts.append("vcenter")
        elif va == "Top":
            parts.append("vtop")
        if props.get("textPlacement") == "Wrap":
            parts.append("wrap")
        if "backColor" in props:
            parts.append("bg")
        if "format" in props:
            parts.append("fmt")

        if len(parts) == 0:
            # The name "default" is reserved for the style WITHOUT properties: under it the compiler
            # understands the absence of formatting, and a cell does not write such a style. A set
            # of only inconspicuous properties (indent, protection) or of a single font must
            # get its own name, otherwise it will be lost.
            has_content = bool(props) or fmt["FontIdx"] >= 0
            return "style" if has_content else "default"
        return "-".join(parts)

    style_names = OrderedDict()
    style_defs = OrderedDict()

    for key in style_keys:
        fmt = style_keys[key]
        name = name_style(fmt)

        base_name = name
        suffix = 2
        while name in style_defs:
            name = f"{base_name}{suffix}"
            suffix += 1

        style_names[key] = name

        s_def = OrderedDict()
        if fmt["FontIdx"] >= 0:
            s_def["font"] = font_names.get(fmt["FontIdx"], "default")
        s_def.update(style_props(fmt))

        style_defs[name] = s_def

    def get_style_name(fmt_idx):
        key = format_to_style_key.get(fmt_idx)
        if key and key in style_names:
            return style_names[key]
        return "default"

    def column_styles_of(cs):
        """Layout columns whose format carries more than width - "column -> style"."""
        out = OrderedDict()
        for col, fi in cs["FmtIdx"].items():
            if fi == 0:
                # The column is listed but has no format. Useless for authoring, but without
                # this the roundtrip loses the element entirely.
                out[col] = None
                continue
            fmt = get_format(fi)
            if fmt and style_props(fmt):
                out[col] = get_style_name(fi)
        return out

    def to_positional_cells(cells):
        """Positional record of the cell list: position is taken from the order, `col` is not written.
        A cell that has nothing besides text or a parameter is written as a value; span
        is expanded by ">" markers; the rest - by an object element without col. A skipped column is
        null. Choose the record that is SHORTER: previously the positional form was discarded
        as soon as the first cell was not in the first column, although one or two leading nulls
        are usually shorter than an object record with `col`."""
        if not cells:
            return cells
        out = []
        expected = 1
        for c in cells:
            col = int(c.get("col", 0))
            if col < expected:
                return cells   # overlap - cannot be expressed positionally
            while expected < col:
                out.append(None)
                expected += 1
            span = int(c.get("span", 1) or 1)
            keys = [k for k in c if k not in ("col", "span")]
            # Text is the only content: write it as a value. It is either a string or
            # an object "language -> text", and in a positional record the element IS that value.
            plain_text = len(keys) == 1 and keys[0] == "text"
            plain_param = len(keys) == 1 and keys[0] == "param"
            if plain_text:
                out.append(c["text"])
            elif plain_param:
                out.append("{%s}" % c["param"])
            else:
                obj = OrderedDict((k, v) for k, v in c.items() if k != "col")
                out.append(obj)
            # expand span with markers - except for an object element, it carries span itself.
            if (plain_text or plain_param) and span > 1:
                out.extend([">"] * (span - 1))
            expected = col + span
        # The positional form is valuable for its compactness: if it is longer than the object one, there is no point in it.
        a, b = try_inline_json(out), try_inline_json(cells)
        if a is not None and b is not None and len(a) > len(b):
            return cells
        return out

    # --- 12. Build areas ---

    # The grid is cut into blocks: non-overlapping Rows areas define boundaries, rows outside
    # them become UNNAMED blocks. Previously rows outside areas were simply lost - in the corpus
    # such holes exist in 34% of templates, and 21% of templates have no Rows areas at all.
    # Everything that is not expressible as a block (non-Rows areas and overlapping Rows) goes to namedAreas
    # by coordinates. The rule is deterministic - otherwise the roundtrip would break.

    max_row_idx = max(row_data.keys()) if row_data else -1

    def row_columns_id(r):
        rd = row_data.get(r)
        return rd["ColumnsId"] if rd else None

    def uniform_column_set(frm, to):
        """An area is suitable as a range area only if all its rows have ONE
        layout: otherwise it would have to be cut, and a name must not be cut."""
        first = row_columns_id(frm)
        return all(row_columns_id(r) == first for r in range(frm + 1, to + 1))

    block_areas = []
    overlay_areas = []
    claimed = set()
    for a in sorted(named_areas, key=lambda x: (x["BeginRow"], x["EndRow"], x["Ord"])):
        fits = a["Type"] == "Rows" and a["BeginRow"] >= 0 and a["EndRow"] >= a["BeginRow"]
        if fits:
            for r in range(a["BeginRow"], a["EndRow"] + 1):
                if r in claimed:
                    fits = False
                    break
        if fits:
            fits = uniform_column_set(a["BeginRow"], a["EndRow"])
        if fits:
            # The block sets the layout for rows, and the area inherits the same one. When the area carries
            # a DIFFERENT binding, it cannot be expressed as a block - send it to namedAreas, where the binding is written
            # as an explicit key.
            fits = a["ColumnsId"] == (row_columns_id(a["BeginRow"]) or "")
        if fits:
            claimed.update(range(a["BeginRow"], a["EndRow"] + 1))
            block_areas.append(a)
        else:
            overlay_areas.append(a)

    def split_gap_by_column_set(frm, to):
        """Cut an unnamed gap into pieces with a single layout: the boundaries of the sets do not
        coincide with the boundaries of named areas."""
        out = []
        if to < frm:
            return out
        run_start = frm
        run_id = row_columns_id(frm)
        for r in range(frm + 1, to + 1):
            cid = row_columns_id(r)
            if cid != run_id:
                out.append({"Name": None, "BeginRow": run_start, "EndRow": r - 1, "ColumnsId": run_id})
                run_start, run_id = r, cid
        out.append({"Name": None, "BeginRow": run_start, "EndRow": to, "ColumnsId": run_id})
        return out

    # Areas in row order + unnamed gap fillers.
    blocks = []
    cursor = 0
    for a in sorted(block_areas, key=lambda x: x["BeginRow"]):
        if a["BeginRow"] > cursor:
            blocks.extend(split_gap_by_column_set(cursor, a["BeginRow"] - 1))
        blocks.append({"Name": a["Name"], "BeginRow": a["BeginRow"], "EndRow": a["EndRow"],
                       "ColumnsId": row_columns_id(a["BeginRow"])})
        cursor = a["EndRow"] + 1
    if cursor <= max_row_idx:
        blocks.extend(split_gap_by_column_set(cursor, max_row_idx))

    dsl_areas = []

    for area in blocks:
        area_rows = []

        for global_row in range(area["BeginRow"], area["EndRow"] + 1):
            rd = row_data.get(global_row)

            if not rd or rd["Empty"]:
                area_rows.append(OrderedDict())
                continue

            dsl_row = OrderedDict()

            # Format of the row itself: height and hiding are its own properties (a cell has no
            # such ones), the rest is formatting, which may also sit on cells.
            row_fmt = get_format(rd["FormatIdx"]) if rd["FormatIdx"] > 0 else None
            row_own = style_props(row_fmt) if row_fmt else OrderedDict()
            row_hidden = row_own.pop("hidden", False)
            if row_fmt and row_fmt["Height"] > 0:
                dsl_row["height"] = row_fmt["Height"]
            if row_hidden:
                dsl_row["hidden"] = True

            # Separate content cells from gap-fill cells
            content_cells = []
            gap_cells = []

            for cell in rd["Cells"]:
                # An input field cell is substantive even when it has neither text nor parameter:
                # its format sets the value. Without this such a row would go to the empty ones.
                cf = get_format(cell["FormatIdx"])
                has_value = bool(cf and cf["Props"].get("containsValue") == "true")
                # The detail itself makes a cell substantive: in the corpus 12 653 cells
                # carry only it. Without this such a cell went into fillers and was lost.
                has_content = (cell["Param"] or cell["HasText"] or has_value
                               or cell["Detail"] or cell["Note"] or cell["PictureParam"])
                has_merge = f"{global_row},{cell['Col']}" in merge_map

                if has_content or has_merge:
                    content_cells.append(cell)
                else:
                    gap_cells.append(cell)

            # Detect rowStyle
            row_style_name = None
            row_style_key = None

            if len(gap_cells) > 0:
                gap_keys = {}
                for gc in gap_cells:
                    fmt = get_format(gc["FormatIdx"])
                    gap_keys[get_style_key(fmt)] = True

                if len(gap_keys) == 1:
                    row_style_key = list(gap_keys.keys())[0]
                    if row_style_key in style_names:
                        row_style_name = style_names[row_style_key]

            # Row style and cell style are independent things: the platform often, but not always,
            # writes them the same. One key with the apply modifier covers all three cases.
            own_fmt = row_style_fmt(row_fmt)
            own_key = get_style_key(own_fmt) if own_fmt else None
            own_name = style_names.get(own_key) if own_key else None
            cells_name = row_style_name if row_style_name and row_style_name != "default" else None

            if own_name and cells_name and own_key == row_style_key:
                dsl_row["rowStyle"] = own_name
            elif own_name and not cells_name:
                dsl_row["rowStyle"] = OrderedDict([("style", own_name), ("apply", "row")])
            elif cells_name and not own_name:
                dsl_row["rowStyle"] = OrderedDict([("style", cells_name), ("apply", "cells")])
            elif own_name and cells_name:
                # Styles are different - the row gets its own, cells get theirs; the cell style is distributed below
                # per cell, so here only the row is written.
                dsl_row["rowStyle"] = OrderedDict([("style", own_name), ("apply", "row")])
                row_style_name = None
                row_style_key = None
                cells_name = None

            # Build cell list
            dsl_cells = []

            for cell in sorted(content_cells, key=lambda c: c["Col"]):
                dsl_cell = OrderedDict()
                dsl_cell["col"] = cell["Col"] + 1

                # Span/rowspan from merge
                mk = f"{global_row},{cell['Col']}"
                if mk in merge_map:
                    m = merge_map[mk]
                    if m["W"] > 0:
                        dsl_cell["span"] = m["W"] + 1
                    if m["H"] > 0:
                        dsl_cell["rowspan"] = m["H"] + 1

                # Style
                cell_fmt = get_format(cell["FormatIdx"])
                cell_style_key = get_style_key(cell_fmt)

                if row_style_key and cell_style_key == row_style_key:
                    pass  # Inherits rowStyle
                else:
                    # Write the style only when it differs from what the compiler will substitute:
                    # without a style cells have "default" anyway, so such a key is noise
                    # (56% of cells). And when the style is distributed to cells, "default" MUST be written:
                    # otherwise the cell would inherit it on rebuild.
                    # Compare against cells_name - the style that is REALLY distributed to cells. Previously
                    # row_style_name stood here, and it may equal "default": the row does not write such a style,
                    # while the cell received a meaningless key to a non-existent style.
                    sn = get_style_name(cell["FormatIdx"])
                    if sn != "default" or cells_name:
                        dsl_cell["style"] = sn

                # Value (input field cell). The property lives in the format but belongs to
                # the cell: in the corpus only <f> references such entries.
                if cell_fmt and cell_fmt["Props"].get("containsValue") == "true":
                    dsl_cell["valueType"] = cell_fmt["Props"].get("valueType", "")
                    ctl = cell_fmt["Props"].get("controlType")
                    if ctl is None:
                        # A format without <controlType> at all - this is how machine-generated
                        # templates of regulated reporting are written; the compiler will repeat that
                        # only on an explicit instruction.
                        dsl_cell["controlType"] = "none"
                    else:
                        name = VALUE_CONTROL_NAMES.get(ctl.lower(), ctl)
                        # input is the compiler default; writing it means noise on 63 629
                        # formats of the corpus.
                        if name != "input":
                            dsl_cell["controlType"] = name
                    if cell["Value"] is not None:
                        dsl_cell["value"] = value_to_dsl(*cell["Value"])
                    if cell["Control"]:
                        dsl_cell["control"] = cell["Control"]

                # Content
                fill_type = cell_fmt["FillType"] if cell_fmt else ""

                if cell["Param"]:
                    dsl_cell["param"] = cell["Param"]
                elif fill_type == "Template" and cell["HasText"]:
                    dsl_cell["template"] = get_dsl_text(cell["Text"])
                elif cell["HasText"]:
                    dsl_cell["text"] = get_dsl_text(cell["Text"])
                # The detail lives separately from the fill parameter: in the corpus 20 404 cells
                # carry it without a parameter versus 8 582 with one. While it was read only together
                # with the parameter, two thirds of the details were lost silently.
                if cell["Detail"]:
                    dsl_cell["detail"] = cell["Detail"]
                if cell["PictureParam"]:
                    dsl_cell["pictureParameter"] = cell["PictureParam"]

                if cell["Note"]:
                    n = cell["Note"]
                    dsl_note = OrderedDict()
                    dsl_note["text"] = get_dsl_text(n["Text"])
                    style_name = get_style_name(n["FormatIdx"])
                    if style_name != "default":
                        dsl_note["style"] = style_name
                    if not n["AutoSize"]:
                        dsl_note["autoSize"] = False
                    dsl_note["box"] = n["Box"]
                    if n["AnchorRow"] != 1 or n["AnchorCol"] != 1:
                        dsl_note["anchor"] = OrderedDict([("row", n["AnchorRow"]), ("col", n["AnchorCol"])])
                    dsl_cell["note"] = dsl_note

                dsl_cells.append(dsl_cell)

            if len(dsl_cells) > 0:
                dsl_row["cells"] = to_positional_cells(dsl_cells)
            # The shortest of the applicable forms: if a row has no properties of its own and the cell list
            # is positional - the row is written simply as an array, without the cells key.
            # The list is positional if the position is NOT recorded in it: no element has col.
            # The previous check looked for an element-row, so a row of only multilingual
            # texts was not recognized as positional and remained an object.
            if (len(dsl_row) == 1 and "cells" in dsl_row
                    and not any(isinstance(el, dict) and "col" in el for el in dsl_row["cells"])):
                area_rows.append(dsl_row["cells"])
            else:
                area_rows.append(dsl_row)

        # Compress consecutive empty rows ({}) into { empty = N }
        compressed_rows = []
        empty_run = 0
        for r in area_rows:
            if len(r) == 0:
                empty_run += 1
            else:
                if empty_run > 0:
                    if empty_run == 1:
                        compressed_rows.append(OrderedDict())
                    else:
                        compressed_rows.append(OrderedDict([("empty", empty_run)]))
                    empty_run = 0
                compressed_rows.append(r)
        if empty_run > 0:
            if empty_run == 1:
                compressed_rows.append(OrderedDict())
            else:
                compressed_rows.append(OrderedDict([("empty", empty_run)]))

        dsl_block = OrderedDict()
        # An area without a name is just a piece of the grid; the name key is not written for it.
        if area["Name"]:
            dsl_block["name"] = area["Name"]
        # Reference to the column layout by the name from columnSets - like a cell's style to styles.
        # Do not write the default (layout without id).
        if area.get("ColumnsId"):
            dsl_block["columnSet"] = area["ColumnsId"]
        dsl_block["rows"] = compressed_rows
        dsl_areas.append(dsl_block)

    # --- 13. Compress columnWidths ---

    compressed_widths = OrderedDict()
    if len(col_width_map) > 0:
        # Group columns by width
        width_to_cols = {}
        for col_str, width in col_width_map.items():
            width_to_cols.setdefault(width, []).append(col_str)

        for width, cols in width_to_cols.items():
            cols_sorted = sorted(cols, key=lambda x: int(x))

            ranges = []
            range_start = cols_sorted[0]
            range_prev = cols_sorted[0]

            for i in range(1, len(cols_sorted)):
                if int(cols_sorted[i]) == int(range_prev) + 1:
                    range_prev = cols_sorted[i]
                else:
                    if range_start == range_prev:
                        ranges.append(range_start)
                    else:
                        ranges.append(f"{range_start}-{range_prev}")
                    range_start = cols_sorted[i]
                    range_prev = cols_sorted[i]

            if range_start == range_prev:
                ranges.append(range_start)
            else:
                ranges.append(f"{range_start}-{range_prev}")

            for rng in ranges:
                compressed_widths[rng] = width

    # --- 14. Build fonts output ---

    fonts_out = OrderedDict()
    for name, f in font_defs.items():
        if f.get("Ref"):
            fonts_out[name] = OrderedDict([("ref", f["Ref"])])
            continue
        f_out = OrderedDict()
        f_out["face"] = f["Face"]
        f_out["size"] = f["Size"]
        if f["Bold"]:
            f_out["bold"] = True
        if f["Italic"]:
            f_out["italic"] = True
        if f["Underline"]:
            f_out["underline"] = True
        if f["Strikeout"]:
            f_out["strikeout"] = True
        fonts_out[name] = f_out

    # --- 15. Assemble result ---

    result = OrderedDict()
    result["columns"] = total_columns
    result["defaultWidth"] = default_width
    if len(compressed_widths) > 0:
        result["columnWidths"] = compressed_widths
    if default_set:
        default_col_styles = column_styles_of(default_set)
        if default_col_styles:
            result["columnStyles"] = default_col_styles
    # Declare the language set only if it differs from the compiler default (a single ru).
    if text_languages and text_languages != ['ru']:
        result["textLanguages"] = text_languages

    # Declaring the TEMPLATE languages is not the same as text languages: in almost all ERP templates
    # a single ru is declared, while text lies under both ru and en. Write only if it differs
    # from the compiler default.
    ls_node = find(root, "d:languageSettings")
    if ls_node is not None:
        langs = []
        for li in findall(ls_node, "d:languageInfo"):
            desc_node = find(li, "d:description")
            langs.append(OrderedDict([
                ("id", text_of(find(li, "d:id")) or ""),
                ("code", text_of(find(li, "d:code")) or ""),
                ("description", text_of(desc_node) or "" if desc_node is not None else ""),
            ]))
        if langs != [OrderedDict([("id", "ru"), ("code", RU_NAME), ("description", RU_NAME)])]:
            result["languages"] = langs
        cur_node = find(ls_node, "d:currentLanguage")
        cur = text_of(cur_node) if cur_node is not None else None
        if cur != "ru":
            result["currentLanguage"] = cur
        dflt = text_of(find(ls_node, "d:defaultLanguage"))
        if dflt and dflt != "ru":
            result["defaultLanguage"] = dflt

    # Remove empty "default" style
    if "default" in style_defs and len(style_defs["default"]) == 0:
        del style_defs["default"]

    # Remove unused styles
    used_styles = set()
    for a in dsl_areas:
        for r in a["rows"]:
            # A row may be an array (short form) - it has no cells key, and without this
            # branch a style used only inside such a row was cut as "unused".
            if isinstance(r, list):
                cell_list = r
            else:
                if "rowStyle" in r:
                    rs = r["rowStyle"]
                    used_styles.add(rs["style"] if isinstance(rs, dict) else rs)
                cell_list = r.get("cells") or []
            # The cell list may be positional: strings, None and markers carry no style,
            # a style exists only on an object element.
            for c in cell_list:
                if isinstance(c, dict) and "style" in c:
                    used_styles.add(c["style"])
                # The fourth format owner is the note: its style also holds a reference,
                # otherwise it is cut as unused and the reference remains dangling.
                if isinstance(c, dict) and isinstance(c.get("note"), dict) and "style" in c["note"]:
                    used_styles.add(c["note"]["style"])
    # A style exists not only on a cell and a row: a column is the third format owner. Take
    # styles FROM THE LAYOUTS THEMSELVES, not from result: columnSets gets into the result LATER than this
    # check, so a style referenced only by an additional layout
    # was cut off, while the reference to it remained dangling (5 templates of the 40 in the pilot).
    for cs in column_sets:
        for name in column_styles_of(cs).values():
            if name:
                used_styles.add(name)
    # A drawing is the fifth format owner. Its name is assigned later, when the result is assembled,
    # so here count it from the palette reference: otherwise the drawing style would be cut as
    # unused, and the reference to it would remain dangling.
    for _item in drawings_out:
        _fi = _item.get("_fmt") or 0
        if _fi:
            _name = get_style_name(_fi)
            if _name != "default":
                used_styles.add(_name)
    to_remove = [s for s in style_defs if s not in used_styles]
    for s in to_remove:
        del style_defs[s]

    result["fonts"] = fonts_out
    result["styles"] = style_defs

    # Column layouts other than the default: the key is the identifier from the template, areas reference
    # it. Content does not identify a layout (the corpus is full of sets with identical
    # content and different ids), so there is no merging by content.
    extra_sets = [c for c in column_sets if c["Id"]]
    if extra_sets:
        sets_out = OrderedDict()
        for cs in extra_sets:
            entry = OrderedDict([("columns", cs["Size"])])
            if cs["Widths"]:
                entry["columnWidths"] = cs["Widths"]
            styles_out = column_styles_of(cs)
            if styles_out:
                entry["columnStyles"] = styles_out
            sets_out[cs["Id"]] = entry
        result["columnSets"] = sets_out

    # The group name is the same multilingual string as cell text, and collapses the same way.
    for _g in row_groups + col_groups:
        if "name" in _g:
            _g["name"] = get_dsl_text(_g["name"])
    if row_groups:
        result["rowGroups"] = row_groups
    if col_groups:
        result["columnGroups"] = col_groups

    # Read here, not in section 4a: the header/footer text needs the template language set, which
    # becomes known only after rows are parsed.
    header_part = read_header_part('Header')
    footer_part = read_header_part('Footer')
    if header_part:
        result["header"] = header_part
    if footer_part:
        result["footer"] = footer_part
    if print_settings:
        result["printSettings"] = print_settings

    # Drawing formatting: the line and its sides are its own keys, the common part is a named style.
    # Set the key order here too, so that it does not depend on what was parsed earlier.
    ordered = []
    for item in drawings_out:
        fmt_idx = item.pop("_fmt", 0)
        if "text" in item:
            item["text"] = get_dsl_text(item["text"])
        line_val = None
        sides = OrderedDict()
        if fmt_idx:
            fmt = get_format(fmt_idx)
            props = fmt["Props"] if fmt else {}
            if "drawingBorder" in props:
                line_val = line_to_dsl(int(props["drawingBorder"]))
            for side in ("Left", "Top", "Right", "Bottom"):
                tag = f'drawingHave{side}Border'
                if tag in props:
                    sides[side.lower()] = props[tag] == "true"
            name = get_style_name(fmt_idx)
            if name != "default":
                item["style"] = name
        if line_val is not None:
            item["line"] = line_val
        if sides:
            item["sides"] = sides
        out_item = OrderedDict()
        for key in ("type", "id", "zOrder", "name", "picture", "detail", "text",
                    "style", "line", "sides", "begin", "end", "pictureSize"):
            if key in item:
                out_item[key] = item[key]
        ordered.append(out_item)
    drawings_out = ordered
    if pictures_out:
        result["pictures"] = pictures_out
    if drawings_out:
        result["drawings"] = drawings_out

    result["areas"] = dsl_areas

    # Named areas not expressible as a block - by coordinates. Do not write the type: it is derived
    # from the specified axes (as in ТабличныйДокумент.Область()). DSL is 1-based, XML is 0-based.
    if overlay_areas:
        na_out = []
        for a in overlay_areas:
            entry = OrderedDict([("name", a["Name"])])
            if a["BeginRow"] >= 0:
                entry["rows"] = (f'{a["BeginRow"] + 1}-{a["EndRow"] + 1}'
                                 if a["EndRow"] > a["BeginRow"] else a["BeginRow"] + 1)
            if a["BeginCol"] >= 0:
                entry["cols"] = (f'{a["BeginCol"] + 1}-{a["EndCol"] + 1}'
                                 if a["EndCol"] > a["BeginCol"] else a["BeginCol"] + 1)
            # Write the binding only when it is not derived from the covered rows.
            derived = ""
            if a["BeginRow"] >= 0:
                covered = {row_columns_id(r) or "" for r in range(a["BeginRow"], a["EndRow"] + 1)}
                if len(covered) == 1:
                    derived = covered.pop()
            if a["ColumnsId"] != derived:
                entry["columnSet"] = a["ColumnsId"]
            na_out.append(entry)
        result["namedAreas"] = na_out

    # --- 16. Convert to JSON ---

    json_str = convert_to_compact_json(result)

    # --- 17. Output ---

    if output_path:
        abs_path = os.path.join(os.getcwd(), output_path) if not os.path.isabs(output_path) else output_path
        with open(abs_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(json_str)
        print(f"[OK] Decompiled: {output_path}")
    else:
        print(json_str)

    print(f"     Areas: {len(named_areas)}, Rows: {len(row_data)}, Columns: {total_columns}", file=sys.stderr)
    print(f"     Fonts: {len(font_defs)}, Styles: {len(style_defs)}, Merges: {len(merge_map)}", file=sys.stderr)


if __name__ == "__main__":
    main()
