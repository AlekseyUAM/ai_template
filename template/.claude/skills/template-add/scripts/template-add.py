#!/usr/bin/env python
# template-add v1.27 - Add template to 1C object (+write_xml_file/write_utf8_bom: common write reference)
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills

import argparse
import json
import os
import re
import sys
import uuid

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
    # choices - mirror of [ValidateSet]; canonicalize BEFORE parsing, otherwise argparse rejects the case
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


NSMAP = {"md": "http://v8.1c.ru/8.3/MDClasses"}


# ============================================================
# Support guard (Ext/ParentConfigurations.bin) — see docs/1c-support-state-spec.md
# Blocks edits of vendor objects "на замке" / read-only configs. Trigger = bin
# present; reaction from .v8-project.json editingAllowedCheck (deny|warn|off,
# default deny). Never throws (except sys.exit on deny) — errors degrade to allow.
# ============================================================

def _sg_root_uuid(xml_path):
    if not os.path.isfile(xml_path):
        return None
    try:
        mx = etree.parse(xml_path).getroot()
        for child in mx:
            if isinstance(child.tag, str) and child.get("uuid"):
                return child.get("uuid")
    except Exception:
        return None
    return None


def _sg_is_external_root(xml_path):
    if not os.path.isfile(xml_path):
        return False
    try:
        mx = etree.parse(xml_path).getroot()
        for child in mx:
            if isinstance(child.tag, str):
                return child.tag.split("}")[-1] in ("ExternalDataProcessor", "ExternalReport")
    except Exception:
        return False
    return False

def _sg_find_v8project(start_dir):
    d = start_dir
    for _ in range(20):
        if not d:
            break
        pj = os.path.join(d, ".v8-project.json")
        if os.path.isfile(pj):
            return pj
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _sg_get_edit_mode(cfg_dir):
    try:
        pj = _sg_find_v8project(os.getcwd()) or _sg_find_v8project(cfg_dir)
        if not pj:
            return "deny"
        proj = json.loads(open(pj, encoding="utf-8-sig").read())
        cfg_full = os.path.normcase(os.path.abspath(cfg_dir)).rstrip("\\/")
        for db in proj.get("databases", []):
            src = db.get("configSrc")
            if src:
                src_full = os.path.normcase(os.path.abspath(src)).rstrip("\\/")
                if cfg_full == src_full or cfg_full.startswith(src_full + os.sep):
                    if db.get("editingAllowedCheck"):
                        return db["editingAllowedCheck"]
        if proj.get("editingAllowedCheck"):
            return proj["editingAllowedCheck"]
        return "deny"
    except Exception:
        return "deny"


