#!/usr/bin/env python
# role-compile v1.45 — Compile 1C role from JSON
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills
import argparse
import json
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

from lxml import etree

# Case-insensitive input: parameter names and choices values are accepted
# in any case (argparse matches exactly by default).

def parse_json_input(text, source, expected=None, inline=False):
    """Parse user JSON: one line to stderr instead of a traceback (issue #80).

    expected is filled only for polymorphic input: for a file the hint would
    be filler - the file name and the parser text are self-sufficient. inline also prints what
    arrived: for a file there is no such question, it lies on disk and is visible in full.

    Imports inside the body: a copy of the function lives in skills with different module names
    (skd-decompile imports json locally as _json), and the body must be identical.
    """
    import json as _pj
    import sys as _psys
    try:
        if not str(text).strip():
            raise ValueError("input is empty")
        return _pj.loads(text)
    except ValueError as exc:
        what = "%s expects %s" % (source, expected) if expected else "Invalid JSON in %s" % source
        if inline:
            got = " ".join(str(text).split())
            label = "got"
            if not got:
                got = "(empty)"
            elif len(got) > 60:
                label = "got (first 60 chars)"
                got = got[:60]
            what = "%s, %s: %s" % (what, label, got)
        print("[ERROR] %s (%s)" % (what, exc), file=_psys.stderr)
        _psys.exit(1)


def read_json_file(path):
    """Read the input JSON file with the encoding from the BOM (issue #80).

    The BOM is the file's own declaration, so we trust it; without a BOM we expect strict UTF-8. We do
    not guess the code page: a guessed name would silently travel into metadata.
    """
    import os as _pos
    import sys as _psys
    if not _pos.path.exists(path):
        print("[ERROR] File not found: %s" % path, file=_psys.stderr)
        _psys.exit(1)
    if _pos.path.isdir(path):
        print("[ERROR] Expected a JSON file, got a directory: %s" % path, file=_psys.stderr)
        _psys.exit(1)
    with open(path, "rb") as _fh:
        data = _fh.read()
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8")
    if data[:2] == b"\xff\xfe":
        return data[2:].decode("utf-16-le")
    if data[:2] == b"\xfe\xff":
        return data[2:].decode("utf-16-be")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        print("[ERROR] %s is not valid UTF-8: %s - save the file as UTF-8, or add a BOM if it is UTF-16"
              % (path, exc), file=_psys.stderr)
        _psys.exit(1)


class CIDict(dict):
    # Keys are stored AS IS: some of them are object names (tabular sections, standard
    # attributes), they get into the XML. Only lookup is case-insensitive. Insertion order
    # is preserved - the emission order depends on it.
    def _actual(self, key):
        if not isinstance(key, str) or dict.__contains__(self, key):
            return key
        ci = self.__dict__.get('_ci')
        if ci is None or len(ci) != len(self):
            ci = {k.lower(): k for k in self if isinstance(k, str)}
            self.__dict__['_ci'] = ci
        return ci.get(key.lower(), key)

    def __getitem__(self, key):
        return dict.__getitem__(self, self._actual(key))

    def __contains__(self, key):
        return dict.__contains__(self, self._actual(key))

    def get(self, key, default=None):
        return dict.get(self, self._actual(key), default)

    def pop(self, key, *default):
        return dict.pop(self, self._actual(key), *default)

    def __setitem__(self, key, value):
        # writing by a key with a different case updates the existing one instead of creating a duplicate
        dict.__setitem__(self, self._actual(key), value)

