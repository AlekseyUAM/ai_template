#!/usr/bin/env python3
"""Build event_handlers.json from the 1C platform syntax help (.hbk).

The .hbk container stores a ZIP with HTML pages of the syntax assistant. Event
descriptions live in `objects/**/events/*.html`; the paired `.st` file contains
a ready handler template in Russian and English:
    Процедура ОбработкаПроведения(Отказ, РежимПроведения)
    Procedure Posting(Cancel, PostingMode)
Event parameters are taken from those templates (fallback: the `Синтаксис:`
section of the page).

Usage:
    python tools/update_event_handlers.py --hbk "C:/.../shcntx_ru.hbk" \
        --out event_handlers.json --platform 8.3.27.2170
    python tools/update_event_handlers.py --html-dir <extracted> --out ...

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import struct
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── HBK container ─────────────────────────────────────────────

_HBK_END = 0x7FFFFFFF
_BLOCK_HEADER_LEN = 31  # "\r\n" + 8 hex + " " + 8 hex + " " + 8 hex + " " + "\r\n"


def _block_header(data: bytes, offset: int):
    """Return (data_size, page_size, next_page) of the block at offset."""
    if data[offset:offset + 2] != b"\r\n":
        raise ValueError(f"not a block header at 0x{offset:x}")
    line = data[offset:offset + _BLOCK_HEADER_LEN].decode("ascii", "replace")
    parts = line[2:].split()
    if len(parts) < 3:
        raise ValueError(f"bad block header at 0x{offset:x}: {line!r}")
    return int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)


def _read_pages(data: bytes, offset: int) -> bytes:
    out = bytearray()
    while offset != _HBK_END:
        size, _page, nxt = _block_header(data, offset)
        out += data[offset + _BLOCK_HEADER_LEN:offset + _BLOCK_HEADER_LEN + size]
        offset = nxt
    return bytes(out)


def hbk_files(path: Path) -> dict[str, bytes]:
    """Return {archive_name: bytes} for the FileStorage ZIP inside .hbk."""
    data = path.read_bytes()
    root_size, _root_page, _root_next = _block_header(data, 16)
    toc = data[16 + _BLOCK_HEADER_LEN:16 + _BLOCK_HEADER_LEN + root_size]
    storage = None
    for i in range(0, len(toc) - 11, 12):
        attr_addr, data_addr, _ = struct.unpack_from("<III", toc, i)
        attrs_size, _p, _n = _block_header(data, attr_addr)
        body = data[attr_addr + _BLOCK_HEADER_LEN:
                    attr_addr + _BLOCK_HEADER_LEN + attrs_size]
        # 8 bytes creation, 8 bytes modification, 4 zero, then UTF-16LE name
        name = body[20:].decode("utf-16le", "ignore").rstrip("\x00")
        if name == "FileStorage":
            storage = _read_pages(data, data_addr)
            break
    if storage is None:
        raise ValueError("FileStorage not found in .hbk")
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(storage)) as zf:
        for name in zf.namelist():
            if name.lower().endswith((".html", ".st")):
                result[name] = zf.read(name)
    return result


# ── owner → module key ───────────────────────────────────────

_TYPE_RU = {
    "Document": "Документ", "Catalog": "Справочник",
    "DocumentJournal": "Журнал документов", "Enum": "Перечисление",
    "Constant": "Константа", "InformationRegister": "Регистр сведений",
    "AccumulationRegister": "Регистр накопления",
    "AccountingRegister": "Регистр бухгалтерии",
    "CalculationRegister": "Регистр расчета", "BusinessProcess": "Бизнес-процесс",
    "Task": "Задача", "ChartOfAccounts": "План счетов",
    "ChartsOfCalculationTypes": "План видов расчета",
    "ChartOfCalculationTypes": "План видов расчета",
    "ChartOfCharacteristicTypes": "План видов характеристик",
    "ChartsOfCharacteristicTypes": "План видов характеристик",
    "ExchangePlan": "План обмена", "Sequence": "Последовательность",
    "Recalculation": "Перерасчет", "FilterCriterion": "Критерий отбора",
    "SettingsStorage": "Хранилище настроек", "DataProcessor": "Обработка",
    "Report": "Отчет", "CommonModule": "Общий модуль",
    "CommonCommand": "Общая команда", "Command": "Команда",
    "HTTPService": "HTTP-сервис", "WebService": "Web-сервис",
    "WebSocketClient": "WebSocket-клиент", "Bot": "Бот",
    "IntegrationService": "Сервис интеграции",
    "ExternalDataProcessor": "Внешняя обработка",
    "ExternalReport": "Внешний отчет",
    "ExternalDataSourceTable": "Таблица внешнего источника данных",
    "ExternalDataSourceCube": "Куб внешнего источника данных",
    "ExternalDataSourceCubeDimensionTable":
        "Таблица измерений куба внешнего источника данных",
}

_KIND_RU = {
    "ObjectModule": "Модуль объекта", "ManagerModule": "Модуль менеджера",
    "RecordSetModule": "Модуль набора записей",
    "ValueManagerModule": "Модуль менеджера значения", "Module": "Модуль",
    "CommandModule": "Модуль команды",
    "ManagedApplicationModule": "Модуль управляемого приложения",
    "OrdinaryApplicationModule": "Модуль обычного приложения",
    "ExternalConnectionModule": "Модуль внешнего соединения",
    "SessionModule": "Модуль сеанса",
}

# Help owner base → (metadata type, module kind). Only modules where the
# platform calls handlers by name. Forms are intentionally absent: their
# handlers are bound in Form.xml and are not checked by this script.
OWNER_TO_MODULE: dict[str, tuple[str, str]] = {
    "ДокументОбъект": ("Document", "ObjectModule"),
    "ДокументМенеджер": ("Document", "ManagerModule"),
    "СправочникОбъект": ("Catalog", "ObjectModule"),
    "СправочникМенеджер": ("Catalog", "ManagerModule"),
    "ЖурналДокументовМенеджер": ("DocumentJournal", "ManagerModule"),
    "ПеречислениеМенеджер": ("Enum", "ManagerModule"),
    "КонстантаМенеджер": ("Constant", "ManagerModule"),
    "КонстантаМенеджерЗначения": ("Constant", "ValueManagerModule"),
    "КритерийОтбораМенеджер": ("FilterCriterion", "ManagerModule"),
    "ПланСчетовОбъект": ("ChartOfAccounts", "ObjectModule"),
    "ПланСчетовМенеджер": ("ChartOfAccounts", "ManagerModule"),
    "ПланВидовХарактеристикОбъект": ("ChartOfCharacteristicTypes", "ObjectModule"),
    "ПланВидовХарактеристикМенеджер": ("ChartOfCharacteristicTypes", "ManagerModule"),
    "ПланВидовРасчетаОбъект": ("ChartOfCalculationTypes", "ObjectModule"),
    "ПланВидовРасчетаМенеджер": ("ChartOfCalculationTypes", "ManagerModule"),
    "ПланОбменаОбъект": ("ExchangePlan", "ObjectModule"),
    "ПланОбменаМенеджер": ("ExchangePlan", "ManagerModule"),
    "БизнесПроцессОбъект": ("BusinessProcess", "ObjectModule"),
    "БизнесПроцессМенеджер": ("BusinessProcess", "ManagerModule"),
    "ЗадачаОбъект": ("Task", "ObjectModule"),
    "ЗадачаМенеджер": ("Task", "ManagerModule"),
    "ОбработкаОбъект": ("DataProcessor", "ObjectModule"),
    "ОбработкаМенеджер": ("DataProcessor", "ManagerModule"),
    "ОтчетОбъект": ("Report", "ObjectModule"),
    "ОтчетМенеджер": ("Report", "ManagerModule"),
    "РегистрСведенийНаборЗаписей": ("InformationRegister", "RecordSetModule"),
    "РегистрСведенийМенеджер": ("InformationRegister", "ManagerModule"),
    "РегистрНакопленияНаборЗаписей": ("AccumulationRegister", "RecordSetModule"),
    "РегистрНакопленияМенеджер": ("AccumulationRegister", "ManagerModule"),
    "РегистрБухгалтерииНаборЗаписей": ("AccountingRegister", "RecordSetModule"),
    "РегистрБухгалтерииМенеджер": ("AccountingRegister", "ManagerModule"),
    "РегистрРасчетаНаборЗаписей": ("CalculationRegister", "RecordSetModule"),
    "РегистрРасчетаМенеджер": ("CalculationRegister", "ManagerModule"),
    "ПоследовательностьНаборЗаписей": ("Sequence", "RecordSetModule"),
    "ПерерасчетНаборЗаписей": ("Recalculation", "RecordSetModule"),
    "ХранилищеНастроекМенеджер": ("SettingsStorage", "ManagerModule"),
    "ВнешняяОбработка": ("ExternalDataProcessor", "ObjectModule"),
    "ВнешнийОтчет": ("ExternalReport", "ObjectModule"),
    "ВнешнийИсточникДанныхТаблицаОбъект":
        ("ExternalDataSourceTable", "ObjectModule"),
    "ВнешнийИсточникДанныхТаблицаНаборЗаписей":
        ("ExternalDataSourceTable", "RecordSetModule"),
    "ВнешнийИсточникДанныхТаблицаМенеджер":
        ("ExternalDataSourceTable", "ManagerModule"),
    "ВнешнийИсточникДанныхКубМенеджер":
        ("ExternalDataSourceCube", "ManagerModule"),
    "ВнешнийИсточникДанныхКубТаблицаИзмеренияМенеджер":
        ("ExternalDataSourceCubeDimensionTable", "ManagerModule"),
    "Модуль команды": (None, "CommandModule"),
    "Модуль WebSocket клиента": ("WebSocketClient", "Module"),
    "Модуль бота": ("Bot", "Module"),
}

# Modules whose handler names are configured in metadata: signatures cannot be
# matched by procedure name, so they are not checked.
ARBITRARY_HANDLER_OWNERS = {
    "Модуль HTTP-сервиса": ("HTTPService", "Module"),
    "Модуль Web-сервиса": ("WebService", "Module"),
    "Модуль сервиса интеграции": ("IntegrationService", "Module"),
}

APP_EVENT_CATEGORIES = {
    "События приложения": ("Configuration", "ManagedApplicationModule"),
    "События обычного приложения": ("Configuration", "OrdinaryApplicationModule"),
    "События внешнего соединения": ("Configuration", "ExternalConnectionModule"),
    "События модуля сеанса": ("Configuration", "SessionModule"),
}

# Signatures accepted in addition to the syntax assistant. BSP reports use the
# 4th `АдресХранилища` parameter of `ПриКомпоновкеРезультата`; the catalog
# `ПередЗаписью(Отказ, РежимЗаписи, РежимПроведения)` is deliberately NOT here:
# `РежимПроведения` is document-specific and such a catalog handler is a defect.
EXTRA_SIGNATURES: dict[str, dict[str, list[dict]]] = {
    "Report.ObjectModule": {
        "ПриКомпоновкеРезультата": [
            {
                "params_ru": ["ДокументРезультат", "ДанныеРасшифровки",
                              "СтандартнаяОбработка", "АдресХранилища"],
                "params_en": ["ResultDocument", "DetailsData",
                              "StandardProcessing", "StorageAddress"],
                "optional": [False, False, False, True],
                "required_count": 3,
            },
            {
                "params_ru": ["ДокументРезультат", "ДанныеРасшифровкиОбъект",
                              "СтандартнаяОбработка", "АдресХранилища"],
                "params_en": ["ResultDocument", "DetailsData",
                              "StandardProcessing", "StorageAddress"],
                "optional": [False, False, False, True],
                "required_count": 3,
            },
        ],
    },
}


def module_key(meta: str | None, kind: str) -> str:
    return f"{meta}.{kind}" if meta else kind


def module_title(meta: str | None, kind: str) -> str:
    kind_ru = _KIND_RU.get(kind, kind)
    if meta and meta != "Configuration":
        return f"{kind_ru} ({_TYPE_RU.get(meta, meta)})"
    return kind_ru


# ── page parsing ─────────────────────────────────────────────

_TITLE_RE = re.compile(r'<h1 class="V8SH_pagetitle">(.*?)</h1>', re.S)
_OWNER_RE = re.compile(r'<p class="V8SH_title">(.*?)</p>', re.S)
_SYNTAX_RE = re.compile(
    r'<p class="V8SH_chapter">Синтаксис:</p>(.*?)(?:<p class="V8SH_chapter">|</body>)',
    re.S)
_ST_RE = re.compile(r'"ru",\d+,\d+,"","(.*?)"\}', re.S)
_ST_EN_RE = re.compile(r'"en",\d+,\d+,"","(.*?)"\}', re.S)
_PROC_RE = re.compile(
    r'^\s*(?:(Процедура|Функция|Procedure|Function)\s+)?([^(]+?)\s*\((.*?)\)',
    re.S | re.I)


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def params_info(html_text: str) -> list[tuple[str, bool]]:
    """[(parameter name, optional)] from the `Параметры:` chapter."""
    section = re.search(
        r'<p class="V8SH_chapter">Параметры:</p>(.*?)'
        r'(?=<p class="V8SH_chapter">|</body>)', html_text, re.S)
    if not section:
        return []
    result = []
    for match in re.finditer(
            r'<div class="V8SH_rubric">\s*<p[^>]*>(.*?)</div>(.*?)'
            r'(?=<div class="V8SH_rubric">|<p class="V8SH_chapter">|$)',
            section.group(1), re.S):
        name = strip_tags(match.group(1)).strip("<> ")
        body = strip_tags(match.group(2))
        optional = ("Значение по умолчанию" in body
                    or "Необязательн" in body)
        result.append((name, optional))
    return result


def split_title(title: str) -> tuple[str, str]:
    match = re.match(r"^(.*?)\s*\((.*)\)\s*$", title)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return title.strip(), ""


def event_name(full: str) -> str:
    return full.split(".")[-1].strip()


def parse_template(text: str) -> tuple[str, str, list[str], bool] | None:
    """(kind, name, params, arbitrary) from a handler template, or None."""
    match = _PROC_RE.search(html.unescape(text))
    if not match:
        return None
    keyword = (match.group(1) or "").lower()
    kind = "procedure" if keyword in ("", "процедура", "procedure") else "function"
    name = match.group(2).strip()
    raw = match.group(3).strip()
    params = [p.strip() for p in raw.split(",") if p.strip()] if raw else []
    arbitrary = "<" in name or ">" in name
    clean = [p.strip("<> ") for p in params]
    return kind, name, clean, arbitrary


def page_signature(html_text: str, st_text: str | None):
    """Return (kind, ru_name, en_name, params_ru, params_en, arbitrary)."""
    title_match = _TITLE_RE.search(html_text)
    title = strip_tags(title_match.group(1)) if title_match else ""
    ru_full, en_full = split_title(title)
    ru_name = event_name(ru_full)
    en_name = event_name(en_full) if en_full else ""

    params_ru: list[str] = []
    params_en: list[str] = []
    arbitrary = False
    kind = "procedure"
    if st_text:
        ru_m = _ST_RE.search(st_text)
        en_m = _ST_EN_RE.search(st_text)
        if ru_m:
            parsed = parse_template(ru_m.group(1).split("<br>")[0])
            if parsed:
                kind, name, params_ru, arbitrary = parsed
                if name and "<" not in name:
                    ru_name = name
        if en_m:
            parsed = parse_template(en_m.group(1).split("<br>")[0])
            if parsed:
                _kind, name, params_en, en_arbitrary = parsed
                if name and "<" not in name:
                    en_name = name
                arbitrary = arbitrary or en_arbitrary
    if not params_ru:
        syn = _SYNTAX_RE.search(html_text)
        if syn:
            parsed = parse_template(strip_tags(syn.group(1)))
            if parsed:
                _kind, name, params_ru, arb = parsed
                arbitrary = arbitrary or arb
                if name and "<" not in name and not ru_name:
                    ru_name = name
    info = params_info(html_text)
    total = len(params_ru) or len(params_en)
    optional = [info[i][1] if i < len(info) else False for i in range(total)]
    required = sum(1 for value in optional if not value)
    return kind, ru_name, en_name, params_ru, params_en, optional, required, arbitrary


def add_event(modules: dict, key: str, meta: str | None, kind: str,
              title: str, en_title: str, ev_kind: str, ru_name: str,
              en_name: str, params_ru: list[str], params_en: list[str],
              optional: list[bool], required: int, arbitrary: bool):
    mod = modules.setdefault(key, {
        "title_ru": module_title(meta, kind),
        "title_en": en_title or module_title(meta, kind),
        "metadata_type": meta,
        "module_kind": kind,
        "events": {},
    })
    if arbitrary:
        mod["handler_name_arbitrary"] = True
        return
    if not ru_name:
        return
    event = mod["events"].setdefault(ru_name, {
        "name_en": en_name, "kind": ev_kind, "signatures": []})
    signature = {"params_ru": params_ru, "params_en": params_en,
                 "optional": optional, "required_count": required}
    if signature not in event["signatures"]:
        event["signatures"].append(signature)


def parse_help(files: dict[str, bytes]) -> dict:
    modules: dict[str, dict] = {}

    # Application events: category page → its sibling folder.
    category_dirs: dict[str, str] = {}
    for path, raw in files.items():
        if not path.endswith(".html"):
            continue
        text = raw.decode("utf-8-sig", "replace")
        m = _TITLE_RE.search(text)
        if not m:
            continue
        title = strip_tags(m.group(1))
        if title in APP_EVENT_CATEGORIES:
            category_dirs[path[:-5]] = title

    for folder, category in category_dirs.items():
        meta, kind = APP_EVENT_CATEGORIES[category]
        prefix = folder + "/"
        for path, raw in files.items():
            if not path.startswith(prefix) or not path.endswith(".html"):
                continue
            if path.count("/") != prefix.count("/"):
                continue
            text = raw.decode("utf-8-sig", "replace")
            st = files.get(path[:-5] + ".st")
            st_text = st.decode("utf-8-sig", "replace") if st else None
            (ev_kind, ru, en, pr, pe, optional, required,
             arbitrary) = page_signature(text, st_text)
            add_event(modules, module_key(meta, kind), meta, kind,
                      category, "", ev_kind, ru, en, pr, pe, optional,
                      required, arbitrary)

    # Arbitrary-handler service modules.
    for path, raw in files.items():
        if not path.endswith(".html") or "/events/" not in path:
            continue
        text = raw.decode("utf-8-sig", "replace")
        owner_m = _OWNER_RE.search(text)
        title_m = _TITLE_RE.search(text)
        if not owner_m or not title_m:
            continue
        owner = strip_tags(owner_m.group(1)).split(" (")[0]
        base = owner.split(".")[0].strip()
        if base in ARBITRARY_HANDLER_OWNERS:
            meta, kind = ARBITRARY_HANDLER_OWNERS[base]
            modules.setdefault(module_key(meta, kind), {
                "title_ru": module_title(meta, kind),
                "title_en": "",
                "metadata_type": meta,
                "module_kind": kind,
                "handler_name_arbitrary": True,
                "events": {},
            })

    # Metadata module events.
    for path, raw in files.items():
        if not path.endswith(".html") or "/events/" not in path:
            continue
        if path.startswith("objects/Global context/"):
            continue
        text = raw.decode("utf-8-sig", "replace")
        owner_m = _OWNER_RE.search(text)
        if not owner_m:
            continue
        owner_ru, owner_en = split_title(strip_tags(owner_m.group(1)))
        base = owner_ru.split(".")[0].strip()
        if base not in OWNER_TO_MODULE:
            continue
        meta, kind = OWNER_TO_MODULE[base]
        st = files.get(path[:-5] + ".st")
        st_text = st.decode("utf-8-sig", "replace") if st else None
        (ev_kind, ru, en, pr, pe, optional, required,
         arbitrary) = page_signature(text, st_text)
        if meta is None:  # command module: same events for both metadata types
            add_event(modules, module_key("CommonCommand", kind), "CommonCommand",
                      kind, owner_ru, owner_en, ev_kind, ru, en, pr, pe,
                      optional, required, arbitrary)
            add_event(modules, module_key("Command", kind), "Command",
                      kind, owner_ru, owner_en, ev_kind, ru, en, pr, pe,
                      optional, required, arbitrary)
        else:
            add_event(modules, module_key(meta, kind), meta, kind,
                      owner_ru, owner_en, ev_kind, ru, en, pr, pe,
                      optional, required, arbitrary)

    # Drop empty event maps that are not arbitrary-name modules.
    return {key: mod for key, mod in modules.items()
            if mod.get("events") or mod.get("handler_name_arbitrary")}


def apply_extra_signatures(modules: dict) -> None:
    for key, events in EXTRA_SIGNATURES.items():
        mod = modules.get(key)
        if not mod:
            continue
        for name, signatures in events.items():
            event = (mod.get("events") or {}).get(name)
            if not event:
                continue
            for signature in signatures:
                if signature not in event["signatures"]:
                    event["signatures"].append(signature)


def build(files: dict[str, bytes], platform: str) -> dict:
    modules = parse_help(files)
    apply_extra_signatures(modules)
    events = sum(len(mod.get("events") or {}) for mod in modules.values())
    return {
        "schema_version": 1,
        "platform": platform,
        "generated_at": date.today().isoformat(),
        "source": "shcntx_ru.hbk (syntax assistant)",
        "event_count": events,
        "modules": dict(sorted(modules.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--hbk", type=Path, help="путь к shcntx_ru.hbk")
    src.add_argument("--html-dir", type=Path,
                     help="ранее распакованный каталог справки")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--platform", default="unknown")
    args = parser.parse_args()

    if args.hbk:
        files = hbk_files(args.hbk)
    else:
        files = {}
        for path in args.html_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in (".html", ".st"):
                rel = path.relative_to(args.html_dir).as_posix()
                files[rel] = path.read_bytes()

    data = build(files, args.platform)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"модулей: {len(data['modules'])}, событий: {data['event_count']}")
    print(f"записано: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