def assert_edit_allowed(target_path, require):
    try:
        rp = os.path.abspath(target_path)
        # Autonomous external object (EPF/ERF): never part of a config on support (issue #39).
        if _sg_is_external_root(rp):
            return
        elem_uuid = _sg_root_uuid(rp)
        cfg_dir = None
        bin_path = None
        d = rp if os.path.isdir(rp) else os.path.dirname(rp)
        for _ in range(12):
            if not d:
                break
            if _sg_is_external_root(d + ".xml"):
                return
            if not elem_uuid:
                elem_uuid = _sg_root_uuid(d + ".xml")
            if not cfg_dir:
                cand = os.path.join(d, "Ext", "ParentConfigurations.bin")
                if os.path.exists(cand) or os.path.exists(os.path.join(d, "Configuration.xml")):
                    cfg_dir = d
                    bin_path = cand
            if elem_uuid and cfg_dir:
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        if not elem_uuid and cfg_dir:
            elem_uuid = _sg_root_uuid(os.path.join(cfg_dir, "Configuration.xml"))
        if not bin_path or not os.path.exists(bin_path):
            return
        data = open(bin_path, "rb").read()
        if len(data) <= 32:
            return
        if data[:3] == b"\xef\xbb\xbf":
            data = data[3:]
        text = data.decode("utf-8", "replace")
        h = re.match(r"\{6,(\d+),(\d+),", text)
        if not h:
            return
        g = int(h.group(1))
        k = int(h.group(2))
        if k == 0:
            return
        best = None
        if elem_uuid:
            for m in re.finditer(r"([0-2]),0," + re.escape(elem_uuid.lower()), text):
                f1 = int(m.group(1))
                if best is None or f1 < best:
                    best = f1
        blocked = False
        code = ""
        reason = ""
        if g == 1:
            blocked = True
            code = "capability-off"
            reason = "возможность изменения конфигурации выключена (вся конфигурация read-only)"
        elif require == "removed":
            if best is not None and best != 2:
                blocked = True
                code = "not-removed"
                reason = "объект не снят с поддержки — удаление сломает обновления"
        else:
            if best is not None and best == 0:
                blocked = True
                code = "locked"
                reason = "объект на замке — редактирование сломает обновления"
        if not blocked:
            return
        mode = _sg_get_edit_mode(cfg_dir)
        if mode == "off":
            return
        if mode == "warn":
            sys.stderr.write(f"[support-guard] ПРЕДУПРЕЖДЕНИЕ: {reason}. Цель: {rp}\n")
            return
        head = "[support-guard] Редактирование отклонено: это объект типовой конфигурации на поддержке поставщика, прямое редактирование молча сломает будущие обновления."
        cfe = "Рекомендуемый путь: внести доработку в расширение (навыки cfe-borrow / cfe-patch-method) — состояние поддержки менять не нужно, обновления вендора сохраняются."
        off_note = "Снять проверку для этой базы: editingAllowedCheck = warn|off в .v8-project.json."
        if code == "capability-off":
            state = f"Состояние: у всей конфигурации выключена возможность изменения (режим read-only «из коробки») — поэтому объект «{rp}» редактировать нельзя."
            fix = (
                "Либо снять защиту явно (навык support-edit, два шага):\n"
                f'  1. support-edit -Path "{cfg_dir}" -Capability on — включить возможность изменения (объекты пока остаются на замке);\n'
                f'  2. support-edit -Path "{rp}" -Set editable — открыть этот объект для редактирования.\n'
                "  Изменение применяется в базу полной загрузкой выгрузки и обходит механизм обновлений вендора."
            )
        elif code == "not-removed":
            state = f"Состояние: объект «{rp}» на поддержке (не снят с поддержки) — его удаление разорвёт обновления вендора."
            fix = (
                "Либо сначала снять объект с поддержки, затем удалять:\n"
                f'  support-edit -Path "{rp}" -Set off-support — объект уходит из-под обновлений, после этого удаление безопасно.'
            )
        else:
            state = f"Состояние: объект «{rp}» на замке (возможность изменения конфигурации включена, но сам объект не редактируется)."
            fix = (
                "Либо разрешить редактирование этого объекта (навык support-edit, выбрать одно):\n"
                f'  support-edit -Path "{rp}" -Set editable — редактировать и дальше получать обновления вендора (возможны конфликты слияния);\n'
                f'  support-edit -Path "{rp}" -Set off-support — снять с поддержки: обновления по объекту больше не приходят.'
            )
        sys.stderr.write(head + "\n" + state + "\n" + cfe + "\n" + fix + "\n" + off_note + "\n")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        return

TYPE_MAP = {
    "HTML": {"TemplateType": "HTMLDocument", "Ext": ".xml"},
    "Text": {"TemplateType": "TextDocument", "Ext": ".txt"},
    "SpreadsheetDocument": {"TemplateType": "SpreadsheetDocument", "Ext": ".xml"},
    "BinaryData": {"TemplateType": "BinaryData", "Ext": ".bin"},
    "DataCompositionSchema": {"TemplateType": "DataCompositionSchema", "Ext": ".xml"},
}