def ci_json(obj):
    """Recursively wraps parsed JSON: dicts -> CIDict, lists are walked."""
    if isinstance(obj, dict):
        return CIDict((k, ci_json(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return [ci_json(v) for v in obj]
    return obj

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


def detect_eol(text):
    # Take the INSERT line ending from the file itself: the CRLF canon applies to files
    # we create, while editing an existing one preserves its style (#44/#46/#47).
    # The semantics are the same as _detect_xml_style in other ports: CRLF present -> CRLF.
    # The majority rule was a discrepancy here - on mixed input it gave
    # a different answer than the canon with the same purpose.
    return '\r\n' if '\r\n' in text else '\n'

def esc_xml(s):
    # Escape an ATTRIBUTE VALUE: & < > and quote - inside "..." a literal " is invalid.
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def esc_xml_text(s):
    """Escape element TEXT: only & < > . The platform does not escape quotes in text
    (92142 raw quotes in the corpus, not a single &quot;); it accepts &quot; but normalizes it back."""
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def emit_mltext(lines, indent, tag, text):
    if not text:
        lines.append(f"{indent}<{tag}/>")
        return
    lines.append(f"{indent}<{tag}>")
    lines.append(f"{indent}\t<v8:item>")
    lines.append(f"{indent}\t\t<v8:lang>ru</v8:lang>")
    lines.append(f"{indent}\t\t<v8:content>{esc_xml_text(text)}</v8:content>")
    lines.append(f"{indent}\t</v8:item>")
    lines.append(f"{indent}</{tag}>")


def new_uuid():
    return str(uuid.uuid4())


def write_utf8_bom(path, content):
    # newline='' - no translation: otherwise Python text mode would give CRLF on Windows
    # and LF on macOS, that is, the skill output would depend on the OS.
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(content)



# --- Russian synonyms -> canonical English names ---

TYPE_ALIASES = {
    "Справочник": "Catalog",
    "Документ": "Document",
    "РегистрСведений": "InformationRegister",
    "РегистрНакопления": "AccumulationRegister",
    "РегистрБухгалтерии": "AccountingRegister",
    "РегистрРасчета": "CalculationRegister",
    "РегистрРасчёта": "CalculationRegister",
    "Константа": "Constant",
    "ПланСчетов": "ChartOfAccounts",
    "ПланВидовХарактеристик": "ChartOfCharacteristicTypes",
    "ПланВидовРасчета": "ChartOfCalculationTypes",
    "ПланВидовРасчёта": "ChartOfCalculationTypes",
    "ПланОбмена": "ExchangePlan",
    "БизнесПроцесс": "BusinessProcess",
    "Задача": "Task",
    "Обработка": "DataProcessor",
    "Отчет": "Report",
    "Отчёт": "Report",
    "ОбщаяФорма": "CommonForm",
    "ОбщаяКоманда": "CommonCommand",
    "Подсистема": "Subsystem",
    "КритерийОтбора": "FilterCriterion",
    "ЖурналДокументов": "DocumentJournal",
    "Последовательность": "Sequence",
    "ВебСервис": "WebService",
    "HTTPСервис": "HTTPService",
    "СервисИнтеграции": "IntegrationService",
    "ПараметрСеанса": "SessionParameter",
    "ОбщийРеквизит": "CommonAttribute",
    "Конфигурация": "Configuration",
    "ВнешнийИсточникДанных": "ExternalDataSource",
    # Types without rights in roles: aliases are needed not for generation but for a meaningful refusal -
    # otherwise the skill would answer a Russian spelling with "unknown type 'ОбщийМодуль'".
    "Перечисление": "Enum",
    "ОбщийМодуль": "CommonModule",
    "ОпределяемыйТип": "DefinedType",
    "ОбщаяКартинка": "CommonPicture",
    "ОбщийМакет": "CommonTemplate",
    "Язык": "Language",
    "ФункциональнаяОпция": "FunctionalOption",
    "ПараметрФункциональныхОпций": "FunctionalOptionsParameter",
    "ПодпискаНаСобытие": "EventSubscription",
    "РегламентноеЗадание": "ScheduledJob",
    "ЭлементСтиля": "StyleItem",
    "ХранилищеНастроек": "SettingsStorage",
    "ПакетXDTO": "XDTOPackage",
    "WSСсылка": "WSReference",
    "Нумератор": "DocumentNumerator",
    # Nested
    "Реквизит": "Attribute",
    "СтандартныйРеквизит": "StandardAttribute",
    "ТабличнаяЧасть": "TabularSection",
    "Измерение": "Dimension",
    "Ресурс": "Resource",
    "Команда": "Command",
    "РеквизитАдресации": "AddressingAttribute",
}

RIGHT_ALIASES = {
    "Чтение": "Read",
    "Добавление": "Insert",
    "Изменение": "Update",
    "Удаление": "Delete",
    "Просмотр": "View",
    "Редактирование": "Edit",
    "ВводПоСтроке": "InputByString",
    "Проведение": "Posting",
    "ОтменаПроведения": "UndoPosting",
    "ИнтерактивноеДобавление": "InteractiveInsert",
    "ИнтерактивнаяПометкаУдаления": "InteractiveSetDeletionMark",
    "ИнтерактивноеСнятиеПометкиУдаления": "InteractiveClearDeletionMark",
    "ИнтерактивноеУдаление": "InteractiveDelete",
    "ИнтерактивноеУдалениеПомеченных": "InteractiveDeleteMarked",
    "ИнтерактивноеПроведение": "InteractivePosting",
    "ИнтерактивноеПроведениеНеоперативное": "InteractivePostingRegular",
    "ИнтерактивнаяОтменаПроведения": "InteractiveUndoPosting",
    "ИнтерактивноеИзменениеПроведенных": "InteractiveChangeOfPosted",
    "Использование": "Use",
    "Получение": "Get",
    "Установка": "Set",
    "Старт": "Start",
    "ИнтерактивныйСтарт": "InteractiveStart",
    "ИнтерактивнаяАктивация": "InteractiveActivate",
    "Выполнение": "Execute",
    "ИнтерактивноеВыполнение": "InteractiveExecute",
    "УправлениеИтогами": "TotalsControl",
    "Администрирование": "Administration",
    "АдминистрированиеДанных": "DataAdministration",
    "ТонкийКлиент": "ThinClient",
    "ВебКлиент": "WebClient",
    "ТолстыйКлиент": "ThickClient",
    "ВнешнееСоединение": "ExternalConnection",
    "Вывод": "Output",
    "СохранениеДанныхПользователя": "SaveUserData",
    "МобильныйКлиент": "MobileClient",
}

# --- Known rights per object type ---

KNOWN_RIGHTS = {
    "Configuration": [
        "Administration", "DataAdministration", "UpdateDataBaseConfiguration",
        "ConfigurationExtensionsAdministration", "ActiveUsers", "EventLog", "ExclusiveMode",
        "ThinClient", "ThickClient", "WebClient", "MobileClient", "ExternalConnection",
        "Automation", "Output", "SaveUserData", "TechnicalSpecialistMode",
        "InteractiveOpenExtDataProcessors", "InteractiveOpenExtReports",
        "AnalyticsSystemClient", "CollaborationSystemInfoBaseRegistration",
        "MainWindowModeNormal", "MainWindowModeWorkplace",
        "MainWindowModeEmbeddedWorkplace", "MainWindowModeFullscreenWorkplace", "MainWindowModeKiosk",
    ],
    "Catalog": [
        "Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark",
        "InteractiveDelete", "InteractiveDeleteMarked",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData",
        "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "UpdateDataHistoryOfMissingData", "ReadDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "Document": [
        "Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString",
        "Posting", "UndoPosting",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark",
        "InteractiveDelete", "InteractiveDeleteMarked",
        "InteractivePosting", "InteractivePostingRegular", "InteractiveUndoPosting",
        "InteractiveChangeOfPosted",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "UpdateDataHistoryOfMissingData", "ReadDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "InformationRegister": [
        "Read", "Update", "View", "Edit", "TotalsControl",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "UpdateDataHistoryOfMissingData", "ReadDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "AccumulationRegister": ["Read", "Update", "View", "Edit", "TotalsControl"],
    "AccountingRegister": ["Read", "Update", "View", "Edit", "TotalsControl"],
    "CalculationRegister": [
        "Read", "Update", "View", "Edit",
    ],
    "Constant": [
        "Read", "Update", "View", "Edit",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "ChartOfAccounts": [
        "Read", "Insert", "Update", "Delete",
        "View", "Edit", "InputByString", "InteractiveInsert",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDelete", "InteractiveDeleteMarked",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "ChartOfCharacteristicTypes": [
        "Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark",
        "InteractiveDelete", "InteractiveDeleteMarked",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData",
        "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "ChartOfCalculationTypes": [
        "Read", "Insert", "Update", "Delete",
        "View", "Edit", "InputByString", "InteractiveInsert",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDelete", "InteractiveDeleteMarked",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "ExchangePlan": [
        "Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark",
        "InteractiveDelete", "InteractiveDeleteMarked",
        "ReadDataHistory", "ViewDataHistory", "UpdateDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "BusinessProcess": [
        "Read", "Insert", "Update", "Delete",
        "View", "Edit", "InputByString", "Start",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDelete",
        "InteractiveDeleteMarked", "InteractiveActivate", "InteractiveStart", "ReadDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings",
        "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "Task": [
        "Read", "Insert", "Update", "Delete",
        "View", "Edit", "InputByString", "Execute",
        "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDelete",
        "InteractiveDeleteMarked", "InteractiveActivate", "InteractiveExecute", "ReadDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings",
        "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "DataProcessor": ["Use", "View"],
    "Report": ["Use", "View"],
    "CommonForm": ["View"],
    "CommonCommand": ["View"],
    "Subsystem": ["View"],
    "FilterCriterion": ["View"],
    "DocumentJournal": ["Read", "View"],
    "Sequence": ["Read", "Update"],
    "WebService": ["Use"],
    "HTTPService": ["Use"],
    "IntegrationService": ["Use"],
    "SessionParameter": ["Get", "Set"],
    "CommonAttribute": ["View", "Edit"],
    "ExternalDataSource": [
        "Use", "Administration", "StandardAuthenticationChange",
        "SessionStandardAuthenticationChange", "SessionOSAuthenticationChange",
    ],
}

# Nested kinds (penultimate path segment) -> allowed rights. The lists were taken from a corpus of
# typical configurations and from a role dump where rights are set across the whole editor tree:
# no place for guesses here - a closed list turns a miss into a false rejection.
NESTED_KIND_RIGHTS = {
    "Attribute": ["View", "Edit"],
    "StandardAttribute": ["View", "Edit"],
    "TabularSection": ["View", "Edit"],
    "StandardTabularSection": ["View", "Edit"],
    "Dimension": ["View", "Edit"],
    "Resource": ["View", "Edit"],
    "AccountingFlag": ["View", "Edit"],
    "ExtDimensionAccountingFlag": ["View", "Edit"],
    "AddressingAttribute": ["View", "Edit"],
    "Field": ["View", "Edit"],
    "Command": ["View"],
    "Subsystem": ["View"],
    "Operation": ["Use"],
    "Method": ["Use"],
    "IntegrationServiceChannel": ["Use"],
    "Recalculation": ["Read", "Update"],
    "Cube": ["Read", "View"],
    "DimensionTable": ["Read", "View"],
    "Function": ["Use", "View"],
    "Table": [
        "Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString",
        "InteractiveInsert", "InteractiveDelete",
    ],
}

# Kinds that exist only under one parent type: without this binding
# `Catalog.Товары.Field.Цена` would pass as a valid nested object.
KIND_OWNERS = {
    'Table': 'ExternalDataSource',
    'Cube': 'ExternalDataSource',
    'Function': 'ExternalDataSource',
    'Field': 'ExternalDataSource',
    'DimensionTable': 'ExternalDataSource',
    'Recalculation': 'CalculationRegister',
    'Operation': 'WebService',
    'Method': 'HTTPService',
    'IntegrationServiceChannel': 'IntegrationService',
}

# A right on a service lives on the LEAF - the URL template method, operation, channel - not on the
# service itself: there is no root node in any typical role (907 corpus records - zero), and in the
# Configurator there is no checkbox on the root at all. The short entry `HTTPService.X: Use` expresses
# the intent "open the service as a whole" and is expanded into leaves using the service metadata.
SERVICE_LEAVES = {
    'WebService': {'dir': 'WebServices', 'kinds': ['Operation']},
    'HTTPService': {'dir': 'HTTPServices', 'kinds': ['URLTemplate', 'Method']},
    'IntegrationService': {'dir': 'IntegrationServices', 'kinds': ['IntegrationServiceChannel']},
}

# The same kind under different parents has a different set: a register dimension -
# View + Edit, an external data source cube dimension - View only. Do not merge them:
# merging would silently allow Edit where the platform does not grant it.
NESTED_KIND_RIGHTS_BY_TYPE = {
    "ExternalDataSource": {
        "Dimension": ["View"],
        "Resource": ["View"],
    },
}

# Types without rights in roles (they are absent from the role editor tree). The list does NOT drive
# behavior - rejection comes from the type missing in KNOWN_RIGHTS; here it only chooses the wording.
NO_RIGHTS_TYPES = [
    "Enum", "CommonModule", "DefinedType", "CommonPicture", "CommonTemplate", "Language",
    "FunctionalOption", "FunctionalOptionsParameter", "EventSubscription", "ScheduledJob",
    "StyleItem", "Style", "SettingsStorage", "XDTOPackage", "WSReference", "DocumentNumerator",
]

# --- Presets ---

PRESETS = {
    "view": {
        "Catalog": ["Read", "View", "InputByString"],
        "ExchangePlan": ["Read", "View", "InputByString"],
        "Document": ["Read", "View", "InputByString"],
        "ChartOfAccounts": ["Read", "View", "InputByString"],
        "ChartOfCharacteristicTypes": ["Read", "View", "InputByString"],
        "ChartOfCalculationTypes": ["Read", "View", "InputByString"],
        "BusinessProcess": ["Read", "View", "InputByString"],
        "Task": ["Read", "View", "InputByString"],
        "InformationRegister": ["Read", "View"],
        "AccumulationRegister": ["Read", "View"],
        "AccountingRegister": ["Read", "View"],
        "CalculationRegister": ["Read", "View"],
        "Constant": ["Read", "View"],
        "DocumentJournal": ["Read", "View"],
        "Sequence": ["Read"],
        "CommonForm": ["View"],
        "CommonCommand": ["View"],
        "Subsystem": ["View"],
        "FilterCriterion": ["View"],
        "SessionParameter": ["Get"],
        "CommonAttribute": ["View"],
        "DataProcessor": ["Use", "View"],
        "Report": ["Use", "View"],
        "Configuration": ["ThinClient", "WebClient", "Output", "SaveUserData", "MainWindowModeNormal"],
    },
    "edit": {
        "Catalog": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark"],
        "ExchangePlan": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark"],
        "Document": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "Posting", "UndoPosting", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractivePosting", "InteractivePostingRegular", "InteractiveUndoPosting", "InteractiveChangeOfPosted"],
        "ChartOfAccounts": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark"],
        "ChartOfCharacteristicTypes": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark"],
        "ChartOfCalculationTypes": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark"],
        "BusinessProcess": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "Start", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveActivate", "InteractiveStart"],
        "Task": ["Read", "Insert", "Update", "Delete", "View", "Edit", "InputByString", "Execute", "InteractiveInsert", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveActivate", "InteractiveExecute"],
        "InformationRegister": ["Read", "Update", "View", "Edit"],
        "AccumulationRegister": ["Read", "Update", "View", "Edit"],
        "AccountingRegister": ["Read", "Update", "View", "Edit"],
        "Constant": ["Read", "Update", "View", "Edit"],
        "DocumentJournal": ["Read", "View"],
        "Sequence": ["Read", "Update"],
        "SessionParameter": ["Get", "Set"],
        "CommonAttribute": ["View", "Edit"],
    },
}


def translate_object_name(name):
    parts = name.split('.')
    result = []
    for p in parts:
        result.append(TYPE_ALIASES.get(p, p))
    return '.'.join(result)


def translate_right_name(name):
    return RIGHT_ALIASES.get(name, name)


def get_object_type(object_name):
    dot_idx = object_name.find('.')
    if dot_idx < 0:
        return object_name
    return object_name[:dot_idx]


def is_nested_object(object_name):
    return len(object_name.split('.')) >= 3


def get_nested_kind(object_name):
    """Nested kind - the penultimate segment: a path can have eight segments
    (ExternalDataSource.И.Cube.К.DimensionTable.Т.Field.П), so count from the end."""
    parts = object_name.split('.')
    if len(parts) < 3:
        return None
    return parts[-2]


def get_nested_rights(object_type, kind):
    by_type = NESTED_KIND_RIGHTS_BY_TYPE.get(object_type)
    if by_type and kind in by_type:
        return by_type[kind]
    return NESTED_KIND_RIGHTS.get(kind)


# --- Right dependencies (measured on the platform) ---
# On load the platform itself closes the set: granted Edit - got Read, Update and View as well.
# We write the closure immediately, otherwise the file and the infobase diverge.
# The table is common to types; exceptions are where a type has its own mechanics (data processor and report
# rely on Use, chart of accounts does not pull Read under data history).
RIGHT_DEPS = {
    "Delete": ["Read"],
    "Edit": ["Read", "Update", "View"],
    "EditDataHistoryVersionComment": ["Read", "ReadDataHistory", "UpdateDataHistoryVersionComment", "View"],
    "Execute": ["Read", "Update"],
    "InputByString": ["Read", "View"],
    "Insert": ["Read"],
    "InteractiveActivate": ["Read", "Update"],
    "InteractiveChangeOfPosted": ["Edit", "Read", "Update", "View"],
    "InteractiveClearDeletionMark": ["Edit", "Read", "Update", "View"],
    "InteractiveClearDeletionMarkPredefinedData": ["Edit", "InteractiveClearDeletionMark", "Read", "Update", "View"],
    "InteractiveDelete": ["Delete", "Edit", "Read", "Update", "View"],
    "InteractiveDeleteMarked": ["Delete", "Edit", "Read", "Update", "View"],
    "InteractiveDeleteMarkedPredefinedData": ["Delete", "Edit", "InteractiveDeleteMarked", "Read", "Update", "View"],
    "InteractiveDeletePredefinedData": ["Delete", "Edit", "InteractiveDelete", "Read", "Update", "View"],
    "InteractiveExecute": ["Execute", "Read", "Update"],
    "InteractiveInsert": ["Edit", "Insert", "Read", "Update", "View"],
    "InteractivePosting": ["Edit", "Posting", "Read", "Update", "View"],
    "InteractivePostingRegular": ["Edit", "InteractivePosting", "Posting", "Read", "Update", "View"],
    "InteractiveSetDeletionMark": ["Edit", "Read", "Update", "View"],
    "InteractiveSetDeletionMarkPredefinedData": ["Edit", "InteractiveSetDeletionMark", "Read", "Update", "View"],
    "InteractiveStart": ["Read", "Start", "Update"],
    "InteractiveUndoPosting": ["Edit", "Read", "UndoPosting", "Update", "View"],
    "Posting": ["Read", "Update"],
    "ReadDataHistory": ["Read"],
    "ReadDataHistoryOfMissingData": ["Read", "ReadDataHistory"],
    "Start": ["Read", "Update"],
    "SwitchToDataHistoryVersion": ["Read", "View"],
    "UndoPosting": ["Read", "Update"],
    "Update": ["Read"],
    "UpdateDataHistory": ["Read", "ReadDataHistory"],
    "UpdateDataHistoryOfMissingData": ["Read", "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory"],
    "UpdateDataHistoryVersionComment": ["Read", "ReadDataHistory"],
    "View": ["Read"],
    "ViewDataHistory": ["Read", "ReadDataHistory", "View"],
}

RIGHT_DEPS_BY_TYPE = {
    "ChartOfAccounts": {
        "ReadDataHistory": [],
        "ReadDataHistoryOfMissingData": ["ReadDataHistory"],
        "UpdateDataHistory": ["ReadDataHistory"],
        "UpdateDataHistoryOfMissingData": ["ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory"],
        "UpdateDataHistoryVersionComment": ["ReadDataHistory"],
    },
    "DataProcessor": {
        "View": ["Use"],
    },
    "InformationRegister": {
        "UpdateDataHistoryOfMissingData": ["Read", "ReadDataHistory", "UpdateDataHistory"],
    },
    "Report": {
        "View": ["Use"],
    },
}

CONFIGURATION_LEGACY_DEPS = ["AnalyticsSystemClient", "MainWindowModeEmbeddedWorkplace", "MainWindowModeFullscreenWorkplace", "MainWindowModeKiosk", "MainWindowModeNormal", "MainWindowModeWorkplace"]

# Configuration rights: before format 2.19 the platform set the whole window mode block together with
# any right; since 2.19 (8.3.26) it stopped. The rights themselves are valid in both.
CONFIGURATION_LEGACY_RANK = 218


# The platform stores only what DIFFERS from the role default: with
# setForNewObjects=false permissions live at the top level; with true - denials; for attribute
# nested objects the same role is played by setForAttributesByDefault. What matches the default
# the platform discards on the first load, so we do not write it either.
ATTRIBUTE_KINDS = [
    "Attribute", "StandardAttribute", "TabularSection", "StandardTabularSection",
    "Dimension", "Resource", "AccountingFlag", "ExtDimensionAccountingFlag", "AddressingAttribute",
]


def get_default_right_value(object_name, set_for_new_objects, set_for_attributes_by_default):
    parts = object_name.split('.')
    if len(parts) < 3:
        return set_for_new_objects
    # External data sources were not checked against this rule - touch only what was measured.
    if parts[0] == 'ExternalDataSource':
        return "false"
    kind = parts[-2]
    if kind in ATTRIBUTE_KINDS:
        return set_for_attributes_by_default
    # Commands, subsystems, service operations are not controlled by role flags - permissions live there.
    return "false"


def close_rights_dependencies(object_name, rights, format_rank):
    """Closure of an object's right set. Returns (final rights, what was added)."""
    parts = object_name.split('.')
    nested = len(parts) >= 3
    object_type = parts[0]
    allowed = (get_nested_rights(object_type, get_nested_kind(object_name)) if nested
               else KNOWN_RIGHTS.get(object_type))
    if not allowed:
        return rights, []
    have = {}
    for r in rights:
        have.setdefault(r['Name'], r)
    by_type = RIGHT_DEPS_BY_TYPE.get(object_type, {})
    added = []
    # Forward - only from ALLOWED rights: the platform closes what is granted, not what is denied.
    queue = [n for n in have if have[n]['Value'] == 'true']
    while queue:
        name = queue.pop(0)
        need = by_type[name] if name in by_type else RIGHT_DEPS.get(name)
        if not need:
            continue
        for dep in need:
            if dep not in allowed:
                continue
            if dep in have:
                # A permission overrides a denial - that is what the platform does on load too.
                if have[dep]['Value'] != 'true':
                    have[dep]['Value'] = 'true'
                    added.append(dep)
                    queue.append(dep)
                continue
            have[dep] = {'Name': dep, 'Value': 'true', 'Condition': None}
            added.append(dep)
            queue.append(dep)
    # Backward - from DENIALS: a right that a denied one needs is denied by the platform as well.
    deny_queue = [n for n in have if have[n]['Value'] != 'true']
    while deny_queue:
        name = deny_queue.pop(0)
        for candidate in allowed:
            if candidate == name or candidate in have:
                continue
            need = by_type[candidate] if candidate in by_type else RIGHT_DEPS.get(candidate)
            if not need or name not in need:
                continue
            have[candidate] = {'Name': candidate, 'Value': 'false', 'Condition': None}
            added.append(candidate)
            deny_queue.append(candidate)
    if object_type == 'Configuration' and format_rank <= CONFIGURATION_LEGACY_RANK and have:
        for dep in CONFIGURATION_LEGACY_DEPS:
            if dep in have:
                continue
            have[dep] = {'Name': dep, 'Value': 'true', 'Condition': None}
            added.append(dep)
    return list(have.values()), added


# --- Canonical order of rights and nodes (measured on the platform) ---
# The platform normalizes the order of <right> inside <object> and the order of the <object>s themselves:
# rights go in a fixed per-type order, nodes - by the metadata object uuid.
# We write it the same way right away, otherwise the first dump from the Configurator gives a diff out of nowhere.
RIGHT_ORDER = {
    "AccountingRegister": ["Read", "Update", "View", "Edit", "TotalsControl"],
    "AccumulationRegister": ["Read", "Update", "View", "Edit", "TotalsControl"],
    "BusinessProcess": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveActivate", "Start", "InteractiveStart", "ReadDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings",
        "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "CalculationRegister": ["Read", "Update", "View", "Edit"],
    "Catalog": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "ChartOfAccounts": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "ChartOfCalculationTypes": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "ChartOfCharacteristicTypes": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveDeletePredefinedData", "InteractiveSetDeletionMarkPredefinedData", "InteractiveClearDeletionMarkPredefinedData", "InteractiveDeleteMarkedPredefinedData",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "CommonAttribute": ["View", "Edit"],
    "CommonCommand": ["View"],
    "CommonForm": ["View"],
    "Configuration": [
        "Administration", "DataAdministration", "UpdateDataBaseConfiguration", "ExclusiveMode",
        "ActiveUsers", "EventLog", "ThinClient", "WebClient",
        "MobileClient", "ThickClient", "ExternalConnection", "Automation",
        "TechnicalSpecialistMode", "CollaborationSystemInfoBaseRegistration", "MainWindowModeNormal", "MainWindowModeWorkplace",
        "MainWindowModeEmbeddedWorkplace", "MainWindowModeFullscreenWorkplace", "MainWindowModeKiosk", "AnalyticsSystemClient",
        "SaveUserData", "ConfigurationExtensionsAdministration", "InteractiveOpenExtDataProcessors", "InteractiveOpenExtReports",
        "Output",
    ],
    "Constant": [
        "Read", "Update", "View", "Edit",
        "ReadDataHistory", "UpdateDataHistory", "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "DataProcessor": ["Use", "View"],
    "Document": [
        "Read", "Insert", "Update", "Delete",
        "Posting", "UndoPosting", "View", "InteractiveInsert",
        "Edit", "InteractiveDelete", "InteractiveSetDeletionMark", "InteractiveClearDeletionMark",
        "InteractiveDeleteMarked", "InteractivePosting", "InteractivePostingRegular", "InteractiveUndoPosting",
        "InteractiveChangeOfPosted", "InputByString", "ReadDataHistory", "ReadDataHistoryOfMissingData",
        "UpdateDataHistory", "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment",
        "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "DocumentJournal": ["Read", "View"],
    "ExchangePlan": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData",
        "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment",
        "SwitchToDataHistoryVersion",
    ],
    "FilterCriterion": ["View"],
    "HTTPService": ["Use"],
    "InformationRegister": [
        "Read", "Update", "View", "Edit",
        "TotalsControl", "ReadDataHistory", "ReadDataHistoryOfMissingData", "UpdateDataHistory",
        "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings", "UpdateDataHistoryVersionComment", "ViewDataHistory",
        "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "IntegrationService": ["Use"],
    "Report": ["Use", "View"],
    "Sequence": ["Read", "Update"],
    "SessionParameter": ["Get", "Set"],
    "Subsystem": ["View"],
    "Task": [
        "Read", "Insert", "Update", "Delete",
        "View", "InteractiveInsert", "Edit", "InteractiveDelete",
        "InteractiveSetDeletionMark", "InteractiveClearDeletionMark", "InteractiveDeleteMarked", "InputByString",
        "InteractiveActivate", "Execute", "InteractiveExecute", "ReadDataHistory",
        "ReadDataHistoryOfMissingData", "UpdateDataHistory", "UpdateDataHistoryOfMissingData", "UpdateDataHistorySettings",
        "UpdateDataHistoryVersionComment", "ViewDataHistory", "EditDataHistoryVersionComment", "SwitchToDataHistoryVersion",
    ],
    "WebService": ["Use"],
}

NESTED_RIGHT_ORDER = {
    "AccountingFlag": ["View", "Edit"],
    "AddressingAttribute": ["View", "Edit"],
    "Attribute": ["View", "Edit"],
    "Command": ["View"],
    "Dimension": ["View", "Edit"],
    "ExtDimensionAccountingFlag": ["View", "Edit"],
    "IntegrationServiceChannel": ["Use"],
    "Method": ["Use"],
    "Operation": ["Use"],
    "Recalculation": ["Read", "Update"],
    "Resource": ["View", "Edit"],
    "StandardAttribute": ["View", "Edit"],
    "StandardTabularSection": ["View", "Edit"],
    "Subsystem": ["View"],
    "TabularSection": ["View", "Edit"],
}

# Metadata object directories - needed to read the uuid and place <object> nodes.
TYPE_DIRS = {
    "Catalog": "Catalogs", "Document": "Documents", "DocumentJournal": "DocumentJournals",
    "Sequence": "Sequences", "Constant": "Constants", "Report": "Reports",
    "DataProcessor": "DataProcessors", "InformationRegister": "InformationRegisters",
    "AccumulationRegister": "AccumulationRegisters", "AccountingRegister": "AccountingRegisters",
    "CalculationRegister": "CalculationRegisters", "ChartOfAccounts": "ChartsOfAccounts",
    "ChartOfCharacteristicTypes": "ChartsOfCharacteristicTypes",
    "ChartOfCalculationTypes": "ChartsOfCalculationTypes", "ExchangePlan": "ExchangePlans",
    "BusinessProcess": "BusinessProcesses", "Task": "Tasks", "Subsystem": "Subsystems",
    "CommonForm": "CommonForms", "CommonCommand": "CommonCommands",
    "CommonAttribute": "CommonAttributes", "FilterCriterion": "FilterCriteria",
    "SessionParameter": "SessionParameters", "WebService": "WebServices",
    "HTTPService": "HTTPServices", "IntegrationService": "IntegrationServices",
    "ExternalDataSource": "ExternalDataSources",
}


def sort_rights_canonical(object_name, rights):
    """Order of object rights: known ones - by the table, unknown ones - after them, in input order."""
    parts = object_name.split('.')
    order = NESTED_RIGHT_ORDER.get(parts[-2]) if len(parts) >= 3 else RIGHT_ORDER.get(parts[0])
    if not order:
        return rights
    by_name = {}
    for r in rights:
        by_name.setdefault(r['Name'], r)
    sorted_rights = []
    for name in order:
        if name in by_name:
            sorted_rights.append(by_name.pop(name))
    for r in rights:
        if r['Name'] in by_name:
            sorted_rights.append(by_name.pop(r['Name']))
    return sorted_rights


# Standard attributes and standard tabular sections have no uuid in the dump: they are system ones.
# The absence of a uuid for them is normal, not a lost object.
def is_standard_kind(object_name):
    parts = object_name.split('.')
    if len(parts) < 3:
        return False
    return parts[-2].startswith("Standard")


# uuid of the rights object: for the top level - from the object file, for a nested one - by descending the tree.
# Searching the whole file with a regex is not allowed: a header attribute and a tabular section attribute are often
# named the same, and the search would find the first one it meets. Child subsystems are stored
# in separate files, so for them the descent goes through directories.
# Standard attributes have no uuid in the dump at all - return None silently for them.
def get_rights_object_uuid(object_name, config_root):
    parts = object_name.split('.')
    if parts[0] == 'Configuration':
        cfg_path = os.path.join(config_root, 'Configuration.xml')
        if not os.path.isfile(cfg_path):
            return None
        with open(cfg_path, 'r', encoding='utf-8-sig') as f:
            m = re.search(r'<Configuration uuid="([0-9a-fA-F-]+)"', f.read())
        return m.group(1) if m else None
    directory = TYPE_DIRS.get(parts[0])
    if not directory or len(parts) < 2:
        return None
    # Subsystems are nested by directories: Subsystems/Родитель/Subsystems/Ребёнок.xml
    owner_path = os.path.join(config_root, directory, parts[1] + '.xml')
    i = 2
    while len(parts) > i + 1 and parts[i] == 'Subsystem':
        owner_path = os.path.join(os.path.splitext(owner_path)[0], 'Subsystems', parts[i + 1] + '.xml')
        i += 2
    if not os.path.isfile(owner_path):
        return None
    try:
        tree = etree.parse(owner_path)
    except Exception:
        return None
    md = '{http://v8.1c.ru/8.3/MDClasses}'
    node = tree.getroot()[0] if len(tree.getroot()) else None
    if node is None:
        return None
    # The remaining "kind, name" pairs are looked up strictly inside the current node.
    while i + 1 < len(parts):
        kind, name = parts[i], parts[i + 1]
        child = None
        for candidate in node.findall(f'{md}ChildObjects/{md}{kind}'):
            props = candidate.find(f'{md}Properties/{md}Name')
            if props is not None and (props.text or '') == name:
                child = candidate
                break
        if child is None:
            return None
        node = child
        i += 2
    return node.get('uuid')


def sort_objects_by_uuid(objects, config_root):
    """Node order: by object uuid; unresolved ones - at the end, in input order."""
    known, unknown = [], []
    for o in objects:
        uuid_value = get_rights_object_uuid(o['Name'], config_root)
        if uuid_value:
            known.append((uuid_value, o))
        else:
            if not is_standard_kind(o['Name']):
                print(f"[role-compile] {o['Name']}: объект не найден в выгрузке, uuid неизвестен — "
                      f"узел записан в конец (платформа переставит его при первой выгрузке)",
                      file=sys.stderr)
            unknown.append(o)
    known.sort(key=lambda pair: pair[0])
    return [o for _, o in known] + unknown


# Errors accumulate rather than print immediately: the role is written as a whole, so the only
# safe moment to refuse is before the first write, and all reasons must be shown at once.
VALIDATION_ERRORS = []


def add_validation_error(message):
    VALIDATION_ERRORS.append(message)


def validate_object_name(object_name):
    """Type by the white list (always, including nested paths) and the nested kind.
    A forbidden and an unknown type are different diagnoses."""
    object_type = get_object_type(object_name)
    if object_type not in KNOWN_RIGHTS:
        if object_type in NO_RIGHTS_TYPES:
            add_validation_error(f"{object_name}: тип '{object_type}' не имеет прав в роли — уберите объект из списка")
        else:
            similar = [t for t in KNOWN_RIGHTS if object_type in t or t in object_type][:3]
            sug = f" Возможно: {', '.join(similar)}?" if similar else ''
            add_validation_error(f"{object_name}: неизвестный тип объекта '{object_type}'.{sug}")
        return False

    if is_nested_object(object_name):
        kind = get_nested_kind(object_name)
        if kind in KIND_OWNERS and object_type != KIND_OWNERS[kind]:
            add_validation_error(f"{object_name}: вид '{kind}' бывает только у {KIND_OWNERS[kind]}")
            return False
        if get_nested_rights(object_type, kind) is None:
            add_validation_error(f"{object_name}: неизвестный вид вложенности '{kind}'")
            return False

    return True


def resolve_preset(object_type, preset_name):
    preset = preset_name.lstrip('@')
    if preset not in PRESETS:
        print(f"WARNING: Unknown preset '@{preset}'. Known: @view, @edit", file=sys.stderr)
        return []
    type_map = PRESETS[preset]
    if object_type not in type_map:
        available = []
        for k in PRESETS:
            if object_type in PRESETS[k]:
                available.append(f'@{k}')
        avail_str = ', '.join(available) if available else 'none'
        print(f"WARNING: Preset '@{preset}' not defined for type '{object_type}'. Available: {avail_str}", file=sys.stderr)
        return []
    return list(type_map[object_type])


def validate_right_name(object_name, right_name):
    object_type = get_object_type(object_name)

    # The type was already checked by validate_object_name - here only rights, otherwise a single
    # forbidden type would print as many lines as it has rights listed.
    if object_type not in KNOWN_RIGHTS:
        return False

    if is_nested_object(object_name):
        kind = get_nested_kind(object_name)
        valid_nested = get_nested_rights(object_type, kind)
        if valid_nested is None:
            return False
        if right_name not in valid_nested:
            add_validation_error(f"{object_name}: право '{right_name}' недопустимо для вида '{kind}' (допустимо: {', '.join(valid_nested)})")
            return False
        return True

    valid_rights = KNOWN_RIGHTS[object_type]
    if right_name not in valid_rights:
        suggestions = [r for r in valid_rights if right_name in r or r in right_name][:3]
        sug_str = f" Возможно: {', '.join(suggestions)}?" if suggestions else ""
        add_validation_error(f"{object_name}: право '{right_name}' не существует у типа '{object_type}'.{sug_str}")
        return False

    return True


# "@path" in a condition value - the text is taken from a file: typical RLS conditions take tens of
# lines with quotes, and inside a JSON string that is a source of escaping errors. A relative
# path is looked up next to the role JSON definition, then in the current directory.
def resolve_text_from_file(val, base_dir):
    if not val.startswith("@"):
        return val
    file_path = val[1:]
    if os.path.isabs(file_path):
        candidates = [file_path]
    else:
        candidates = [
            os.path.join(base_dir, file_path),
            os.path.join(os.getcwd(), file_path),
        ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, 'r', encoding='utf-8-sig') as f:
                return f.read().rstrip()
    print(f"Файл значения не найден: {file_path} (искали: {', '.join(candidates)})", file=sys.stderr)
    sys.exit(1)


TEXT_BASE_DIR = os.getcwd()


MD_NS = 'http://v8.1c.ru/8.3/MDClasses'

# Service metadata are read once per name: expansion and adoption check
# ask for the same file.
SERVICE_META_CACHE = {}


def get_service_meta(object_type, service_name, config_root):
    key = f"{object_type}.{service_name}"
    if key in SERVICE_META_CACHE:
        return SERVICE_META_CACHE[key]

    spec = SERVICE_LEAVES[object_type]
    xml_path = os.path.join(config_root, spec['dir'], f"{service_name}.xml")
    result = {'path': xml_path, 'found': False, 'adopted': False, 'leaves': []}

    if os.path.isfile(xml_path):
        try:
            root = etree.parse(xml_path).getroot()
            node = root.find(f"{{{MD_NS}}}{object_type}")
            if node is not None:
                result['found'] = True
                # ObjectBelonging=Adopted - the service is borrowed into the extension.
                ob = node.find(f"{{{MD_NS}}}Properties/{{{MD_NS}}}ObjectBelonging")
                if ob is not None and (ob.text or '') == 'Adopted':
                    result['adopted'] = True

                # Descend by kinds: in an HTTP service the leaf lies two levels down
                # (URLTemplate -> Method), in the others - one.
                level = [(node, f"{object_type}.{service_name}")]
                for kind in spec['kinds']:
                    nxt = []
                    for item_node, item_name in level:
                        for child in item_node.findall(f"{{{MD_NS}}}ChildObjects/{{{MD_NS}}}{kind}"):
                            name_node = child.find(f"{{{MD_NS}}}Properties/{{{MD_NS}}}Name")
                            if name_node is None:
                                continue
                            nxt.append((child, f"{item_name}.{kind}.{name_node.text}"))
                    level = nxt
                result['leaves'] = [n for _, n in level]
        except Exception:
            # Broken XML is not our concern: there is nothing to expand, then the refusal
            # "metadata not found" will work with the same path in the hint.
            pass

    SERVICE_META_CACHE[key] = result
    return result


def get_service_leaf_hint(object_type, service_name):
    """Format hint: the only thing that differs among the three service kinds is the path to the leaf."""
    if object_type == 'HTTPService':
        return f"{object_type}.{service_name}.URLTemplate.<Шаблон>.Method.<Метод>: Use"
    if object_type == 'WebService':
        return f"{object_type}.{service_name}.Operation.<Операция>: Use"
    return f"{object_type}.{service_name}.IntegrationServiceChannel.<Канал>: Use"


# An extension role included in <DefaultRoles> cannot grant rights on borrowed objects -
# the platform answers «Назначение прав доступа на заимствованные объекты основными
# ролями в расширениях недопустимо». Count once: the role name does not change during a run.
IS_DEFAULT_ROLE = None


def test_default_role(config_root, name):
    global IS_DEFAULT_ROLE
    if IS_DEFAULT_ROLE is not None:
        return IS_DEFAULT_ROLE
    IS_DEFAULT_ROLE = False

    cfg_path = os.path.join(config_root, 'Configuration.xml')
    if os.path.isfile(cfg_path):
        with open(cfg_path, 'r', encoding='utf-8-sig') as f:
            text = f.read()
        # Extension only: for a regular configuration DefaultRoles means something else and there is no ban.
        if '<ConfigurationExtensionPurpose>' in text:
            m = re.search(r'<DefaultRoles>(.*?)</DefaultRoles>', text, re.S)
            # Comparison is CASE-SENSITIVE, otherwise "расш1_роль1" would pass as the main role
            # "Расш1_Роль1".
            if m and re.search(re.escape(f"Role.{name}") + r'\s*<', m.group(1)):
                IS_DEFAULT_ROLE = True
    return IS_DEFAULT_ROLE


def expand_service_entry(parsed, config_root, name):
    """Returns a list of entries to replace the original: the service root is expanded into leaves,
    everything else passes as is."""
    obj_name = parsed['Name']
    object_type = get_object_type(obj_name)
    if object_type not in SERVICE_LEAVES:
        return [parsed]

    parts = obj_name.split('.')
    if len(parts) < 2:
        return [parsed]
    service_name = parts[1]
    meta = get_service_meta(object_type, service_name, config_root)

    if meta['adopted'] and test_default_role(config_root, name):
        add_validation_error(
            f"{obj_name}: '{name}' — основная роль расширения (входит в DefaultRoles), "
            f"а {object_type}.{service_name} заимствован; назначать права на заимствованные объекты "
            "основными ролями расширения платформа запрещает. Заведите отдельную роль и не включайте её в основные.")
        return []

    # The user specified the full path - there is nothing to expand.
    if len(parts) > 2:
        return [parsed]

    hint = get_service_leaf_hint(object_type, service_name)
    if not meta['found']:
        add_validation_error(
            f"{obj_name}: метаданные сервиса не найдены ({meta['path']}); "
            f"право на сервис целиком платформа игнорирует — укажите листья явно: {hint}")
        return []
    if not meta['leaves']:
        add_validation_error(
            f"{obj_name}: у сервиса нет ни одного вложенного объекта, раскрывать нечего; "
            "право на сервис целиком платформа игнорирует. "
            f"Для заимствованного сервиса заимствуйте нужные методы, затем: {hint}")
        return []

    expanded = [{'Name': leaf, 'Rights': parsed['Rights']} for leaf in meta['leaves']]
    print(f"     {obj_name} -> раскрыт (вложенных объектов: {len(expanded)})")
    return expanded


def parse_object_entry(entry):
    # --- String shorthand ---
    if isinstance(entry, str):
        colon_idx = entry.find(':')
        if colon_idx < 0:
            print(f"WARNING: Invalid string '{entry}' -- expected 'Object.Name: @preset' or 'Object.Name: Right1, Right2'", file=sys.stderr)
            return None
        obj_name = translate_object_name(entry[:colon_idx].strip())
        rights_str = entry[colon_idx + 1:].strip()
        # Do not parse further an object with an invalid name: a preset for a non-existent type
        # would add a meaningless warning to the refusal.
        if not validate_object_name(obj_name):
            return None
        object_type = get_object_type(obj_name)

        if rights_str.startswith('@'):
            right_names = resolve_preset(object_type, rights_str)
        else:
            right_names = [translate_right_name(r.strip()) for r in rights_str.split(',') if r.strip()]
            for r in right_names:
                validate_right_name(obj_name, r)

        rights = []
        for r in right_names:
            rights.append({'Name': r, 'Value': 'true', 'Condition': None})
        return {'Name': obj_name, 'Rights': rights}

    # --- Object form ---
    obj_name = translate_object_name(str(entry.get('name', '')))
    if not obj_name:
        print("WARNING: Object entry missing 'name' field", file=sys.stderr)
        return None

    if not validate_object_name(obj_name):
        return None

    object_type = get_object_type(obj_name)
    # Use a list of tuples to preserve insertion order
    rights_map = {}  # name -> {Value, Condition}
    rights_order = []  # preserve order

    # 1) Start with preset
    if entry.get('preset'):
        preset_rights = resolve_preset(object_type, str(entry['preset']))
        for r in preset_rights:
            if r not in rights_map:
                rights_order.append(r)
            rights_map[r] = {'Value': 'true', 'Condition': None}

    # 2) Apply explicit rights
    if entry.get('rights') is not None:
        if isinstance(entry['rights'], list):
            for r in entry['rights']:
                r_name = translate_right_name(str(r))
                validate_right_name(obj_name, r_name)
                if r_name not in rights_map:
                    rights_order.append(r_name)
                rights_map[r_name] = {'Value': 'true', 'Condition': None}
        elif isinstance(entry['rights'], dict):
            for p_name, p_value in entry['rights'].items():
                r_name = translate_right_name(p_name)
                validate_right_name(obj_name, r_name)
                bool_val = 'true' if p_value is True or str(p_value) == 'True' else 'false'
                if r_name not in rights_map:
                    rights_order.append(r_name)
                rights_map[r_name] = {'Value': bool_val, 'Condition': None}

    # 3) Apply RLS conditions
    if entry.get('rls'):
        for p_name, p_value in entry['rls'].items():
            rls_right = translate_right_name(p_name)
            if rls_right in rights_map:
                rights_map[rls_right]['Condition'] = resolve_text_from_file(str(p_value), TEXT_BASE_DIR)
            else:
                print(f"WARNING: {obj_name}: RLS for '{rls_right}' but this right is not in the rights list", file=sys.stderr)

    # Convert to array
    rights = []
    for k in rights_order:
        rights.append({
            'Name': k,
            'Value': rights_map[k]['Value'],
            'Condition': rights_map[k]['Condition'],
        })

    return {'Name': obj_name, 'Rights': rights}


def get_new_object_position(cfg_dir):
    """Where the skill places a new entry in <ChildObjects> - the newObjectPosition setting.

    databases[].newObjectPosition of the database whose configSrc covers the parent XML directory,
    otherwise the root field, otherwise end. Values: end - after the last object of the same kind
    (that is how the Configurator appends); byName - by name among objects of the same kind.
    We search the file from the working directory upward, the configuration directory - as a fallback: the same way
    support-guard and the db-* group search it, and the skill script is called by an absolute path, and cwd
    remains the project working directory.
    configSrc is counted from the .v8-project.json directory, as documented in
    docs/v8-project-guide.md. Family registry: tests/skills/check-inline-drift.mjs.
    """
    try:
        pj = _sg_find_v8project(os.getcwd()) or _sg_find_v8project(os.path.abspath(cfg_dir or "."))
        if not pj:
            return "end"
        proj = json.loads(open(pj, encoding="utf-8-sig").read())
        proj_dir = os.path.dirname(pj)
        cfg_full = os.path.normcase(os.path.abspath(cfg_dir or ".")).rstrip("\\/")
        for db in proj.get("databases", []):
            src = db.get("configSrc")
            if src and db.get("newObjectPosition"):
                src_full = os.path.normcase(os.path.abspath(os.path.join(proj_dir, src))).rstrip("\\/")
                if cfg_full == src_full or cfg_full.startswith(src_full + os.sep):
                    return "byName" if str(db["newObjectPosition"]).lower() == "byname" else "end"
        if str(proj.get("newObjectPosition") or "").lower() == "byname":
            return "byName"
        return "end"
    except Exception:
        return "end"


def is_order_sensitive_type(type_name):
    """Kinds whose order in the tree carries meaning: we do not sort them automatically.

    CommonAttribute is an exception from the standard itself (#std467): for common divider attributes
    the order in the tree sets the order of session parameter assignment. Subsystem and CommandGroup:
    until they are listed in <SubsystemsOrder> / <GroupsOrder> of the Ext/CommandInterface.xml file,
    the tree order sets the interface order, and the platform does not create these lists itself
    (in the ACC dump, outside GroupsOrder there are 15 live groups out of 39). Language is excluded out of caution,
    without measurement: there are usually one or two languages, and in typical configurations their order is not alphabetical.
    An explicitly named kind is sorted in any case.
    Family registry: tests/skills/check-inline-drift.mjs.
    """
    return type_name in ("CommonAttribute", "Subsystem", "CommandGroup", "Language")


def compare_metadata_names(a, b):
    """Order of metadata object names, as in the Configurator tree.

    The key is "rank+char" pairs: case is ignored, underscore before digits, digits before
    letters, letters by code (Latin before Cyrillic), ё in place of е. Cultural tables are not
    used - they differ across OSes and runtimes, while this way both ports compare
    identically everywhere. Equal keys are separated by ordinal comparison of the source strings.
    Returns -1 | 0 | 1. Family registry: tests/skills/check-inline-drift.mjs.
    """
    keys = []
    for name in (a, b):
        parts = []
        for ch in name.lower():
            if ch == "ё":
                ch = "е"
            if ch.isdigit():
                parts.append("1" + ch)
            elif ch.isalpha():
                parts.append("2" + ch)
            else:
                parts.append("0" + ch)
        keys.append("".join(parts))
    if keys[0] != keys[1]:
        return -1 if keys[0] < keys[1] else 1
    if a != b:
        return -1 if a < b else 1
    return 0


# Canonical kind order in <ChildObjects> - the reference is docs/1c-configuration-spec.md,
# table "Order of types in ChildObjects". Needed so a new kind group takes its
# place: otherwise the platform will reorder it on the first dump and produce a diff out of nowhere.
# Map registry: tests/skills/check-type-maps.mjs.
CHILD_OBJECT_TYPES = [
    'Language', 'Subsystem', 'StyleItem', 'Style',
    'CommonPicture', 'SessionParameter', 'Role', 'CommonTemplate',
    'FilterCriterion', 'CommonModule', 'CommonAttribute', 'ExchangePlan',
    'XDTOPackage', 'WebService', 'HTTPService', 'WSReference',
    'EventSubscription', 'ScheduledJob', 'SettingsStorage', 'FunctionalOption',
    'FunctionalOptionsParameter', 'DefinedType', 'Bot', 'PaletteColor', 'CommonCommand', 'CommandGroup',
    'Constant', 'CommonForm', 'Catalog', 'Document',
    'DocumentNumerator', 'Sequence', 'DocumentJournal', 'Enum',
    'Report', 'DataProcessor', 'InformationRegister', 'AccumulationRegister',
    'ChartOfCharacteristicTypes', 'ChartOfAccounts', 'AccountingRegister',
    'ChartOfCalculationTypes', 'CalculationRegister',
    'BusinessProcess', 'Task', 'ExternalDataSource', 'IntegrationService',
]


def register_in_childobjects(parent_xml_path, parent_tag, child_tag, child_name):
    """Register an object in <ChildObjects> of the parent XML.

    Common implementation: the reference is meta-compile, copies - role-compile, xdto-compile.
    Family registry: tests/skills/check-inline-drift.mjs.
    Returns the outcome: added | already | no-childobj | no-config.
    """
    if not os.path.isfile(parent_xml_path):
        return 'no-config'

    # Read raw content, preserving BOM/EOL byte-for-byte (newline='' => no translation)
    with open(parent_xml_path, 'r', encoding='utf-8-sig', newline='') as f:
        config_content = f.read()

    ns = 'http://v8.1c.ru/8.3/MDClasses'
    # ET is used ONLY read-only here: to locate ChildObjects and detect a duplicate.
    # We deliberately do NOT re-serialize Configuration.xml with ElementTree.write():
    # it drops every xmlns declaration used only inside attribute VALUES (e.g.
    # xsi:type="app:ApplicationUsePurpose" in UsePurposes) because ET never sees such
    # prefixes in element/attribute names. The dropped declaration makes XDTO read the
    # value as anyType and Designer refuses to load the file (issue #38). Registration is
    # therefore done by raw-text insertion, preserving BOM, EOL and all namespaces
    # byte-for-byte (same approach as subsystem-compile).
    tree = ET.parse(parent_xml_path)
    root = tree.getroot()

    child_objects = root.find(f'{{{ns}}}{parent_tag}/{{{ns}}}ChildObjects')
    if child_objects is None:
        # Try direct path
        parent_elem = root.find(f'{{{ns}}}{parent_tag}')
        if parent_elem is not None:
            child_objects = parent_elem.find(f'{{{ns}}}ChildObjects')

    if child_objects is None:
        return 'no-childobj'

    existing = child_objects.findall(f'{{{ns}}}{child_tag}')
    if any((e.text or '').strip() == child_name for e in existing):
        return 'already'

    eol = '\r\n' if '\r\n' in config_content else '\n'
    entry = f'<{child_tag}>{esc_xml_text(child_name)}</{child_tag}>'

    block = re.search(r'<ChildObjects\s*>.*?</ChildObjects>', config_content, re.S)
    if block is None:
        # Empty self-closing <ChildObjects/> => open it with the first entry.
        empty = re.search(r'<ChildObjects\s*/>', config_content)
        if empty is None:
            return 'no-childobj'
        replacement = f'<ChildObjects>{eol}\t\t\t{entry}{eol}\t\t</ChildObjects>'
        new_content = config_content[:empty.start()] + replacement + config_content[empty.end():]
        write_utf8_bom(parent_xml_path, new_content)
        return 'added'

    # byName: before the first object of the same kind whose name is greater than the new one.
    # Skip kinds with meaningful tree order - see is_order_sensitive_type.
    if (not is_order_sensitive_type(child_tag)
            and get_new_object_position(os.path.dirname(os.path.abspath(parent_xml_path))) == 'byName'):
        line_rx = re.compile(rf'(?m)^([ \t]*)<{child_tag}>([^<]*)</{child_tag}>')
        for m in line_rx.finditer(config_content, block.start(), block.end()):
            if compare_metadata_names(m.group(2), child_name) > 0:
                new_content = (config_content[:m.start()]
                               + f'{m.group(1)}{entry}{eol}'
                               + config_content[m.start():])
                write_utf8_bom(parent_xml_path, new_content)
                return 'added'

    close_same = f'</{child_tag}>'
    last_same = config_content.rfind(close_same, block.start(), block.end())
    if last_same != -1:
        # After the last element of the same type (keeps them grouped).
        insert_at = last_same + len(close_same)
        new_content = (config_content[:insert_at]
                       + f'{eol}\t\t\t{entry}'
                       + config_content[insert_at:])
    else:
        # There is no group of this kind yet: put it into the canonical kind order - before the first
        # group of a kind older in CHILD_OBJECT_TYPES. Appending to the end of the block is not allowed: the platform
        # would reorder the group on the first dump and produce a diff out of nowhere.
        anchor = None
        if child_tag in CHILD_OBJECT_TYPES:
            own_idx = CHILD_OBJECT_TYPES.index(child_tag)
            type_rx = re.compile(r'(?m)^([ \t]*)<(\w+)>[^<]*</\2>')
            for m in type_rx.finditer(config_content, block.start(), block.end()):
                other = m.group(2)
                if other in CHILD_OBJECT_TYPES and CHILD_OBJECT_TYPES.index(other) > own_idx:
                    anchor = m
                    break
        if anchor is not None:
            new_content = (config_content[:anchor.start()]
                           + f'{anchor.group(1)}{entry}{eol}'
                           + config_content[anchor.start():])
        else:
            # There are no older kinds in the file - the new line goes before </ChildObjects>,
            # the closing tag indent is reused.
            close_at = config_content.rfind('</ChildObjects>', block.start(), block.end())
            new_content = (config_content[:close_at]
                           + f'\t{entry}{eol}\t\t'
                           + config_content[close_at:])
    write_utf8_bom(parent_xml_path, new_content)
    return 'added'


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description='Compile 1C role from JSON', allow_abbrev=False)
    parser.add_argument('-JsonPath', type=str, required=True)
    parser.add_argument('-OutputDir', type=str, required=True)
    args = ci_parse_args(parser)

    # --- 1. Load and validate JSON ---
    json_path = args.JsonPath
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    defn = ci_json(parse_json_input(read_json_file(json_path), json_path))

    if not defn.get('name'):
        print("JSON must have 'name' field (role programmatic name)", file=sys.stderr)
        sys.exit(1)

    role_name = str(defn['name'])
    synonym = str(defn['synonym']) if defn.get('synonym') else role_name
    comment = str(defn['comment']) if defn.get('comment') else ''

    # Synonym: accept "rights" as alias for "objects"
    if not defn.get('objects') and defn.get('rights'):
        defn['objects'] = defn['rights']

    out_dir_resolved = args.OutputDir if os.path.isabs(args.OutputDir) else os.path.join(os.getcwd(), args.OutputDir)
    assert_edit_allowed(out_dir_resolved, "editable")
    format_version = detect_format_version(out_dir_resolved)

    # --- 2. Parse all object entries ---
    # Look up the relative path of the @file first next to the role JSON definition.
    global TEXT_BASE_DIR
    TEXT_BASE_DIR = os.path.dirname(os.path.abspath(args.JsonPath))

    parsed_objects = []
    seen_object_names = set()
    if defn.get('objects'):
        for entry in defn['objects']:
            parsed = parse_object_entry(entry)
            if not parsed:
                continue
            for p in expand_service_entry(parsed, out_dir_resolved, role_name):
                # A duplicate arises normally: an expanded leaf coincided with an explicit one. Rights on
                # the leaf are the same (Use), so the second entry is noise, not a conflict.
                if p['Name'] in seen_object_names:
                    print(f"WARNING: {p['Name']}: объект указан дважды, вторая запись пропущена", file=sys.stderr)
                    continue
                seen_object_names.add(p['Name'])
                parsed_objects.append(p)

    # Refuse BEFORE writing: the role is written with three files (metadata, rights, registration in
    # Configuration.xml), and a partially written role is worse than a missing one. Print all
    # reasons at once - otherwise the user fixes them one by one.
    if VALIDATION_ERRORS:
        print(f"[role-compile] Роль не создана: {len(VALIDATION_ERRORS)} ошибок в описании прав.", file=sys.stderr)
        for e in VALIDATION_ERRORS:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # --- 3. Generate UUID ---
    uid = new_uuid()

    # --- 4. Emit metadata XML (Roles/Name.xml) ---
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    # Namespace declarations - in one variable and one line, as the platform writes them.
    xmlns_decl = ('xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:app="http://v8.1c.ru/8.2/managed-application/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:cmi="http://v8.1c.ru/8.2/managed-application/cmi" xmlns:ent="http://v8.1c.ru/8.1/data/enterprise" xmlns:lf="http://v8.1c.ru/8.2/managed-application/logform" xmlns:style="http://v8.1c.ru/8.1/data/ui/style" xmlns:sys="http://v8.1c.ru/8.1/data/ui/fonts/system" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:v8ui="http://v8.1c.ru/8.1/data/ui" xmlns:web="http://v8.1c.ru/8.1/data/ui/colors/web" xmlns:win="http://v8.1c.ru/8.1/data/ui/colors/windows" xmlns:xen="http://v8.1c.ru/8.3/xcf/enums" xmlns:xpr="http://v8.1c.ru/8.3/xcf/predef" xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"')
    # 2.21 (8.5) added the palette namespace to the header. Insert it IN PLACE (after lf, before
    # style): the platform keeps declarations alphabetically. Palette does NOT go into Rights.xml.
    if format_rank(format_version) >= 221:
        xmlns_decl = xmlns_decl.replace(
            ' xmlns:style=',
            ' xmlns:pal="http://v8.1c.ru/8.1/data/ui/colors/palette" xmlns:style=')
    lines.append(f'<MetaDataObject {xmlns_decl} version="{format_version}">')
    lines.append(f'\t<Role uuid="{uid}">')
    lines.append('\t\t<Properties>')
    lines.append(f'\t\t\t<Name>{role_name}</Name>')
    lines.append('\t\t\t<Synonym>')
    lines.append('\t\t\t\t<v8:item>')
    lines.append('\t\t\t\t\t<v8:lang>ru</v8:lang>')
    lines.append(f'\t\t\t\t\t<v8:content>{esc_xml_text(synonym)}</v8:content>')
    lines.append('\t\t\t\t</v8:item>')
    lines.append('\t\t\t</Synonym>')
    if comment:
        lines.append(f'\t\t\t<Comment>{esc_xml_text(comment)}</Comment>')
    else:
        lines.append('\t\t\t<Comment/>')
    lines.append('\t\t</Properties>')
    lines.append('\t</Role>')
    lines.append('</MetaDataObject>')

    metadata_xml = '\r\n'.join(lines)

    # --- 5. Emit Rights XML (Roles/Name/Ext/Rights.xml) ---
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<Rights xmlns="http://v8.1c.ru/8.2/roles" xmlns:xs="http://www.w3.org/2001/XMLSchema"'
                 ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Rights"'
                 f' version="{format_version}">')

    # Global flags
    sfno = str(defn['setForNewObjects']).lower() if defn.get('setForNewObjects') is not None else 'false'
    sfab = str(defn['setForAttributesByDefault']).lower() if defn.get('setForAttributesByDefault') is not None else 'true'
    irco = str(defn['independentRightsOfChildObjects']).lower() if defn.get('independentRightsOfChildObjects') is not None else 'false'

    lines.append(f'\t<setForNewObjects>{sfno}</setForNewObjects>')
    lines.append(f'\t<setForAttributesByDefault>{sfab}</setForAttributesByDefault>')
    lines.append(f'\t<independentRightsOfChildObjects>{irco}</independentRightsOfChildObjects>')

    # Dependency closure: on load the platform will bring the set to the full one anyway,
    # and the file would diverge from the infobase. We show what was added - rights are not granted silently.
    closure_notes = []
    for o in parsed_objects:
        o['Rights'], added = close_rights_dependencies(o['Name'], o['Rights'], format_rank(format_version))
        if added:
            closure_notes.append(f"     {o['Name']}: по зависимости добавлено — {', '.join(added)}")

    # Order as on the platform: nodes by object uuid, rights - by the type canon. Otherwise the first
    # dump from the Configurator will reorder them and give a diff nobody made.
    parsed_objects = sort_objects_by_uuid(parsed_objects, out_dir_resolved)
    for o in parsed_objects:
        o['Rights'] = sort_rights_canonical(o['Name'], o['Rights'])

    # The platform does not store entries equal to the role default - we drop them ourselves and say so.
    dropped_by_default = []
    for obj in parsed_objects:
        default_value = get_default_right_value(obj['Name'], sfno, sfab)
        kept = []
        for right in obj['Rights']:
            # A right with a restriction differs from the default by the restriction itself - the platform stores it,
            # and dropping it would silently lose the written condition.
            if right['Value'] == default_value and not right['Condition']:
                dropped_by_default.append(f"{obj['Name']}.{right['Name']}")
                continue
            kept.append(right)
        obj['Rights'] = kept
    parsed_objects = [o for o in parsed_objects if o['Rights']]

    # Object blocks
    total_rights = 0
    for obj in parsed_objects:
        lines.append('\t<object>')
        lines.append(f'\t\t<name>{obj["Name"]}</name>')
        for right in obj['Rights']:
            lines.append('\t\t<right>')
            lines.append(f'\t\t\t<name>{right["Name"]}</name>')
            lines.append(f'\t\t\t<value>{right["Value"]}</value>')
            if right['Condition']:
                lines.append('\t\t\t<restrictionByCondition>')
                lines.append(f'\t\t\t\t<condition>{esc_xml_text(right["Condition"])}</condition>')
                lines.append('\t\t\t</restrictionByCondition>')
            lines.append('\t\t</right>')
            total_rights += 1
        lines.append('\t</object>')

    # RLS restriction templates
    template_count = 0
    if defn.get('templates'):
        for tpl in defn['templates']:
            lines.append('\t<restrictionTemplate>')
            lines.append(f'\t\t<name>{esc_xml_text(str(tpl["name"]))}</name>')
            lines.append(f'\t\t<condition>{esc_xml_text(resolve_text_from_file(str(tpl["condition"]), TEXT_BASE_DIR))}</condition>')
            lines.append('\t</restrictionTemplate>')
            template_count += 1

    lines.append('</Rights>')

    rights_xml = '\r\n'.join(lines)

    # --- 6. Write output files ---
    out_dir = args.OutputDir
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(os.getcwd(), out_dir)

    # Determine Roles dir and config root
    # Back-compat: if OutputDir leaf is "Roles", use as-is; otherwise treat as config root
    leaf = os.path.basename(out_dir.rstrip(os.sep).rstrip('/'))
    if leaf == 'Roles':
        roles_dir = out_dir
        config_dir = os.path.dirname(out_dir)
    else:
        roles_dir = os.path.join(out_dir, 'Roles')
        config_dir = out_dir

    # Metadata: Roles/RoleName.xml
    metadata_path = os.path.join(roles_dir, f'{role_name}.xml')
    os.makedirs(roles_dir, exist_ok=True)

    # Rights: Roles/RoleName/Ext/Rights.xml
    role_sub_dir = os.path.join(roles_dir, role_name)
    ext_dir = os.path.join(role_sub_dir, 'Ext')
    rights_path = os.path.join(ext_dir, 'Rights.xml')
    os.makedirs(ext_dir, exist_ok=True)

    write_utf8_bom(metadata_path, metadata_xml)
    write_utf8_bom(rights_path, rights_xml)

    # --- 7. Register in Configuration.xml ---
    config_xml_path = os.path.join(config_dir, 'Configuration.xml')
    reg_result = register_in_childobjects(config_xml_path, 'Configuration', 'Role', role_name)

    # --- 8. Summary ---
    print(f"[OK] Role '{role_name}' compiled")
    print(f"     UUID: {uid}")
    print(f"     Metadata: {metadata_path}")
    print(f"     Rights:   {rights_path}")
    print(f"     Objects: {len(parsed_objects)}, Rights: {total_rights}, Templates: {template_count}")
    if dropped_by_default:
        print("[role-compile] Не записаны права, совпадающие с умолчанием роли "
              f"(платформа их не хранит): {', '.join(dropped_by_default)}", file=sys.stderr)
        print("  Запрет хранится у реквизитов и табличных частей (они наследуют права объекта) "
              "либо в роли с setForNewObjects=true; выдача прав — наоборот.", file=sys.stderr)
    for note in closure_notes:
        print(note)
    if reg_result == 'added':
        print(f"     Configuration.xml: <Role>{role_name}</Role> added to ChildObjects")
    elif reg_result == 'already':
        print(f"     Configuration.xml: <Role>{role_name}</Role> already registered")
    elif reg_result == 'no-childobj':
        print(f"WARNING: Configuration.xml found but <ChildObjects> not found", file=sys.stderr)
    elif reg_result == 'no-config':
        print(f"WARNING: Configuration.xml not found at {config_xml_path} -- register manually", file=sys.stderr)


if __name__ == '__main__':
    main()