def _detect_xml_style(path):
    """Style of the existing file for round-trip saving: BOM / EOL / encoding case /
    final newline. None -> file is new (keep current behavior)."""
    try:
        raw = open(path, "rb").read()
    except OSError:
        return None
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    crlf = b"\r\n" in body
    m = re.search(rb'encoding="([^"]+)"', body[:200])
    enc = m.group(1).decode("ascii") if m else "utf-8"
    final_nl = body.endswith(b"\n")
    return {"bom": bom, "crlf": crlf, "enc": enc, "final_nl": final_nl}


def _finalize_xml_bytes(xml_bytes, style):
    """Bring bytes to the original style; for a NEW file (style is None) - to the
    Configurator dump canon: encoding="UTF-8", CRLF in separators, no final newline."""
    enc_decl = style["enc"] if style else "UTF-8"
    xml_bytes = xml_bytes.replace(
        b"<?xml version='1.0' encoding='UTF-8'?>",
        b'<?xml version="1.0" encoding="' + enc_decl.encode("ascii") + b'"?>')
    # Canonicalize line breaks to LF (removes &#13; from \r in tails)
    xml_bytes = (xml_bytes.replace(b"&#13;\n", b"\n").replace(b"&#13;", b"")
                 .replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    # Final newline - as in the original (new file -> none, canon #57)
    want_final_nl = style["final_nl"] if style else False
    xml_bytes = xml_bytes.rstrip(b"\n")
    if want_final_nl:
        xml_bytes += b"\n"
    # EOL - as in the original (new file -> CRLF, canon #57)
    if (style["crlf"] if style else True):
        xml_bytes = xml_bytes.replace(b"\n", b"\r\n")
    return xml_bytes


def save_xml_with_bom(tree, path):
    """Save XML tree preserving the existing file's BOM/EOL/encoding-case/final-newline."""
    style = _detect_xml_style(path)
    xml_bytes = etree.tostring(tree, xml_declaration=True, encoding="UTF-8")
    xml_bytes = _finalize_xml_bytes(xml_bytes, style)
    with open(path, "wb") as f:
        if style is None or style["bom"]:
            f.write(b"\xef\xbb\xbf")
        f.write(xml_bytes)


def write_utf8_bom(path, content):
    # newline='' - no translation: otherwise Python text mode would give CRLF on Windows
    # and LF on macOS, that is, the skill output would depend on the OS.
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(content)



def is_valid_lang(code):
    """The language code goes both into the XML text and into the page file name.

    An empty value would give a ".html" file and an empty <Page></Page>, a path separator - a write
    outside the pages directory, and a reserved device name (nul, con, prn, aux, com1…, lpt1…)
    on Windows redirects the write into the device itself: with -Lang nul this port silently wrote
    <Page>nul</Page> and an empty directory with exit code 0. All platform rejections would be silent.

    fullmatch, not match: the latter with `$` allows a trailing newline.

    A copy of this function exists in help-add (the skills are autonomous, the "descriptor + page"
    format is common to them). Keeping the copies identical is intentional; drift is tracked by check-inline-drift.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        return False
    if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", code):
        return False
    return True


def write_xml_file(path, content):
    """XML in the Configurator dump canon: CRLF in separators, no final newline.

    A copy of this function exists in every emitter skill (the skills are autonomous). Keeping
    the copies identical is intentional: diverged copies negate the whole point.

    An HTML template page does NOT go here - the platform stores it with LF.
    """
    text = content.replace('\r\n', '\n').replace('\n', '\r\n').rstrip('\r\n')
    write_utf8_bom(path, text)


def detect_format_version(d):
    while d:
        # Standalone external data processor/report: it has no Configuration.xml of its own; the version is carried by
        # the root of the processor itself. Without this, a form and a template inside a 2.21 processor would be written as 2.17.
        ext_path = d + ".xml"
        if os.path.isfile(ext_path):
            with open(ext_path, "r", encoding="utf-8-sig") as f:
                ext_head = f.read(2000)
            if re.search(r'<(ExternalDataProcessor|ExternalReport)[ >]', ext_head):
                m = re.search(r'<MetaDataObject[^>]+version="(\d+\.\d+)"', ext_head)
                if m:
                    return m.group(1)
        cfg_path = os.path.join(d, "Configuration.xml")
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                head = f.read(2000)
            m = re.search(r'<MetaDataObject[^>]+version="(\d+\.\d+)"', head)
            if m:
                return m.group(1)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return "2.17"

def format_rank(ver):
    """"2.20" -> 220, "2.9" -> 209. String comparison is wrong ("2.9" > "2.17")."""
    m = re.match(r'^(\d+)\.(\d+)$', ver or '')
    return int(m.group(1)) * 100 + int(m.group(2)) if m else 0



def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Add template to 1C object", allow_abbrev=False)
    parser.add_argument("-ObjectName", "-ProcessorName", required=True)
    parser.add_argument("-TemplateName", required=True)
    parser.add_argument("-TemplateType", required=True,
                        choices=["HTML", "Text", "SpreadsheetDocument", "BinaryData", "DataCompositionSchema"])
    parser.add_argument("-Synonym", default=None)
    parser.add_argument("-Lang", default="ru")
    parser.add_argument("-SrcDir", default="src")
    parser.add_argument("-SetMainSKD", action="store_true")
    args = ci_parse_args(parser)

    object_name = args.ObjectName
    template_name = args.TemplateName
    template_type = args.TemplateType
    synonym = args.Synonym if args.Synonym is not None else template_name
    lang = args.Lang
    src_dir = args.SrcDir
    set_main_skd = args.SetMainSKD

    tmpl = TYPE_MAP[template_type]


    # --- Checks ---

    object_type_folders = [
        "Reports", "DataProcessors", "Documents", "Catalogs",
        "InformationRegisters", "AccumulationRegisters",
        "ChartsOfCharacteristicTypes", "ChartsOfAccounts", "ChartsOfCalculationTypes",
        "BusinessProcesses", "Tasks", "ExchangePlans",
    ]

    root_xml_path = os.path.join(src_dir, f"{object_name}.xml")
    if not os.path.exists(root_xml_path):
        candidates = []
        for folder in object_type_folders:
            probe = os.path.join(src_dir, folder, f"{object_name}.xml")
            if os.path.exists(probe):
                candidates.append(os.path.join(src_dir, folder))
        if len(candidates) == 1:
            src_dir = candidates[0]
            root_xml_path = os.path.join(src_dir, f"{object_name}.xml")
            print(f"[INFO] SrcDir расширен до: {src_dir}")
        elif len(candidates) > 1:
            print(f"Объект '{object_name}' найден в нескольких подпапках: {', '.join(candidates)}", file=sys.stderr)
            print(f"Укажи SrcDir явно", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Корневой файл объекта не найден: {root_xml_path}", file=sys.stderr)
            print(f"Ожидается: <SrcDir>/<ObjectName>.xml", file=sys.stderr)
            print(f"Подсказка: SrcDir должен указывать на папку типа объектов (например Reports), а не на корень конфигурации", file=sys.stderr)
            sys.exit(1)

    processor_dir = os.path.join(src_dir, object_name)
    templates_dir = os.path.join(processor_dir, "Templates")
    template_meta_path = os.path.join(templates_dir, f"{template_name}.xml")

    if not is_valid_lang(lang):
        print(f"Недопустимый код языка: '{lang}'", file=sys.stderr)
        print("Ожидается код вида ru, en (буквы, цифры, дефис, подчёркивание; имена устройств Windows недопустимы)", file=sys.stderr)
        sys.exit(1)

    # An existing HTML template is not always a reason to refuse: the platform puts
    # several languages into one template (<Page> for each, pages alongside), and a repeated call with a different -Lang
    # adds a page. For other types the behavior is the previous one - refusal.
    add_lang_mode = False
    if os.path.exists(template_meta_path):
        with open(template_meta_path, "r", encoding="utf-8-sig") as f:
            meta_text = f.read()
        m_type = re.search(r"<TemplateType>([^<]+)</TemplateType>", meta_text)
        existing_type = m_type.group(1) if m_type else None

        if template_type == "HTML" and existing_type == "HTMLDocument":
            add_lang_mode = True
        elif template_type == "HTML":
            print(f"Макет уже существует: {template_meta_path}", file=sys.stderr)
            print(f"Его тип — {existing_type}, страницу на языке можно добавить только к HTML-макету", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Макет уже существует: {template_meta_path}", file=sys.stderr)
            sys.exit(1)

    assert_edit_allowed(root_xml_path, "editable")

    # Take the version first of all from the root of the object itself - it always carries it, and for a standalone
    # external data processor/report there is nowhere to walk up to Configuration.xml.
    format_version = None
    with open(root_xml_path, "r", encoding="utf-8-sig") as f:
        obj_head = f.read(2000)
    m_ver = re.search(r'<MetaDataObject[^>]+version="(\d+\.\d+)"', obj_head)
    if m_ver:
        format_version = m_ver.group(1)
    if not format_version:
        format_version = detect_format_version(os.path.abspath(src_dir))

    # Namespace declarations - in a single variable: the emission site only substitutes it.
    # Header edits (like xmlns:pal in format 2.21) are made here, in one place.
    xmlns_decl = (
        'xmlns="http://v8.1c.ru/8.3/MDClasses"'
        ' xmlns:app="http://v8.1c.ru/8.2/managed-application/core"'
        ' xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"'
        ' xmlns:cmi="http://v8.1c.ru/8.2/managed-application/cmi"'
        ' xmlns:ent="http://v8.1c.ru/8.1/data/enterprise"'
        ' xmlns:lf="http://v8.1c.ru/8.2/managed-application/logform"'
        ' xmlns:style="http://v8.1c.ru/8.1/data/ui/style"'
        ' xmlns:sys="http://v8.1c.ru/8.1/data/ui/fonts/system"'
        ' xmlns:v8="http://v8.1c.ru/8.1/data/core"'
        ' xmlns:v8ui="http://v8.1c.ru/8.1/data/ui"'
        ' xmlns:web="http://v8.1c.ru/8.1/data/ui/colors/web"'
        ' xmlns:win="http://v8.1c.ru/8.1/data/ui/colors/windows"'
        ' xmlns:xen="http://v8.1c.ru/8.3/xcf/enums"'
        ' xmlns:xpr="http://v8.1c.ru/8.3/xcf/predef"'
        ' xmlns:xr="http://v8.1c.ru/8.3/xcf/readable"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    )

    # 2.21 (8.5) added the palette namespace to the header - for <Color> in enum values.
    # We insert it IN PLACE (after lf, before style): the platform keeps declarations alphabetically,
    # appending at the end is not allowed.
    if format_rank(format_version) >= 221:
        xmlns_decl = xmlns_decl.replace(
            ' xmlns:style=',
            ' xmlns:pal="http://v8.1c.ru/8.1/data/ui/colors/palette" xmlns:style=')

    # --- Create directories ---

    template_ext_dir = os.path.join(templates_dir, template_name, "Ext")
    os.makedirs(template_ext_dir, exist_ok=True)

    # Skeleton of the template HTML page - in the same form the platform editor writes it
    # (single line, paired </meta>): the first save in the Configurator will give a minimal
    # diff. Needed in two places (new template and adding a language) - hence a single variable.
    html_skeleton = (
        '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">'
        '<html><head>'
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"></meta>'
        '</head><body>\n'
        '</body></html>'
    )

    # --- 1a. Adding a page in another language to an existing HTML template ---
    # Do NOT touch template metadata and ChildObjects here: both are already in place,
    # overwriting would change the UUID. A language not declared in the configuration Languages/ is accepted
    # by the platform and returned on dump (verified on 8.3.27) - we do not check the language set.
    if add_lang_mode:
        desc_path = os.path.join(template_ext_dir, "Template.xml")
        page_dir = os.path.join(template_ext_dir, "Template")
        legacy_page_path = os.path.join(template_ext_dir, "Template.html")
        langs = []
        desc_version = format_version

        # First PARSE the state, and write only at the very end: otherwise a refusal halfway
        # leaves the template parsed (page present, descriptor missing) - and the platform
        # silently ignores such a layout again.
        legacy_pending = False
        page_path = os.path.join(page_dir, f"{lang}.html")

        if os.path.exists(desc_path):
            with open(desc_path, "r", encoding="utf-8-sig") as f:
                desc_text = f.read()
            # Take the version from the descriptor itself: editing someone else's dump must not change the format.
            m_dv = re.search(r'<Help[^>]+version="(\d+\.\d+)"', desc_text)
            if m_dv:
                desc_version = m_dv.group(1)
            langs = re.findall(r"<Page>([^<]+)</Page>", desc_text)
            # Half-migrated tree: the descriptor is already there, but the old Ext/Template.html remains nearby.
            # The platform ignores it, so the text in it will disappear unnoticed - we say it out loud.
            if os.path.exists(legacy_page_path):
                print("[WARN] Рядом лежит старый Ext/Template.html — платформа его игнорирует.")
                print("       Перенесите нужное в Template/<язык>.html и удалите его.")
        elif os.path.exists(legacy_page_path):
            # Layout before v1.24 - a single Ext/Template.html that the platform silently ignores.
            # It has no language, but only a version of the skill without the -Lang parameter could create it,
            # that is, it is a page in the default language.
            if os.path.exists(os.path.join(page_dir, "ru.html")):
                print("Макет разобран: есть и старый Ext/Template.html, и Template/ru.html — что из них актуально, решать не навыку.", file=sys.stderr)
                print("Оставьте один файл и повторите.", file=sys.stderr)
                sys.exit(1)
            legacy_pending = True
            langs = ["ru"]

        # The page file is NEVER overwritten: it may contain template text.
        # An error - only when there is nothing to add: the language is already in the descriptor AND the page is on disk.
        # Comparison is case-insensitive.
        lang_known = lang.lower() in [x.lower() for x in langs]
        # Page existence - also case-insensitive: os.path.exists on Linux is case-sensitive,
        # so we compare names forcibly case-insensitively.
        page_exists = False
        if os.path.isdir(page_dir):
            want = f"{lang}.html".lower()
            page_exists = any(f.lower() == want for f in os.listdir(page_dir))
        # During migration there is nothing to check: langs there is set by us, and the page will appear by moving.
        if lang_known and page_exists and not legacy_pending:
            print(f"Страница макета на языке '{lang}' уже существует: {page_path}", file=sys.stderr)
            sys.exit(1)

        # Page order - by language code (in the ERP dump this is so in all 54 bilingual templates).
        if not lang_known:
            langs = langs + [lang]
        langs = sorted(langs)

        pages_xml = '\n'.join(f"\t<Page>{x}</Page>" for x in langs)
        desc_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Help xmlns="http://v8.1c.ru/8.3/xcf/extrnprops"'
            ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            f' version="{desc_version}">\n'
            f'{pages_xml}\n'
            '</Help>'
        )

        # --- write ---
        os.makedirs(page_dir, exist_ok=True)
        if legacy_pending:
            os.replace(legacy_page_path, os.path.join(page_dir, "ru.html"))
            print("[WARN] Макет был в старой раскладке (Ext/Template.html) — платформа её игнорирует.")
            print("       Страница считана как ru и перенесена в Template/ru.html.")
        write_xml_file(desc_path, desc_xml)
        if os.path.exists(page_path):
            # During migration, the saved content was already mentioned above - do not repeat.
            if not legacy_pending:
                print(f"[WARN] Страница {lang}.html уже лежала на диске — содержимое сохранено, дописан только <Page>.")
        else:
            write_utf8_bom(page_path, html_skeleton)

        print(f"[OK] Добавлена страница макета: {template_name} ({lang})")
        print(f"     Содержимое: {page_path}")
        print(f"     Дескриптор: {desc_path}")
        sys.exit(0)

    # --- 1. Template metadata (Templates/<TemplateName>.xml) ---

    template_uuid = str(uuid.uuid4())

    template_meta_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<MetaDataObject {xmlns_decl} version="{format_version}">\n'
        f'\t<Template uuid="{template_uuid}">\n'
        '\t\t<Properties>\n'
        f'\t\t\t<Name>{template_name}</Name>\n'
        '\t\t\t<Synonym>\n'
        '\t\t\t\t<v8:item>\n'
        '\t\t\t\t\t<v8:lang>ru</v8:lang>\n'
        f'\t\t\t\t\t<v8:content>{synonym}</v8:content>\n'
        '\t\t\t\t</v8:item>\n'
        '\t\t\t</Synonym>\n'
        '\t\t\t<Comment/>\n'
        f'\t\t\t<TemplateType>{tmpl["TemplateType"]}</TemplateType>\n'
        '\t\t</Properties>\n'
        '\t</Template>\n'
        '</MetaDataObject>'
    )

    write_xml_file(template_meta_path, template_meta_xml)

    # --- 2. Template content (Templates/<TemplateName>/Ext/Template.<ext>) ---

    template_file_path = os.path.join(template_ext_dir, f"Template{tmpl['Ext']}")
    # Where to put the template text. Matches template_file_path for all types except HTML:
    # there the content lives in a separate page, and Template.xml is only a descriptor.
    template_body_path = template_file_path

    if template_type == "HTML":
        # The platform stores an HTML template as a pair, like help: the descriptor Ext/Template.xml
        # with a list of pages and the page itself Ext/Template/<language>.html (images -
        # nearby in _files/). A single Ext/Template.html is silently ignored by the platform:
        # loading succeeds without errors, but the template in the infobase is empty.
        page_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Help xmlns="http://v8.1c.ru/8.3/xcf/extrnprops"'
            ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            f' version="{format_version}">\n'
            f'\t<Page>{lang}</Page>\n'
            '</Help>'
        )
        write_xml_file(template_file_path, page_xml)

        page_dir = os.path.join(template_ext_dir, "Template")
        os.makedirs(page_dir, exist_ok=True)
        template_body_path = os.path.join(page_dir, f"{lang}.html")

        # Header - in the same form the platform editor writes it (single line,
        # paired </meta>): the first save in the Configurator will give a minimal diff.
        # Page - with LF: the platform stores HTML exactly like that.
        write_utf8_bom(template_body_path, html_skeleton)

    elif template_type == "Text":
        write_utf8_bom(template_file_path, "")

    elif template_type == "SpreadsheetDocument":
        # Empty template - as a self-closing root: the platform writes no empty pairs
        # in any form (0 out of 65 040 XML dumps of acc_8.3.27, including those spread
        # across lines). For XML `<A/>` and `<A></A>` are identical by specification.
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<SpreadsheetDocument xmlns="http://v8.1c.ru/spreadsheet/document"'
            ' xmlns:ss="http://v8.1c.ru/spreadsheet/document"'
            ' xmlns:v8="http://v8.1c.ru/8.1/data/core"'
            ' xmlns:xs="http://www.w3.org/2001/XMLSchema"/>'
        )
        write_xml_file(template_file_path, content)

    elif template_type == "BinaryData":
        with open(template_file_path, "wb") as f:
            pass  # empty file

    elif template_type == "DataCompositionSchema":
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"\n'
            '\t\txmlns:dcscom="http://v8.1c.ru/8.1/data-composition-system/common"\n'
            '\t\txmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"\n'
            '\t\txmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"\n'
            '\t\txmlns:v8="http://v8.1c.ru/8.1/data/core"\n'
            '\t\txmlns:v8ui="http://v8.1c.ru/8.1/data/ui"\n'
            '\t\txmlns:xs="http://www.w3.org/2001/XMLSchema"\n'
            '\t\txmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
            '\t<dataSource>\n'
            '\t\t<name>ИсточникДанных1</name>\n'
            '\t\t<dataSourceType>Local</dataSourceType>\n'
            '\t</dataSource>\n'
            '</DataCompositionSchema>'
        )
        write_xml_file(template_file_path, content)

    # --- 3. Modify root XML ---

    root_xml_full = os.path.abspath(root_xml_path)
    parser_xml = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(root_xml_full, parser_xml)
    root = tree.getroot()

    ns = "http://v8.1c.ru/8.3/MDClasses"
    child_objects = root.find(".//md:ChildObjects", NSMAP)
    if child_objects is None:
        print(f"Не найден элемент ChildObjects в {root_xml_path}", file=sys.stderr)
        sys.exit(1)

    # Add <Template> to end of ChildObjects — idempotent (do not duplicate already-registered template)
    already_registered = child_objects.find(f"md:Template[.='{template_name}']", NSMAP) is not None

    if not already_registered:
        template_elem = etree.SubElement(child_objects, f"{{{ns}}}Template")
        template_elem.text = template_name
        # Remove auto-appended element to reinsert with proper whitespace
        child_objects.remove(template_elem)

        children = list(child_objects)
        if len(children) == 0 and (child_objects.text is None or child_objects.text.strip() == ""):
            # Empty ChildObjects (self-closing)
            child_objects.text = "\n\t\t\t"
            child_objects.append(template_elem)
            template_elem.tail = "\n\t\t"
        else:
            if len(children) > 0:
                last_child = children[-1]
                # last_child.tail is the trailing whitespace before </ChildObjects>
                old_tail = last_child.tail
                last_child.tail = "\n\t\t\t"
                child_objects.append(template_elem)
                template_elem.tail = old_tail if old_tail else "\n\t\t"
            else:
                # Has text content but no element children
                child_objects.text = (child_objects.text or "") + "\n\t\t\t"
                child_objects.append(template_elem)
                template_elem.tail = "\n\t\t"

    # --- 4. MainDataCompositionSchema (for ExternalReport / Report) ---

    main_dcs_updated = False
    if template_type == "DataCompositionSchema":
        report_like_types = ["ExternalReport", "Report"]
        object_type_node = None
        object_type_name = None
        for rt in report_like_types:
            node = root.find(f".//md:{rt}", NSMAP)
            if node is not None:
                object_type_node = node
                object_type_name = rt
                break

        if object_type_node is not None:
            main_dcs = root.find(f".//md:{object_type_name}/md:Properties/md:MainDataCompositionSchema", NSMAP)
            if main_dcs is not None:
                is_empty = main_dcs.text is None or main_dcs.text.strip() == ""
                if is_empty or set_main_skd:
                    obj_name_node = root.find(f".//md:{object_type_name}/md:Properties/md:Name", NSMAP)
                    obj_name = obj_name_node.text if obj_name_node is not None else ""
                    main_dcs.text = f"{object_type_name}.{obj_name}.Template.{template_name}"
                    main_dcs_updated = True

    # Save with BOM
    save_xml_with_bom(tree, root_xml_full)

    print(f"[OK] Создан макет: {template_name} ({template_type})")
    if already_registered:
        print(f"     Already registered: <Template>{template_name}</Template> in ChildObjects (skipped duplicate)")
    print(f"     Метаданные: {template_meta_path}")
    print(f"     Содержимое: {template_body_path}")
    if template_type == "HTML":
        print(f"     Дескриптор: {template_file_path}")
    if main_dcs_updated:
        print(f"     MainDataCompositionSchema: {main_dcs.text}")


if __name__ == "__main__":
    main()
