# meta-validate v1.34 — Validate 1C metadata object structure (Python port)
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills
import argparse
import os
import re
import sys

from lxml import etree

# In batch the script runs again in the same process, and the stream may already be replaced
# (StringIO has no reconfigure) - the encoding was already set by the first run.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

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


# ── arg parsing ──────────────────────────────────────────────

parser = argparse.ArgumentParser(allow_abbrev=False)
parser.add_argument("-ObjectPath", "-Path", required=True)
parser.add_argument("-Detailed", action="store_true")
parser.add_argument("-MaxErrors", type=int, default=30)
parser.add_argument("-OutFile", default="")
args = ci_parse_args(parser)

detailed = args.Detailed
max_errors = args.MaxErrors
out_file = args.OutFile

# ── batch mode: pipe-separated paths ─────────────────────────

path_list = [p.strip() for p in args.ObjectPath.split('|') if p.strip()]
if len(path_list) > 1:
    # Each object is checked by this same script in a FRESH globals() (same process, clean
    # namespace per object). A separate process per object would cost
    # interpreter startup with lxml import (~146 ms) against parsing in a few milliseconds; here both
    # startup and file compilation are paid once for the whole batch.
    batch_ok = 0
    batch_fail = 0
    with open(__file__, encoding="utf-8") as _f:
        _code = compile(_f.read(), __file__, "exec")
    _saved_argv = sys.argv
    for single_path in path_list:
        argv = ["meta-validate.py", "-ObjectPath", single_path, "-MaxErrors", str(max_errors)]
        if detailed:
            argv.append("-Detailed")
        if out_file:
            base, ext = os.path.splitext(out_file)
            obj_leaf = os.path.splitext(os.path.basename(single_path))[0]
            argv += ["-OutFile", f"{base}_{obj_leaf}{ext}"]
        sys.argv = argv
        rc = 0
        try:
            exec(_code, {"__name__": "__main__", "__file__": __file__})
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 0
        except Exception as e:
            # A failure of one object must not break the batch - in the separate-process variant
            # this was ensured by process isolation.
            print(f"[ERROR] {single_path}: {type(e).__name__}: {e}")
            rc = 1
        finally:
            sys.argv = _saved_argv
        if rc == 0:
            batch_ok += 1
        else:
            batch_fail += 1
    print()
    print(f"=== Batch: {len(path_list)} objects, {batch_ok} passed, {batch_fail} failed ===")
    sys.exit(1 if batch_fail > 0 else 0)

object_path = path_list[0]

# ── resolve path ─────────────────────────────────────────────

if not os.path.isabs(object_path):
    object_path = os.path.join(os.getcwd(), object_path)

if os.path.isdir(object_path):
    dir_name = os.path.basename(object_path)
    candidate = os.path.join(object_path, f"{dir_name}.xml")
    sibling = os.path.join(os.path.dirname(object_path), f"{dir_name}.xml")
    if os.path.exists(candidate):
        object_path = candidate
    elif os.path.exists(sibling):
        object_path = sibling
    else:
        xml_files = [f for f in os.listdir(object_path) if f.endswith(".xml")]
        if xml_files:
            object_path = os.path.join(object_path, xml_files[0])
        else:
            print(f"[ERROR] No XML file found in directory: {object_path}")
            sys.exit(1)

# File not found -- forgiving input for flat objects (SessionParameter, CommonAttribute,
# DefinedType, WSReference, ... -- a single .xml without a folder): append .xml to a bare name
if not os.path.exists(object_path) and not os.path.splitext(object_path)[1]:
    if os.path.exists(object_path + ".xml"):
        object_path = object_path + ".xml"

# File not found -- check Dir/Name/Name.xml -> Dir/Name.xml
if not os.path.exists(object_path):
    file_name = os.path.splitext(os.path.basename(object_path))[0]
    parent_dir = os.path.dirname(object_path)
    parent_dir_name = os.path.basename(parent_dir)
    if file_name == parent_dir_name:
        candidate = os.path.join(os.path.dirname(parent_dir), f"{file_name}.xml")
        if os.path.exists(candidate):
            object_path = candidate

if not os.path.exists(object_path):
    print(f"[ERROR] File not found: {object_path}")
    sys.exit(1)

resolved_path = os.path.abspath(object_path)

# ── detect config directory (for cross-object checks) ────────

config_dir = None
probe = os.path.dirname(resolved_path)
for _ in range(4):
    if not probe:
        break
    if os.path.exists(os.path.join(probe, "Configuration.xml")):
        config_dir = probe
        break
    probe = os.path.dirname(probe)

# ── output infrastructure ────────────────────────────────────

errors = 0
warnings = 0
ok_count = 0
stopped = False
output_lines = []


def out_line(msg):
    output_lines.append(msg)


def report_ok(msg):
    global ok_count
    ok_count += 1
    if detailed:
        out_line(f"[OK]    {msg}")


def report_error(msg):
    global errors, stopped
    errors += 1
    out_line(f"[ERROR] {msg}")
    if errors >= max_errors:
        stopped = True


def report_warn(msg):
    global warnings
    warnings += 1
    out_line(f"[WARN]  {msg}")


def finalize():
    checks = ok_count + errors + warnings
    if errors == 0 and warnings == 0 and not detailed:
        result = f"=== Validation OK: {md_type}.{obj_name} ({checks} checks) ==="
    else:
        out_line("")
        out_line(f"=== Result: {errors} errors, {warnings} warnings ({checks} checks) ===")
        result = "\n".join(output_lines)
    print(result)
    if out_file:
        with open(out_file, "w", encoding="utf-8-sig") as f:
            f.write(result)
        print(f"Written to: {out_file}")


# ── Format version ───────────────────────────────────────────
# Verified dump format version range: 2.17 (8.3.24) ... 2.21 (8.5). The full ladder is in
# docs/1c-configuration-spec.md, "Лестница версий". The version is set by the DUMP platform, not by the
# configuration compatibility mode. Versions below 2.17 (platforms 8.3.23 and older) exist, but the skills
# were not tested on them - this is a warning about lack of coverage, not about file incorrectness.
FORMAT_VERIFIED_MIN = "2.17"
FORMAT_VERIFIED_MAX = "2.21"


def format_rank(ver):
    """"2.20" -> 220, "2.9" -> 209. String comparison is wrong ("2.9" > "2.17")."""
    m = re.match(r'^(\d+)\.(\d+)$', ver or '')
    return int(m.group(1)) * 100 + int(m.group(2)) if m else 0


# The format version stamp is the version attribute of the ROOT element of the file. The root one specifically: in the extension
# Form.xml below there is <BaseForm version=...>. Only the header is read, without parsing the file.
def root_version(xml_path):
    if not os.path.isfile(xml_path):
        return None
    with open(xml_path, "rb") as f:
        head = f.read(4096).decode("utf-8", errors="ignore")
    m = re.search(r'<[A-Za-z_][\w.:-]*(\s[^>]*)?/?>', head)
    if not m:
        return None
    v = re.search(r'(?:^|\s)version="([^"]*)"', m.group(1) or "")
    if v:
        return v.group(1)
    return None


# Root of an autonomous external data processor/report. Copy of the shared reference (is_external_root family,
# authority - cf-edit).
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


# Dump anchor in whose tree the file lies: the root of an autonomous EPF/ERF or Configuration.xml,
# nearest upwards. The data processor root is checked first - otherwise a data processor lying in the configuration
# tree would be compared against the configuration. No anchor - nothing to compare against.
def find_dump_anchor(start_dir):
    d = start_dir
    for _ in range(15):
        if not d:
            break
        if _sg_is_external_root(d + ".xml"):
            return d + ".xml"
        cfg = os.path.join(d, "Configuration.xml")
        if os.path.exists(cfg):
            return cfg
        parent = os.path.dirname(d)
        if not parent or parent == d:
            break
        d = parent
    return None


# ── Reference tables ─────────────────────────────────────────

guid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
ident_pattern = re.compile(r'^[A-Za-z\u0410-\u042F\u0401\u0430-\u044F\u0451_][A-Za-z0-9\u0410-\u042F\u0401\u0430-\u044F\u0451_]*$')

valid_types = (
    "Catalog", "Document", "Enum", "Constant",
    "InformationRegister", "AccumulationRegister", "AccountingRegister", "CalculationRegister",
    "ChartOfAccounts", "ChartOfCharacteristicTypes", "ChartOfCalculationTypes",
    "BusinessProcess", "Task", "ExchangePlan", "DocumentJournal",
    "Report", "DataProcessor",
    "CommonModule", "ScheduledJob", "EventSubscription",
    "HTTPService", "WebService", "DefinedType",
    # External data source and its table (the table file root is <Table>).
    "ExternalDataSource", "Table",
)

# Valid metadata types without deep validation rules - previously failed as "Unrecognized"
# (a false error on a valid object). For them a basic structural check is performed (root/uuid/Name).
structural_only_types = (
    "Subsystem", "Role", "CommonForm", "CommonCommand", "CommandGroup", "CommonAttribute",
    "CommonTemplate", "CommonPicture", "SessionParameter", "SettingsStorage", "FilterCriterion",
    "IntegrationService", "Bot",
    "FunctionalOption", "FunctionalOptionsParameter", "Language", "Style", "StyleItem",
    "WSReference", "XDTOPackage", "DocumentNumerator", "Sequence",
)

# Nested object descriptors: Forms/<Имя>.xml and Templates/<Имя>.xml. The root is the same MetaDataObject,
# but they are not registered in the configuration ChildObjects and are never the first segment of MDObjectRef -
# do not add them to known_roots of check 17. They are accepted so that a batch run over the list of changed
# files does not fall on them with "Unrecognized".
nested_descriptor_types = ("Form", "Template")
# Form/template kind - the platform uses it to choose the body reader. Values - docs/1c-configuration-spec.md,
# properties FormType and TemplateType. The list is separate from valid_property_values: the meta-compile authority
# has no these keys (forms and templates are created by form-add and template-add).
descriptor_kind_values = {
    "FormType": ("Managed", "Ordinary"),
    "TemplateType": ("SpreadsheetDocument", "BinaryData", "HTMLDocument", "TextDocument", "ActiveDocument",
                     "DataCompositionSchema", "DataCompositionAppearanceTemplate", "GraphicalSchema", "GeographicalSchema", "AddIn"),
}

# GeneratedType categories by type
generated_type_categories = {
    "Catalog":                    ["Object", "Ref", "Selection", "List", "Manager"],
    "Document":                   ["Object", "Ref", "Selection", "List", "Manager"],
    "Enum":                       ["Ref", "Manager", "List"],
    "Constant":                   ["Manager", "ValueManager", "ValueKey"],
    "InformationRegister":        ["Record", "Manager", "Selection", "List", "RecordSet", "RecordKey", "RecordManager"],
    "AccumulationRegister":       ["Record", "Manager", "Selection", "List", "RecordSet", "RecordKey"],
    "AccountingRegister":         ["Record", "Manager", "Selection", "List", "RecordSet", "RecordKey", "ExtDimensions"],
    "CalculationRegister":        ["Record", "Manager", "Selection", "List", "RecordSet", "RecordKey", "Recalcs"],
    "ChartOfAccounts":            ["Object", "Ref", "Selection", "List", "Manager", "ExtDimensionTypes", "ExtDimensionTypesRow"],
    "ChartOfCharacteristicTypes": ["Object", "Ref", "Selection", "List", "Manager", "Characteristic"],
    "ChartOfCalculationTypes":    ["Object", "Ref", "Selection", "List", "Manager", "DisplacingCalculationTypes", "DisplacingCalculationTypesRow", "BaseCalculationTypes", "BaseCalculationTypesRow", "LeadingCalculationTypes", "LeadingCalculationTypesRow"],
    "BusinessProcess":            ["Object", "Ref", "Selection", "List", "Manager", "RoutePointRef"],
    "Task":                       ["Object", "Ref", "Selection", "List", "Manager"],
    "ExchangePlan":               ["Object", "Ref", "Selection", "List", "Manager"],
    "DocumentJournal":            ["Selection", "List", "Manager"],
    "Report":                     ["Object", "Manager"],
    "DataProcessor":              ["Object", "Manager"],
    "DefinedType":                ["DefinedType"],
    "ExternalDataSource":         ["Manager", "TablesManager", "CubesManager"],
    # External data source table: the element name is three-part (Префикс.Источник.Таблица),
    # but the "name ends with .ИмяОбъекта" check works on it as is.
    "Table":                      ["Manager", "Object", "Ref", "List", "Record", "RecordSet", "RecordKey", "RecordManager"],
}

# Types that have NO InternalInfo / GeneratedType
types_without_internal_info = ("CommonModule", "ScheduledJob", "EventSubscription")

# StandardAttributes by type
standard_attributes_by_type = {
    "Catalog":                    ["PredefinedDataName", "Predefined", "Ref", "DeletionMark", "IsFolder", "Owner", "Parent", "Description", "Code"],
    "Document":                   ["Posted", "Ref", "DeletionMark", "Date", "Number"],
    "Enum":                       ["Order", "Ref"],
    "InformationRegister":        ["Active", "LineNumber", "Recorder", "Period"],
    "AccumulationRegister":       ["Active", "LineNumber", "Recorder", "Period", "RecordType"],
    "AccountingRegister":         ["Active", "Period", "Recorder", "LineNumber", "Account", "PeriodAdjustment", "RecordType"],
    "CalculationRegister":        ["Active", "Recorder", "LineNumber", "RegistrationPeriod", "CalculationType", "ReversingEntry", "ActionPeriod", "BegOfActionPeriod", "EndOfActionPeriod", "BegOfBasePeriod", "EndOfBasePeriod"],
    "ChartOfAccounts":            ["PredefinedDataName", "Predefined", "Ref", "DeletionMark", "Description", "Code", "Parent", "Order", "Type", "OffBalance"],
    "ChartOfCharacteristicTypes": ["PredefinedDataName", "Predefined", "Ref", "DeletionMark", "Description", "Code", "Parent", "IsFolder", "ValueType"],
    "ChartOfCalculationTypes":    ["PredefinedDataName", "Predefined", "Ref", "DeletionMark", "Description", "Code", "ActionPeriodIsBasic"],
    "BusinessProcess":            ["Ref", "DeletionMark", "Date", "Number", "Started", "Completed", "HeadTask"],
    "Task":                       ["Ref", "DeletionMark", "Date", "Number", "Executed", "Description", "RoutePoint", "BusinessProcess"],
    "ExchangePlan":               ["Ref", "DeletionMark", "Code", "Description", "ThisNode", "SentNo", "ReceivedNo", "ExchangeDate"],
    "DocumentJournal":            ["Type", "Ref", "Date", "Posted", "DeletionMark", "Number"],
}

# Standard attributes whose presence depends on object properties: for an accounting register
# PeriodAdjustment - on the adjustment period length, RecordType - on correspondence; for an accumulation
# register RecordType - on the register type. Their absence is legal, they do not fall into "Missing".
std_attr_conditional_names = {
    "AccountingRegister":   ("PeriodAdjustment", "RecordType"),
    "AccumulationRegister": ("RecordType",),
    # ExchangeDate - a legacy attribute declared only on some exchange plans: allowed, but not required.
    "ExchangePlan":         ("ExchangeDate",),
}

# Types that have StandardAttributes block
types_with_std_attrs = (
    "Catalog", "Document", "Enum",
    "InformationRegister", "AccumulationRegister", "AccountingRegister", "CalculationRegister",
    "ChartOfAccounts", "ChartOfCharacteristicTypes", "ChartOfCalculationTypes",
    "BusinessProcess", "Task", "ExchangePlan", "DocumentJournal",
)

# ChildObjects rules
child_object_rules = {
    "Catalog":                    ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "Document":                   ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "ExchangePlan":               ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "ChartOfAccounts":            ["Attribute", "TabularSection", "Form", "Template", "Command", "AccountingFlag", "ExtDimensionAccountingFlag"],
    "ChartOfCharacteristicTypes": ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "ChartOfCalculationTypes":    ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "BusinessProcess":            ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "Task":                       ["Attribute", "TabularSection", "Form", "Template", "Command", "AddressingAttribute"],
    "Report":                     ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "DataProcessor":              ["Attribute", "TabularSection", "Form", "Template", "Command"],
    "Enum":                       ["EnumValue", "Form", "Template", "Command"],
    "InformationRegister":        ["Dimension", "Resource", "Attribute", "Form", "Template", "Command"],
    "AccumulationRegister":       ["Dimension", "Resource", "Attribute", "Form", "Template", "Command"],
    "AccountingRegister":         ["Dimension", "Resource", "Attribute", "Form", "Template", "Command"],
    "CalculationRegister":        ["Dimension", "Resource", "Attribute", "Form", "Template", "Command", "Recalculation"],
    "DocumentJournal":            ["Column", "Form", "Template", "Command"],
    "HTTPService":                ["URLTemplate"],
    "WebService":                 ["Operation"],
    # External source: tables are listed by names, functions are stored as full nodes.
    "ExternalDataSource":         ["Table", "Function", "Cube"],
    "Table":                      ["Field", "Form", "Template", "Command"],
    "Constant":                   ["Form"],
    "DefinedType":                [],
    "CommonModule":               [],
    "ScheduledJob":               [],
    "EventSubscription":          [],
}

# Command interface groups (mirror of meta-compile): sections - without commandParameterType; forms - with the parameter.
SECTION_COMMAND_GROUPS = ["NavigationPanelImportant", "NavigationPanelOrdinary", "NavigationPanelSeeAlso",
                          "ActionsPanelCreate", "ActionsPanelReports", "ActionsPanelTools"]
FORM_COMMAND_GROUPS = ["FormCommandBarImportant", "FormCommandBarCreateBasedOn",
                       "FormNavigationPanelImportant", "FormNavigationPanelGoTo", "FormNavigationPanelSeeAlso"]
VALID_COMMAND_GROUPS = SECTION_COMMAND_GROUPS + FORM_COMMAND_GROUPS

# Valid enum property values
valid_property_values = {
    "CodeType":                     ["String", "Number"],
    "CodeAllowedLength":            ["Variable", "Fixed"],
    "NumberType":                   ["String", "Number"],
    "NumberAllowedLength":          ["Variable", "Fixed"],
    "Posting":                      ["Allow", "Deny"],
    "RealTimePosting":              ["Allow", "Deny"],
    "RegisterRecordsDeletion":      ["AutoDelete", "AutoDeleteOnUnpost", "AutoDeleteOff"],
    "RegisterRecordsWritingOnPost": ["WriteModified", "WriteSelected"],
    # AutomaticAndManaged - only on an external data source and its tables.
    "DataLockControlMode":          ["Automatic", "Managed", "AutomaticAndManaged"],
    "FullTextSearch":               ["Use", "DontUse"],
    "DefaultPresentation":          ["AsDescription", "AsCode"],
    # Refinement by object kind ("Вид.Свойство") - before the common list. AsNumber ("в виде номера")
    # exists only on a task: the platform rejects it on a catalog and others (8.3.24 and 8.5.1).
    "Task.DefaultPresentation":     ["AsDescription", "AsNumber"],
    "HierarchyType":                ["HierarchyFoldersAndItems", "HierarchyOfItems"],
    "EditType":                     ["InDialog", "InList", "BothWays"],
    "WriteMode":                    ["Independent", "RecorderSubordinate"],
    "InformationRegisterPeriodicity": ["Nonperiodical", "Second", "Day", "Month", "Quarter", "Year", "RecorderPosition"],
    "RegisterType":                 ["Balance", "Turnovers"],
    "ReturnValuesReuse":            ["DontUse", "DuringRequest", "DuringSession"],
    "ReuseSessions":                ["DontUse", "Use", "AutoUse"],
    "FillChecking":                 ["DontCheck", "ShowError"],
    "Indexing":                     ["DontIndex", "Index", "IndexWithAdditionalOrder"],
    "DataHistory":                  ["Use", "DontUse"],
    "DependenceOnCalculationTypes": ["DontUse", "OnActionPeriod", "OnRegistrationPeriod"],
}

# Properties forbidden per type (would cause LoadConfigFromFiles error)
forbidden_properties = {
    "ChartOfCharacteristicTypes": ["CodeType"],
    "ChartOfAccounts":            ["Autonumbering", "Hierarchical"],
    "ChartOfCalculationTypes":    ["CheckUnique", "Autonumbering"],
    "ExchangePlan":               ["CodeType", "CheckUnique", "Autonumbering"],
}

# ── Namespaces ───────────────────────────────────────────────

NS = {
    "md":  "http://v8.1c.ru/8.3/MDClasses",
    "v8":  "http://v8.1c.ru/8.1/data/core",
    "xr":  "http://v8.1c.ru/8.3/xcf/readable",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xs":  "http://www.w3.org/2001/XMLSchema",
    "cfg": "http://v8.1c.ru/8.1/data/enterprise/current-config",
}

MD_NS = NS["md"]


def local_name(node):
    return etree.QName(node.tag).localname


def find(parent, xpath):
    r = parent.xpath(xpath, namespaces=NS)
    return r[0] if r else None


def find_all(parent, xpath):
    return parent.xpath(xpath, namespaces=NS)


def inner_text(node):
    if node is None:
        return ""
    return node.text or ""


def text_of(node):
    if node is None:
        return ""
    return (node.text or "").strip()


# ── 1. Parse XML ─────────────────────────────────────────────

out_line("")

tree = None
try:
    parser_xml = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(resolved_path, parser_xml)
except Exception as e:
    out_line("=== Validation: (parse failed) ===")
    out_line("")
    report_error(f"1. XML parse failed: {e}")
    finalize()
    sys.exit(1)

root = tree.getroot()

# ── Check 1: Root structure ──────────────────────────────────

check1_ok = True

if local_name(root) != "MetaDataObject":
    report_error(f"1. Root element is '{local_name(root)}', expected 'MetaDataObject'")
    finalize()
    sys.exit(1)

expected_ns = "http://v8.1c.ru/8.3/MDClasses"
root_ns = etree.QName(root.tag).namespace or ""
if root_ns != expected_ns:
    report_error(f"1. Root namespace is '{root_ns}', expected '{expected_ns}'")
    check1_ok = False

# Version attribute
version = root.get("version", "")
version_rank = format_rank(version)
if not version:
    report_warn("1. Missing version attribute on MetaDataObject")
elif version_rank == 0:
    report_error(f"1. Malformed version '{version}' (expected N.N)")
elif version_rank < format_rank(FORMAT_VERIFIED_MIN):
    report_warn(f"1. Format version '{version}' is below the tested range "
                f"{FORMAT_VERIFIED_MIN}-{FORMAT_VERIFIED_MAX} — skills were not verified on it")
elif version_rank > format_rank(FORMAT_VERIFIED_MAX):
    report_warn(f"1. Format version '{version}' is above the tested range "
                f"{FORMAT_VERIFIED_MIN}-{FORMAT_VERIFIED_MAX} — skills were not verified on it")

# Detect type element -- exactly one child element in md namespace
type_node = None
md_type = ""
child_elements = []
for child in root:
    if isinstance(child.tag, str) and etree.QName(child.tag).namespace == expected_ns:
        child_elements.append(child)

if len(child_elements) == 0:
    report_error("1. No metadata type element found inside MetaDataObject")
    finalize()
    sys.exit(1)
elif len(child_elements) > 1:
    names = [local_name(c) for c in child_elements]
    report_error(f"1. Multiple type elements found: {names}")
    check1_ok = False

type_node = child_elements[0]
md_type = local_name(type_node)

if md_type not in valid_types and md_type not in structural_only_types and md_type not in nested_descriptor_types:
    report_error(f"1. Unrecognized metadata type: {md_type}")
    finalize()
    sys.exit(1)

# UUID on type element
type_uuid = type_node.get("uuid", "")
if not type_uuid:
    report_error(f"1. Missing uuid on <{md_type}> element")
    check1_ok = False
elif not guid_pattern.match(type_uuid):
    report_error(f"1. Invalid uuid '{type_uuid}' on <{md_type}>")
    check1_ok = False

# Get object name early for header
props_node = find(type_node, "md:Properties")
name_node = find(props_node, "md:Name") if props_node is not None else None
obj_name = inner_text(name_node) if name_node is not None and inner_text(name_node) else "(unknown)"

# Now emit header — insert at beginning
output_lines.insert(0, f"=== Validation: {md_type}.{obj_name} ===")

if check1_ok:
    report_ok(f"1. Root structure: MetaDataObject/{md_type}, version {version}")

# ── Check 24: format version is consistent within the object; comparison with the dump ──
# Parts of an object - the descriptor X.xml and stamped bodies X/Ext/*.xml - the platform loads in only one
# version: "Версия формата загружаемого файла … отличается от версии формата ранее загруженных файлов".
# Forms and templates of the object (Forms/F.xml + F/Ext/Form.xml, Templates/T.xml + T/Ext/Template.xml) are the same
# pairs, checked together with the object. The platform loads objects of different versions together, this is only dump heterogeneity (typical after
# merging branches dumped by different platforms) - so the comparison with the dump only warns.
# Placed before early exits: needed by every root, including structural-only and nested descriptors.
obj_base_dir = os.path.dirname(resolved_path)
obj_dir = os.path.join(obj_base_dir, os.path.splitext(os.path.basename(resolved_path))[0])
ver_descriptors = [resolved_path]
for sub in ("Forms", "Templates"):
    sub_dir = os.path.join(obj_dir, sub)
    if not os.path.isdir(sub_dir):
        continue
    names = sorted(n for n in os.listdir(sub_dir)
                   if n.lower().endswith(".xml") and os.path.isfile(os.path.join(sub_dir, n)))
    for n in names:
        ver_descriptors.append(os.path.join(sub_dir, n))


def ver_rel(p):
    return p[len(obj_base_dir):].lstrip("\\/").replace("\\", "/")


ver_errors = 0
ver_bodies = 0
for desc in ver_descriptors:
    if stopped:
        break
    desc_ver = version if desc == resolved_path else root_version(desc)
    if not desc_ver:
        continue
    ext_dir = os.path.join(os.path.dirname(desc), os.path.splitext(os.path.basename(desc))[0], "Ext")
    if not os.path.isdir(ext_dir):
        continue
    body_names = sorted(n for n in os.listdir(ext_dir)
                        if n.lower().endswith(".xml") and os.path.isfile(os.path.join(ext_dir, n)))
    for bn in body_names:
        body = os.path.join(ext_dir, bn)
        body_ver = root_version(body)
        if not body_ver:
            continue
        # For an adopted extension form the second stamp is <BaseForm version=...>; the platform compares
        # the descriptor against it too.
        if bn == "Form.xml":
            with open(body, "r", encoding="utf-8-sig") as f:
                body_text = f.read()
            bfm = re.search(r'<BaseForm\s[^>]*?version="([^"]*)"', body_text)
            if bfm and bfm.group(1) != desc_ver:
                ver_errors += 1
                report_error(f"24. {ver_rel(body)} <BaseForm> is stamped {bfm.group(1)}, its descriptor {ver_rel(desc)} "
                             f"{desc_ver} — the platform refuses to load parts of one object in different formats")
                if stopped:
                    break
        if body_ver == desc_ver:
            ver_bodies += 1
            continue
        ver_errors += 1
        report_error(f"24. {ver_rel(body)} is stamped {body_ver}, its descriptor {ver_rel(desc)} {desc_ver} "
                     "— the platform refuses to load parts of one object in different formats")
        if stopped:
            break
if ver_errors == 0 and ver_bodies > 0:
    report_ok(f"24. Format version: {ver_bodies} stamped part(s) agree with their descriptors")
dump_anchor = find_dump_anchor(obj_base_dir)
dump_ver = root_version(dump_anchor) if dump_anchor else None
if dump_ver:
    ver_off = []
    for desc in ver_descriptors:
        dv = version if desc == resolved_path else root_version(desc)
        if dv and dv != dump_ver:
            ver_off.append(f"{ver_rel(desc)} {dv}")
    if ver_off:
        shown = ", ".join(ver_off[:5])
        if len(ver_off) > 5:
            shown += f", … (+{len(ver_off) - 5})"
        report_warn(f"24. Format version differs from the dump ({dump_ver}): {shown} — the platform loads it, "
                    "but the dump is no longer uniform (typical after merging branches dumped by different platforms)")
    else:
        report_ok(f"24. Format version: matches the dump ({dump_ver})")

# ── Structural-only types: basic check (Name), without type-specific rules ──
if md_type in structural_only_types:
    if obj_name == "(unknown)":
        report_error("3. Properties: missing or empty Name")
    elif not ident_pattern.match(obj_name):
        report_error(f"3. Properties: Name '{obj_name}' is not a valid 1C identifier")
    else:
        report_ok(f'3. Properties: Name="{obj_name}" (базовая структурная проверка для {md_type})')
    finalize()
    sys.exit(1 if errors > 0 else 0)

# ── Nested Form/Template descriptors: Name and form/template kind ──
if md_type in nested_descriptor_types:
    if obj_name == "(unknown)":
        report_error("3. Properties: missing or empty Name")
    elif not ident_pattern.match(obj_name):
        report_error(f"3. Properties: Name '{obj_name}' is not a valid 1C identifier")
    else:
        report_ok(f'3. Properties: Name="{obj_name}" (базовая структурная проверка для {md_type})')
    kind_prop = "FormType" if md_type == "Form" else "TemplateType"
    kind_node = find(props_node, f"md:{kind_prop}") if props_node is not None else None
    kind_value = inner_text(kind_node) if kind_node is not None else ""
    allowed = descriptor_kind_values[kind_prop]
    if not kind_value:
        report_error(f"3. Property '{kind_prop}' is missing on <{md_type}>")
    elif kind_value not in allowed:
        report_error(f"3. Property '{kind_prop}' has invalid value '{kind_value}' (allowed: {', '.join(allowed)})")
    else:
        report_ok(f"3. Property '{kind_prop}' = {kind_value}")
    finalize()
    sys.exit(1 if errors > 0 else 0)

if stopped:
    finalize()
    sys.exit(1)

# ── Check 2: InternalInfo ────────────────────────────────────

internal_info = find(type_node, "md:InternalInfo")

if md_type in types_without_internal_info:
    if internal_info is not None:
        gen_types = find_all(internal_info, "xr:GeneratedType")
        if len(gen_types) > 0:
            report_warn(f"2. InternalInfo: {md_type} should not have GeneratedType entries, found {len(gen_types)}")
        else:
            report_ok(f"2. InternalInfo: absent or empty (correct for {md_type})")
    else:
        report_ok(f"2. InternalInfo: absent (correct for {md_type})")
elif md_type in generated_type_categories:
    expected_categories = generated_type_categories[md_type]
    if internal_info is None:
        report_error(f"2. InternalInfo: missing (expected {len(expected_categories)} GeneratedType)")
    else:
        gen_types = find_all(internal_info, "xr:GeneratedType")
        check2_ok = True
        found_categories = []

        for gt in gen_types:
            gt_name = gt.get("name", "")
            gt_category = gt.get("category", "")
            found_categories.append(gt_category)

            # Validate name format
            if gt_name and obj_name != "(unknown)":
                if not gt_name.endswith(f".{obj_name}"):
                    report_error(f"2. GeneratedType name '{gt_name}' does not end with '.{obj_name}'")
                    check2_ok = False

            # Validate category
            if gt_category not in expected_categories:
                report_warn(f"2. Unexpected GeneratedType category '{gt_category}' for {md_type}")

            # Validate TypeId and ValueId UUIDs
            type_id = find(gt, "xr:TypeId")
            value_id = find(gt, "xr:ValueId")
            if type_id is not None and not guid_pattern.match(inner_text(type_id)):
                report_error(f"2. Invalid TypeId UUID in GeneratedType '{gt_category}'")
                check2_ok = False
            if value_id is not None and not guid_pattern.match(inner_text(value_id)):
                report_error(f"2. Invalid ValueId UUID in GeneratedType '{gt_category}'")
                check2_ok = False

        # ExchangePlan: check for ThisNode
        if md_type == "ExchangePlan":
            this_node = find(internal_info, "xr:ThisNode")
            if this_node is None:
                report_warn("2. ExchangePlan missing xr:ThisNode in InternalInfo")
            elif not guid_pattern.match(inner_text(this_node)):
                report_error("2. ExchangePlan xr:ThisNode has invalid UUID")
                check2_ok = False

        # Check count mismatch
        missing_cats = [c for c in expected_categories if c not in found_categories]
        if missing_cats:
            report_warn(f"2. Missing GeneratedType categories: {', '.join(missing_cats)}")

        if check2_ok:
            cat_list = ", ".join(sorted(found_categories))
            report_ok(f"2. InternalInfo: {len(gen_types)} GeneratedType ({cat_list})")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 3: Properties -- Name, Synonym ─────────────────────

if props_node is None:
    report_error("3. Properties block missing")
else:
    check3_ok = True

    # Name
    if name_node is None or not inner_text(name_node):
        report_error("3. Properties: Name is missing or empty")
        check3_ok = False
    else:
        name_val = inner_text(name_node)
        if not ident_pattern.match(name_val):
            report_error(f"3. Properties: Name '{name_val}' is not a valid 1C identifier")
            check3_ok = False
        if len(name_val) > 80:
            report_warn(f"3. Properties: Name '{name_val}' is longer than 80 characters ({len(name_val)})")

    # Synonym
    syn_node = find(props_node, "md:Synonym")
    syn_present = False
    if syn_node is not None:
        syn_item = find(syn_node, "v8:item")
        if syn_item is not None:
            syn_content = find(syn_item, "v8:content")
            if syn_content is not None and inner_text(syn_content):
                syn_present = True

    if check3_ok:
        syn_info = "Synonym present" if syn_present else "no Synonym"
        report_ok(f'3. Properties: Name="{obj_name}", {syn_info}')

if stopped:
    finalize()
    sys.exit(1)

# ── Check 4: Property values -- enum properties ──────────────

if props_node is not None:
    enum_checked = 0
    check4_ok = True

    for prop_name, allowed in valid_property_values.items():
        if "." in prop_name:   # "Вид.Свойство" is a refinement, not a separate property
            continue
        prop_node = find(props_node, f"md:{prop_name}")
        if prop_node is not None and inner_text(prop_node):
            val = inner_text(prop_node)
            allowed = valid_property_values.get(f"{md_type}.{prop_name}") or allowed
            if val not in allowed:
                report_error(f"4. Property '{prop_name}' has invalid value '{val}' (allowed: {', '.join(allowed)})")
                check4_ok = False
            enum_checked += 1

    # The root <Type> (value type descriptor - Константа, ПВХ) must be structural:
    # <v8:Type>/<v8:TypeSet>, not scalar text. Scalar = corrupted type (e.g. after
    # an old meta-edit modify-property Type). See issue #42.
    root_type_el = find(props_node, "md:Type")
    if root_type_el is not None:
        scalar_text = inner_text(root_type_el).strip()
        v8_types = find_all(root_type_el, "v8:Type")
        v8_type_sets = find_all(root_type_el, "v8:TypeSet")
        if len(v8_types) == 0 and len(v8_type_sets) == 0 and scalar_text:
            report_error(f"4. Property <Type> содержит скалярный текст '{scalar_text}' без структуры типа (<v8:Type>/<v8:TypeSet>) — повреждённый дескриптор типа значения")
            check4_ok = False

    if check4_ok:
        report_ok(f"4. Property values: {enum_checked} enum properties checked")
else:
    report_warn("4. No Properties block to check")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 5: StandardAttributes ──────────────────────────────

if md_type in types_with_std_attrs:
    std_attr_node = find(props_node, "md:StandardAttributes")
    if std_attr_node is None:
        report_ok(f"5. StandardAttributes: absent (optional for {md_type})")
    else:
        std_attrs = find_all(std_attr_node, "xr:StandardAttribute")
        expected_std_attrs = standard_attributes_by_type.get(md_type, [])
        check5_ok = True

        found_names = []
        for sa in std_attrs:
            sa_name = sa.get("name", "")
            if sa_name:
                found_names.append(sa_name)
                if sa_name not in expected_std_attrs:
                    # AccountingRegister: pairs of subaccounts, the number of which is set by the chart of accounts
                    is_dynamic = (md_type == "AccountingRegister" and
                                  (re.match(r'^ExtDimension\d+$', sa_name) or
                                   re.match(r'^ExtDimensionType\d+$', sa_name)))
                    if not is_dynamic:
                        report_warn(f"5. Unexpected StandardAttribute '{sa_name}' for {md_type}")
            else:
                report_error("5. StandardAttribute without 'name' attribute")
                check5_ok = False

        if expected_std_attrs:
            cond_names = std_attr_conditional_names.get(md_type, ())
            missing_attrs = [a for a in expected_std_attrs if a not in found_names and a not in cond_names]
            if missing_attrs:
                report_warn(f"5. Missing StandardAttributes: {', '.join(missing_attrs)}")

        if check5_ok:
            report_ok(f"5. StandardAttributes: {len(std_attrs)} entries")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 6: ChildObjects -- allowed element types ───────────

child_obj_node = find(type_node, "md:ChildObjects")
allowed_children = child_object_rules.get(md_type, [])

if child_obj_node is not None:
    check6_ok = True
    child_counts = {}

    for child in child_obj_node:
        if not isinstance(child.tag, str):
            continue
        child_tag = local_name(child)

        if child_tag not in allowed_children:
            report_error(f"6. ChildObjects: disallowed element '{child_tag}' for {md_type}")
            check6_ok = False

        child_counts[child_tag] = child_counts.get(child_tag, 0) + 1

    if check6_ok:
        summary = ", ".join(f"{k}({v})" for k, v in sorted(child_counts.items()))
        if summary:
            report_ok(f"6. ChildObjects types: {summary}")
        else:
            report_ok(f"6. ChildObjects: empty (valid for {md_type})")
elif len(allowed_children) == 0:
    report_ok(f"6. ChildObjects: absent (correct for {md_type})")
else:
    report_ok("6. ChildObjects: absent")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 7: Child elements -- UUID, Name, Type ──────────────


def check_child_element(node, kind, require_type):
    uuid = node.get("uuid", "")
    if not uuid:
        report_error(f"7. {kind} missing uuid")
        return False
    if not guid_pattern.match(uuid):
        report_error(f"7. {kind} has invalid uuid '{uuid}'")
        return False

    el_props = find(node, "md:Properties")
    if el_props is None:
        report_error(f"7. {kind} (uuid={uuid}) missing Properties")
        return False

    el_name = find(el_props, "md:Name")
    if el_name is None or not inner_text(el_name):
        report_error(f"7. {kind} (uuid={uuid}) missing or empty Name")
        return False

    name_val = inner_text(el_name)
    if not ident_pattern.match(name_val):
        report_error(f"7. {kind} '{name_val}' has invalid identifier")
        return False

    if require_type:
        type_el = find(el_props, "md:Type")
        # An empty <Type/> means the "Произвольный" type, a standard construct: in typical configurations this is how
        # service attributes of data processors are described, the platform accepts and saves it unchanged
        # (verified by round-trip). An error here would be a refusal where the platform does not refuse.
        if type_el is None:
            # There is no Type block at all: loading succeeds, but the platform silently substitutes the new
            # attribute type - Строка(10). This does not break loading but loses the intent, hence WARN.
            report_warn(f"7. {kind} '{name_val}' — блок Type не задан; при загрузке платформа подставит Строка(10)")

    return True


if child_obj_node is not None:
    check7_ok = True
    check7_count = 0
    element_kinds = ("Attribute", "Dimension", "Resource", "EnumValue", "Column")

    for kind in element_kinds:
        elements = find_all(child_obj_node, f"md:{kind}")
        require_type = kind not in ("EnumValue", "Column")
        for el in elements:
            if stopped:
                break
            ok = check_child_element(el, kind, require_type)
            if not ok:
                check7_ok = False
            check7_count += 1

    if check7_ok and check7_count > 0:
        report_ok(f"7. Child elements: {check7_count} items checked (UUID, Name, Type)")
    elif check7_count == 0:
        report_ok("7. Child elements: none to check")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 7b: Reserved attribute names (type-dependent: standard ones of THIS type, EN+RU) ───────
# The platform will not accept a custom attribute name matching a standard one (English or Russian) -> error.

RESERVED_EN_RU = {
    'Ref': 'Ссылка', 'DeletionMark': 'ПометкаУдаления', 'Code': 'Код', 'Description': 'Наименование',
    'Date': 'Дата', 'Number': 'Номер', 'Posted': 'Проведен', 'Parent': 'Родитель', 'Owner': 'Владелец',
    'IsFolder': 'ЭтоГруппа', 'Predefined': 'Предопределенный', 'PredefinedDataName': 'ИмяПредопределенныхДанных',
    'Recorder': 'Регистратор', 'Period': 'Период', 'LineNumber': 'НомерСтроки', 'Active': 'Активность',
    'Order': 'Порядок', 'Type': 'Тип', 'OffBalance': 'Забалансовый', 'RecordType': 'ВидДвижения',
    'Started': 'Стартован', 'Completed': 'Завершен', 'HeadTask': 'ВедущаяЗадача',
    'Executed': 'Выполнена', 'RoutePoint': 'ТочкаМаршрута', 'BusinessProcess': 'БизнесПроцесс',
    'ThisNode': 'ЭтотУзел', 'SentNo': 'НомерОтправленного', 'ReceivedNo': 'НомерПринятого',
    'CalculationType': 'ВидРасчета', 'RegistrationPeriod': 'ПериодРегистрации', 'ReversingEntry': 'СторноЗапись',
    'Account': 'Счет', 'ValueType': 'ТипЗначения', 'ActionPeriodIsBasic': 'ПериодДействияБазовый',
}

std_for_type = standard_attributes_by_type.get(md_type)
if child_obj_node is not None and std_for_type:
    reserved_set = set()
    for en in std_for_type:
        reserved_set.add(en.lower())
        ru = RESERVED_EN_RU.get(en)
        if ru:
            reserved_set.add(ru.lower())
    check7b_ok = True
    for attr_node in find_all(child_obj_node, 'md:Attribute'):
        attr_props = find(attr_node, 'md:Properties')
        if attr_props is not None:
            attr_name_node = find(attr_props, 'md:Name')
            if attr_name_node is not None and inner_text(attr_name_node):
                an = inner_text(attr_name_node)
                if an.lower() in reserved_set:
                    report_error(f"7b. Attribute '{an}' conflicts with a standard attribute of {md_type}")
                    check7b_ok = False
    if check7b_ok:
        report_ok("7b. Reserved attribute names: no conflicts")
elif child_obj_node is not None:
    report_ok(f"7b. Reserved attribute names: no conflicts (no standard set for {md_type})")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 8: Name uniqueness ─────────────────────────────────


def check_uniqueness(nodes, kind):
    names = {}
    has_dupes = False
    for node in nodes:
        el_props = find(node, "md:Properties")
        if el_props is None:
            continue
        el_name = find(el_props, "md:Name")
        if el_name is None or not inner_text(el_name):
            continue
        name_val = inner_text(el_name)
        if name_val in names:
            report_error(f"8. Duplicate {kind} name: '{name_val}'")
            has_dupes = True
        else:
            names[name_val] = True
    return not has_dupes


if child_obj_node is not None:
    check8_ok = True

    # Attributes
    attrs = find_all(child_obj_node, "md:Attribute")
    if len(attrs) > 0:
        if not check_uniqueness(attrs, "Attribute"):
            check8_ok = False

    # TabularSections
    tss = find_all(child_obj_node, "md:TabularSection")
    if len(tss) > 0:
        if not check_uniqueness(tss, "TabularSection"):
            check8_ok = False

    # Dimensions
    dims = find_all(child_obj_node, "md:Dimension")
    if len(dims) > 0:
        if not check_uniqueness(dims, "Dimension"):
            check8_ok = False

    # Resources
    ress = find_all(child_obj_node, "md:Resource")
    if len(ress) > 0:
        if not check_uniqueness(ress, "Resource"):
            check8_ok = False

    # EnumValues
    evs = find_all(child_obj_node, "md:EnumValue")
    if len(evs) > 0:
        if not check_uniqueness(evs, "EnumValue"):
            check8_ok = False

    # Columns (DocumentJournal)
    cols = find_all(child_obj_node, "md:Column")
    if len(cols) > 0:
        if not check_uniqueness(cols, "Column"):
            check8_ok = False

    # URLTemplates (HTTPService)
    url_ts = find_all(child_obj_node, "md:URLTemplate")
    if len(url_ts) > 0:
        if not check_uniqueness(url_ts, "URLTemplate"):
            check8_ok = False

    # Operations (WebService)
    ops = find_all(child_obj_node, "md:Operation")
    if len(ops) > 0:
        if not check_uniqueness(ops, "Operation"):
            check8_ok = False

    if check8_ok:
        report_ok("8. Name uniqueness: all names unique")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 9: TabularSections -- internal structure ───────────

if child_obj_node is not None:
    ts_sections = find_all(child_obj_node, "md:TabularSection")
    if len(ts_sections) > 0:
        check9_ok = True
        ts_count = 0

        for ts in ts_sections:
            if stopped:
                break
            ts_count += 1

            # UUID
            ts_uuid = ts.get("uuid", "")
            if not ts_uuid or not guid_pattern.match(ts_uuid):
                report_error(f"9. TabularSection #{ts_count}: invalid or missing uuid")
                check9_ok = False

            # Name
            ts_props = find(ts, "md:Properties")
            ts_name_node = find(ts_props, "md:Name") if ts_props is not None else None
            ts_name = inner_text(ts_name_node) if ts_name_node is not None else "(unnamed)"

            if ts_name_node is None or not inner_text(ts_name_node):
                report_error(f"9. TabularSection #{ts_count}: missing or empty Name")
                check9_ok = False

            # InternalInfo with 2 GeneratedType
            ts_int_info = find(ts, "md:InternalInfo")
            if ts_int_info is not None:
                ts_gens = find_all(ts_int_info, "xr:GeneratedType")
                if len(ts_gens) < 2:
                    report_warn(f"9. TabularSection '{ts_name}': expected 2 GeneratedType, found {len(ts_gens)}")

            # Attributes inside TS
            ts_child_obj = find(ts, "md:ChildObjects")
            if ts_child_obj is not None:
                ts_attrs = find_all(ts_child_obj, "md:Attribute")
                ts_attr_names = {}
                for ta in ts_attrs:
                    ta_ok = check_child_element(ta, f"TabularSection '{ts_name}'.Attribute", True)
                    if not ta_ok:
                        check9_ok = False

                    # Check name uniqueness within TS
                    ta_props = find(ta, "md:Properties")
                    ta_name = find(ta_props, "md:Name") if ta_props is not None else None
                    if ta_name is not None and inner_text(ta_name):
                        if inner_text(ta_name) in ts_attr_names:
                            report_error(f"9. Duplicate attribute '{inner_text(ta_name)}' in TabularSection '{ts_name}'")
                            check9_ok = False
                        else:
                            ts_attr_names[inner_text(ta_name)] = True

                # StandardAttributes of TS: expect LineNumber
                if ts_props is not None:
                    ts_std_attr = find(ts_props, "md:StandardAttributes")
                    if ts_std_attr is not None:
                        ts_std_attrs = find_all(ts_std_attr, "xr:StandardAttribute")
                        has_line_number = False
                        for tsa in ts_std_attrs:
                            if tsa.get("name") == "LineNumber":
                                has_line_number = True
                        if not has_line_number:
                            report_warn(f"9. TabularSection '{ts_name}': missing LineNumber StandardAttribute")

        if check9_ok:
            report_ok(f"9. TabularSections: {ts_count} sections, structure valid")
    else:
        report_ok("9. TabularSections: none present")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 10: Cross-property consistency ─────────────────────

check10_ok = True
check10_issues = 0

if props_node is not None:
    # HierarchyType set but Hierarchical = false
    hierarchical = find(props_node, "md:Hierarchical")
    hierarchy_type = find(props_node, "md:HierarchyType")
    # The platform always writes HierarchyType, regardless of Hierarchical, and with hierarchy disabled
    # simply ignores it (verified: the value survives round-trip). The default value therefore says
    # nothing - we warn only about an explicitly set different hierarchy type: this looks like
    # "a hierarchy type was chosen but enabling the hierarchy itself was forgotten".
    if (hierarchical is not None and hierarchy_type is not None and
            inner_text(hierarchical) == "false" and inner_text(hierarchy_type)
            and inner_text(hierarchy_type) != "HierarchyFoldersAndItems"):
        report_warn(f"10. HierarchyType='{inner_text(hierarchy_type)}' but Hierarchical=false")
        check10_issues += 1

    # Zero-length code/number in input by string: the platform rejects loading - "Указано неверное
    # поле для ввода по строке: Код/Номер" (8.3.24, 8.5.1). Happens after changing the length to 0 without cleaning
    # InputByString (meta-edit no longer does this, but that does not protect against manual edits).
    ibs_fields = [inner_text(f).strip() for f in find_all(props_node, "md:InputByString/xr:Field")]
    for len_prop, std_attr in (("CodeLength", "Code"), ("NumberLength", "Number")):
        len_node = find(props_node, f"md:{len_prop}")
        if len_node is None or inner_text(len_node).strip() != "0":
            continue
        hit = next((f for f in ibs_fields if f.endswith(f".StandardAttribute.{std_attr}")), None)
        if hit:
            report_error(f"10. InputByString contains '{hit}' but {len_prop}=0 — the platform rejects it (invalid input-by-string field)")
            check10_ok = False
            check10_issues += 1

    # CommonModule: no context enabled
    if md_type == "CommonModule":
        contexts = ("Server", "ClientManagedApplication", "ClientOrdinaryApplication",
                     "ExternalConnection", "ServerCall", "Global")
        any_enabled = False
        for ctx in contexts:
            ctx_node = find(props_node, f"md:{ctx}")
            if ctx_node is not None and inner_text(ctx_node) == "true":
                any_enabled = True
                break
        if not any_enabled:
            report_warn("10. CommonModule: no execution context enabled")
            check10_issues += 1

    # EventSubscription: empty Handler
    if md_type == "EventSubscription":
        handler = find(props_node, "md:Handler")
        if handler is None or not text_of(handler):
            report_error("10. EventSubscription: empty Handler")
            check10_ok = False
            check10_issues += 1

        # Empty Source
        source = find(props_node, "md:Source")
        # Sources are also set by type sets (<v8:TypeSet>cfg:CatalogObject</v8:TypeSet>) - in typical configurations
        # every fourth subscription is described this way. A really empty source is rejected by the platform:
        # "ПодпискаНаСобытие.X - Источник событий должен быть задан", so this is an error.
        has_source = False
        if source is not None:
            source_types = find_all(source, "v8:Type")
            source_type_sets = find_all(source, "v8:TypeSet")
            if len(source_types) > 0 or len(source_type_sets) > 0:
                has_source = True
        if not has_source:
            report_error("10. EventSubscription: источник событий не задан — платформа отвергнет загрузку")
            check10_issues += 1

    # ScheduledJob: empty MethodName
    if md_type == "ScheduledJob":
        method = find(props_node, "md:MethodName")
        if method is None or not text_of(method):
            report_error("10. ScheduledJob: empty MethodName")
            check10_ok = False
            check10_issues += 1

    # AccountingRegister: ChartOfAccounts must not be empty
    if md_type == 'AccountingRegister':
        coa = find(props_node, 'md:ChartOfAccounts')
        if coa is None or not text_of(coa):
            report_error('10. AccountingRegister: empty ChartOfAccounts')
            check10_ok = False
            check10_issues += 1
            print('[HINT] /meta-edit -Operation modify-property -Value "ChartOfAccounts=ChartOfAccounts.XXX"')

    # CalculationRegister: ChartOfCalculationTypes must not be empty
    if md_type == 'CalculationRegister':
        coct = find(props_node, 'md:ChartOfCalculationTypes')
        if coct is None or not text_of(coct):
            report_error('10. CalculationRegister: empty ChartOfCalculationTypes')
            check10_ok = False
            check10_issues += 1
            print('[HINT] /meta-edit -Operation modify-property -Value "ChartOfCalculationTypes=ChartOfCalculationTypes.XXX"')

    # BusinessProcess: Task should not be empty
    if md_type == 'BusinessProcess':
        task_prop = find(props_node, 'md:Task')
        if task_prop is None or not text_of(task_prop):
            report_warn('10. BusinessProcess: empty Task reference')
            check10_issues += 1
            print('[HINT] /meta-edit -Operation modify-property -Value "Task=Task.XXX"')

    # CalculationRegister: ActionPeriod=true requires non-empty Schedule
    if md_type == 'CalculationRegister':
        action_period = find(props_node, 'md:ActionPeriod')
        if action_period is not None and text_of(action_period) == 'true':
            schedule = find(props_node, 'md:Schedule')
            if schedule is None or not text_of(schedule):
                report_warn('10. CalculationRegister: ActionPeriod=true but Schedule is empty — platform requires a schedule register')
                check10_issues += 1

    # DocumentJournal: RegisteredDocuments should not be empty
    if md_type == 'DocumentJournal':
        reg_docs = find(props_node, 'md:RegisteredDocuments')
        # The platform lists registered documents as <xr:Item xsi:type="xr:MDObjectRef">,
        # meta-compile writes them the same way; the <v8:Type> form is kept for other kinds of dumps.
        # An empty composition is rejected by the platform: "Для журнала не заданы регистрируемые документы".
        has_reg_docs = False
        if reg_docs is not None:
            items = find_all(reg_docs, 'v8:Type')
            ref_items = find_all(reg_docs, 'xr:Item')
            if len(items) > 0 or len(ref_items) > 0:
                has_reg_docs = True
        if not has_reg_docs:
            report_error('10. DocumentJournal: регистрируемые документы не заданы — платформа отвергнет загрузку')
            check10_issues += 1

    # ChartOfAccounts: ExtDimensionTypes should be set if MaxExtDimensionCount > 0
    if md_type == 'ChartOfAccounts':
        max_ext_dim = find(props_node, 'md:MaxExtDimensionCount')
        if max_ext_dim is not None:
            try:
                med_val = int(inner_text(max_ext_dim) or '0')
            except ValueError:
                med_val = 0
            if med_val > 0:
                edt = find(props_node, 'md:ExtDimensionTypes')
                if edt is None or not text_of(edt):
                    report_warn('10. ChartOfAccounts: MaxExtDimensionCount>0 but ExtDimensionTypes is empty')
                    check10_issues += 1
                    print('[HINT] /meta-edit -Operation modify-property -Value "ExtDimensionTypes=ChartOfCharacteristicTypes.XXX"')

    # Register: must have at least one Dimension or Resource (platform rejects empty registers)
    reg_types_all = ('AccumulationRegister', 'AccountingRegister', 'CalculationRegister', 'InformationRegister')
    if md_type in reg_types_all and child_obj_node is not None:
        dims = len(find_all(child_obj_node, 'md:Dimension'))
        ress = len(find_all(child_obj_node, 'md:Resource'))
        attrs = len(find_all(child_obj_node, 'md:Attribute'))
        if dims + ress + attrs == 0:
            report_warn(f"10. {md_type}: no Dimensions, Resources, or Attributes \u2014 platform will reject")
            check10_issues += 1

    # Document: RegisterRecords references should point to existing objects in config
    if md_type == 'Document' and config_dir:
        reg_records = find(props_node, 'md:RegisterRecords')
        if reg_records is not None:
            rr_items = find_all(reg_records, 'xr:Item')
            for item in rr_items:
                ref_val = (inner_text(item) or '').strip()
                if not ref_val:
                    continue
                # Parse "AccumulationRegister.Name" -> dir AccumulationRegisters/Name
                parts = ref_val.split('.', 1)
                if len(parts) == 2:
                    ref_type, ref_name = parts
                    dir_map = {
                        'AccumulationRegister': 'AccumulationRegisters',
                        'InformationRegister': 'InformationRegisters',
                        'AccountingRegister': 'AccountingRegisters',
                        'CalculationRegister': 'CalculationRegisters',
                    }
                    ref_dir = dir_map.get(ref_type)
                    if ref_dir:
                        ref_path = os.path.join(config_dir, ref_dir, ref_name)
                        ref_xml = os.path.join(config_dir, ref_dir, ref_name + '.xml')
                        if not os.path.exists(ref_path) and not os.path.exists(ref_xml):
                            report_warn(f"10. Document.RegisterRecords references '{ref_val}' but object not found in config")
                            check10_issues += 1

    # Register: must have at least one registrar document
    register_types = ('AccumulationRegister', 'AccountingRegister', 'CalculationRegister', 'InformationRegister')
    if md_type in register_types and config_dir and obj_name != '(unknown)':
        needs_registrar = True
        # InformationRegister with WriteMode=Independent does not need a registrar
        if md_type == 'InformationRegister':
            write_mode = find(props_node, 'md:WriteMode')
            if write_mode is None or inner_text(write_mode) != 'RecorderSubordinate':
                needs_registrar = False
        if needs_registrar:
            reg_ref = f'{md_type}.{obj_name}'
            docs_dir = os.path.join(config_dir, 'Documents')
            has_registrar = False
            if os.path.isdir(docs_dir):
                for fname in os.listdir(docs_dir):
                    if not fname.endswith('.xml'):
                        continue
                    fpath = os.path.join(docs_dir, fname)
                    if not os.path.isfile(fpath):
                        continue
                    with open(fpath, 'r', encoding='utf-8-sig') as f:
                        content = f.read()
                    if reg_ref in content:
                        has_registrar = True
                        break
            if not has_registrar:
                report_warn(f"10. {md_type}: no registrar document found (none references '{reg_ref}' in RegisterRecords)")
                check10_issues += 1

if check10_ok and check10_issues == 0:
    report_ok("10. Cross-property consistency")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 11: HTTPService/WebService nested structure ────────

if md_type == "HTTPService" and child_obj_node is not None:
    url_templates = find_all(child_obj_node, "md:URLTemplate")
    check11_ok = True
    method_count = 0

    valid_http_methods = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "MERGE", "CONNECT")

    for ut in url_templates:
        if stopped:
            break

        ut_props = find(ut, "md:Properties")
        ut_name_node = find(ut_props, "md:Name") if ut_props is not None else None
        ut_name = inner_text(ut_name_node) if ut_name_node is not None else "(unnamed)"

        # Template property
        tpl = find(ut_props, "md:Template") if ut_props is not None else None
        if tpl is None or not text_of(tpl):
            report_error(f"11. HTTPService URLTemplate '{ut_name}': empty Template")
            check11_ok = False

        # Methods inside URLTemplate
        ut_child_obj = find(ut, "md:ChildObjects")
        if ut_child_obj is not None:
            methods = find_all(ut_child_obj, "md:Method")
            for m in methods:
                method_count += 1
                m_props = find(m, "md:Properties")
                if m_props is not None:
                    http_method = find(m_props, "md:HTTPMethod")
                    if http_method is not None and inner_text(http_method):
                        if inner_text(http_method) not in valid_http_methods:
                            report_error(f"11. HTTPService URLTemplate '{ut_name}': invalid HTTPMethod '{inner_text(http_method)}'")
                            check11_ok = False
                    else:
                        report_error(f"11. HTTPService URLTemplate '{ut_name}': Method missing HTTPMethod")
                        check11_ok = False

    if check11_ok:
        report_ok(f"11. HTTPService: {len(url_templates)} URLTemplate(s), {method_count} method(s)")

elif md_type == "WebService" and child_obj_node is not None:
    operations = find_all(child_obj_node, "md:Operation")
    check11_ok = True
    param_count = 0

    valid_directions = ("In", "Out", "InOut")

    for op in operations:
        if stopped:
            break

        op_props = find(op, "md:Properties")
        op_name_node = find(op_props, "md:Name") if op_props is not None else None
        op_name = inner_text(op_name_node) if op_name_node is not None else "(unnamed)"

        # ReturnType
        ret_type = find(op_props, "md:XDTOReturningValueType") if op_props is not None else None
        if ret_type is None or not text_of(ret_type):
            report_warn(f"11. WebService Operation '{op_name}': no XDTOReturningValueType")

        # Parameters inside Operation
        op_child_obj = find(op, "md:ChildObjects")
        if op_child_obj is not None:
            params = find_all(op_child_obj, "md:Parameter")
            for p in params:
                param_count += 1
                p_props = find(p, "md:Properties")
                if p_props is not None:
                    direction = find(p_props, "md:TransferDirection")
                    if direction is not None and inner_text(direction) and inner_text(direction) not in valid_directions:
                        report_error(f"11. WebService Operation '{op_name}': Parameter has invalid TransferDirection '{inner_text(direction)}'")
                        check11_ok = False

    if check11_ok:
        report_ok(f"11. WebService: {len(operations)} operation(s), {param_count} parameter(s)")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 12: Forbidden properties per type ──────────────────

if props_node is not None and md_type in forbidden_properties:
    forbidden = forbidden_properties[md_type]
    check12_ok = True
    for fp in forbidden:
        fp_node = find(props_node, f"md:{fp}")
        if fp_node is not None:
            report_error(f"12. Forbidden property '{fp}' present in {md_type} (will fail on LoadConfigFromFiles)")
            check12_ok = False
    if check12_ok:
        report_ok("12. Forbidden properties: none found")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 13: Method reference validation ─────────────────────

if props_node is not None and md_type in ("EventSubscription", "ScheduledJob") and config_dir:
    check13_ok = True
    method_ref = None
    prop_label = None

    if md_type == "EventSubscription":
        h_node = find(props_node, "md:Handler")
        if h_node is not None:
            method_ref = text_of(h_node)
        prop_label = "Handler"
    elif md_type == "ScheduledJob":
        m_node = find(props_node, "md:MethodName")
        if m_node is not None:
            method_ref = text_of(m_node)
        prop_label = "MethodName"

    if method_ref:
        parts = method_ref.split(".")
        # Format: CommonModule.ModuleName.ProcedureName (3 parts) or ModuleName.ProcedureName (2 parts, legacy)
        if len(parts) == 3 and parts[0] == "CommonModule":
            cm_name = parts[1]
            proc_name = parts[2]
        elif len(parts) == 2:
            cm_name = parts[0]
            proc_name = parts[1]
        else:
            report_error(f"13. {md_type}.{prop_label} = '{method_ref}': expected format 'CommonModule.ModuleName.ProcedureName'")
            check13_ok = False
            cm_name = None
            proc_name = None
        if cm_name:
            cm_xml = os.path.join(config_dir, "CommonModules", f"{cm_name}.xml")
            if not os.path.exists(cm_xml):
                report_error(f"13. {md_type}.{prop_label}: CommonModule '{cm_name}' not found (expected {cm_xml})")
                check13_ok = False
            else:
                # Check BSL file for exported procedure
                bsl_path = os.path.join(config_dir, "CommonModules", cm_name, "Ext", "Module.bsl")
                if os.path.exists(bsl_path):
                    with open(bsl_path, "r", encoding="utf-8-sig") as f:
                        bsl_content = f.read()
                    # The parameter list wraps to following lines, and Экспорт ends up not on
                    # the line with the name - in typical configurations this is how every handler procedure with a long
                    # signature is declared. Hence (?s) for the parenthesis content and \s (not a space) before Экспорт.
                    export_pattern = rf"(?smi)^[ 	]*(Procedure|Function|Процедура|Функция)[ 	]+{re.escape(proc_name)}[ 	]*\([^)]*\)\s+(Export|Экспорт)"
                    if not re.search(export_pattern, bsl_content):
                        report_warn(f"13. {md_type}.{prop_label}: procedure '{proc_name}' not found as exported in CommonModule '{cm_name}'")
                        check13_ok = False
                elif os.path.exists(os.path.splitext(bsl_path)[0] + ".bin"):
                    # The vendor module is dumped in binary form (Module.bin) - there is no text by design,
                    # nothing to check. Warning here would mean making noise about the norm.
                    pass
                else:
                    report_warn(f"13. {md_type}.{prop_label}: BSL file not found ({bsl_path}), cannot verify procedure")

    if check13_ok:
        report_ok(f"13. Method reference: {prop_label} = '{method_ref}'")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 14: DocumentJournal Column content ──────────────────

if md_type == "DocumentJournal" and child_obj_node is not None:
    columns = find_all(child_obj_node, "md:Column")
    check14_ok = True
    col_count = 0
    empty_ref_count = 0

    for col in columns:
        col_count += 1
        col_props = find(col, "md:Properties")
        col_name_node = find(col_props, "md:Name") if col_props is not None else None
        col_name = inner_text(col_name_node) if col_name_node is not None else "(unnamed)"

        refs = find(col_props, "md:References") if col_props is not None else None
        has_items = False
        if refs is not None:
            items = find_all(refs, "xr:Item")
            if len(items) > 0:
                has_items = True
        if not has_items:
            report_error(f"14. DocumentJournal Column '{col_name}': empty References (will fail on LoadConfigFromFiles)")
            check14_ok = False
            empty_ref_count += 1

    if check14_ok and col_count > 0:
        report_ok(f"14. DocumentJournal Columns: {col_count} column(s), all have References")
    elif col_count == 0:
        report_ok("14. DocumentJournal Columns: none")

if stopped:
    finalize()
    sys.exit(1)

# ── Check 15: Commands - Group required/valid; a section group is incompatible with CommandParameterType ──

if child_obj_node is not None:
    commands = find_all(child_obj_node, "md:Command")
    check15_ok = True
    cmd_count = 0
    for cmd in commands:
        if stopped:
            break
        cmd_count += 1
        cuuid = cmd.get("uuid", "")
        cmd_props = find(cmd, "md:Properties")
        cmd_name_node = find(cmd_props, "md:Name") if cmd_props is not None else None
        cmd_name = inner_text(cmd_name_node) if (cmd_name_node is not None and inner_text(cmd_name_node)) else "(unnamed)"
        if not cuuid or not guid_pattern.match(cuuid):
            report_error(f"15. Command '{cmd_name}': missing or invalid uuid")
            check15_ok = False
        if cmd_name == "(unnamed)":
            report_error(f"15. Command (uuid={cuuid}): missing or empty Name")
            check15_ok = False
        group_node = find(cmd_props, "md:Group") if cmd_props is not None else None
        group_val = inner_text(group_node).strip() if group_node is not None else ""
        if not group_val:
            report_error(f"15. Command '{cmd_name}': не задана группа (Group) — 1С отвергает при загрузке")
            check15_ok = False
        elif group_val not in VALID_COMMAND_GROUPS and not group_val.startswith("CommandGroup."):
            report_error(f"15. Command '{cmd_name}': неизвестная группа '{group_val}'. "
                         f"Валидные: {', '.join(VALID_COMMAND_GROUPS)}; либо CommandGroup.<Имя>")
            check15_ok = False
        elif group_val in SECTION_COMMAND_GROUPS:
            cpt_node = find(cmd_props, "md:CommandParameterType") if cmd_props is not None else None
            has_cpt = cpt_node is not None and (len(find_all(cpt_node, "v8:Type")) > 0 or len(find_all(cpt_node, "v8:TypeSet")) > 0)
            if has_cpt:
                report_error(f"15. Command '{cmd_name}': тип параметра (CommandParameterType) недоступен "
                             f"для команд командного интерфейса раздела ('{group_val}')")
                check15_ok = False
    if check15_ok and cmd_count > 0:
        report_ok(f"15. Commands: {cmd_count} command(s), groups valid")

# ── Configuration composition (ChildObjects from Configuration.xml) ──
# The platform judges object existence by COMPOSITION, not by file presence. The file may be absent
# in a partial dump: such a fragment is loaded via /LoadConfigFromFiles -listFile merged with the database,
# and a reference to a non-dumped object remains valid. Hence two different outcomes:
#   not in composition       -> the platform will always reject loading -> ERROR
#   in composition, no file  -> full load fails, partial passes -> WARN
# Configuration ChildObjects is a flat list <Вид>Имя</Вид>, so we search for a substring within section boundaries
# without copying and without parsing XML. The cache lives only within one object: in batch mode
# each next one is parsed anew (new process / clean namespace),
# so the full map (~100 ms) would be paid by every object.

_cfg_text = None
_cfg_child_lower = None
_cfg_child_start = -1
_cfg_child_end = -1
_cfg_text_loaded = False


def _init_config_text():
    global _cfg_text, _cfg_child_start, _cfg_child_end, _cfg_text_loaded
    if _cfg_text_loaded:
        return
    _cfg_text_loaded = True
    if not config_dir:
        return
    cfg_path = os.path.join(config_dir, "Configuration.xml")
    if not os.path.exists(cfg_path):
        return
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            _cfg_text = f.read()
    except Exception:
        _cfg_text = None
        return
    s = _cfg_text.find("<ChildObjects>")
    e = _cfg_text.rfind("</ChildObjects>")
    if s >= 0 and e > s:
        _cfg_child_start = s
        _cfg_child_end = e


def config_is_extension():
    _init_config_text()
    return bool(_cfg_text) and "ConfigurationExtensionPurpose" in _cfg_text


def in_config_composition(kind, name):
    """True - the object is in the composition; False - not; None - the composition is unknown
    (no Configuration.xml or no ChildObjects in it), then the caller keeps the soft level."""
    global _cfg_child_lower
    _init_config_text()
    if _cfg_child_start < 0:
        return None
    needle = "<{0}>{1}</{0}>".format(kind, name)
    if _cfg_text.find(needle, _cfg_child_start, _cfg_child_end) >= 0:
        return True
    # On an exact match miss - compare case-insensitively, as the platform does.
    # The order is exactly this: exact search is an order of magnitude cheaper, and misses are rare. Lower case
    # is taken from the SLICE and we check the fact of occurrence: offsets in lower() need not match the original.
    if _cfg_child_lower is None:
        _cfg_child_lower = _cfg_text[_cfg_child_start:_cfg_child_end].lower()
    return needle.lower() in _cfg_child_lower


# ── Check 16: Reference type existence - types like CatalogRef.X must resolve to configuration objects ──
# The level is chosen by configuration composition: the type is not in ChildObjects - "Неизвестное имя типа" on
# load (ERROR); the object is in the composition but there is no file in the dump - partial dump (WARN).
# We skip extensions (CFE) - their types reference base configuration objects that are absent from the extension
# dump.

if config_dir:
    is_extension = config_is_extension()
    if not is_extension:
        ref_dir_map = {
            "CatalogRef": "Catalogs", "DocumentRef": "Documents", "EnumRef": "Enums",
            "ChartOfAccountsRef": "ChartsOfAccounts", "ChartOfCharacteristicTypesRef": "ChartsOfCharacteristicTypes",
            "ChartOfCalculationTypesRef": "ChartsOfCalculationTypes", "BusinessProcessRef": "BusinessProcesses",
            "ExchangePlanRef": "ExchangePlans", "TaskRef": "Tasks", "DefinedType": "DefinedTypes",
        }
        checked_refs = {}   # ref_key -> whether found; for the OK condition
        missing_refs = {}   # ref_key -> ref_dir; the object is in the composition, no file in the dump
        absent_refs = {}    # ref_key -> ref_dir; the object is not in the configuration composition
        unknown_refs = {}   # ref_key -> ref_dir; composition unknown (Configuration.xml without ChildObjects)
        for tn in find_all(root, ".//v8:Type"):
            tv = inner_text(tn).strip()
            if not tv:
                continue
            colon_idx = tv.find(":")
            if colon_idx >= 0:
                tv = tv[colon_idx + 1:]
            dot_idx = tv.find(".")
            if dot_idx < 0:
                continue
            ref_cat = tv[:dot_idx]
            ref_name = tv[dot_idx + 1:]
            ref_dir = ref_dir_map.get(ref_cat)
            if not ref_dir or not ref_name:
                continue
            ref_key = f"{ref_cat}.{ref_name}"
            if ref_key in checked_refs:
                continue
            ref_folder = os.path.join(config_dir, ref_dir, ref_name)
            ref_file = os.path.join(config_dir, ref_dir, ref_name + ".xml")
            if os.path.exists(ref_folder) or os.path.exists(ref_file):
                checked_refs[ref_key] = True
            else:
                checked_refs[ref_key] = False
                # The metadata kind in ChildObjects is the type without the Ref suffix (CatalogRef -> Catalog);
                # DefinedType has no suffix and is written to the composition as is.
                ref_kind_tag = ref_cat[:-3] if ref_cat.endswith("Ref") else ref_cat
                in_composition = in_config_composition(ref_kind_tag, ref_name)
                if in_composition is False:
                    absent_refs[ref_key] = ref_dir
                elif in_composition is True:
                    missing_refs[ref_key] = ref_dir
                else:
                    unknown_refs[ref_key] = ref_dir
        for ak in sorted(absent_refs):
            report_error(f"16. Ссылочный тип '{ak}' — объекта нет в составе конфигурации ({absent_refs[ak]}/) — «Неизвестное имя типа» при загрузке")
        for mk in sorted(missing_refs):
            report_warn(f"16. Ссылочный тип '{mk}' — объект есть в составе конфигурации, файла объекта в выгрузке нет ({missing_refs[mk]}/)")
        for uk in sorted(unknown_refs):
            report_warn(f"16. Ссылочный тип '{uk}' не найден в конфигурации ({unknown_refs[uk]}/)")
        if not absent_refs and not missing_refs and not unknown_refs and checked_refs:
            report_ok(f"16. Reference types: {len(checked_refs)} resolved")

# ── Check 22: type name - grammar (level 1) and dictionary by owner context (level 2) ──
# LEVEL 1 depends neither on the platform version nor on the configuration composition: the content of <v8:Type>
# always carries a namespace prefix (xs:/v8:/cfg:/dNpM:/ent:/...). The platform will never accept a bare name -
# that is how a DBMS type ("varchar(150)") and a typo ("Srting(20)") look.
# LEVEL 2 is the dictionary: a stored object has a narrower set of types than a data processor or report, where
# ТаблицаЗначений, ОписаниеТипов, Картинка and other runtime types are available. Here it is only
# a warning: the list is finite but grows with platform versions.
KNOWN_XS_TYPES = {"xs:string", "xs:decimal", "xs:boolean", "xs:dateTime", "xs:base64Binary"}
KNOWN_V8_TYPES = {
    "ValueStorage", "UUID", "Null", "Type", "ValueTable", "ValueTree", "ValueList",
    "ValueListType", "StandardPeriod", "StandardBeginningDate", "PointInTime", "TypeDescription",
    "FixedArray", "FixedMap", "FixedStructure", "FillChecking", "Universal",
}
# Reference metatypes: with an object name (<Метатип>.<Имя>) - a concrete type, without a name - a set.
REF_META_TYPES = {
    "CatalogRef", "DocumentRef", "EnumRef", "ChartOfAccountsRef",
    "ChartOfCharacteristicTypesRef", "ChartOfCalculationTypesRef", "ExchangePlanRef",
    "BusinessProcessRef", "BusinessProcessRoutePointRef", "TaskRef", "AnyRef", "AnyIBRef",
}
# Other current-config namespace names without a dot are platform ones, the configuration composition does not change them.
CFG_BARE_NAMES = {"ConstantsSet", "ReportBuilder", "FilterCriterion", "DynamicList"}
# Kinds whose attributes are STORED in the database: runtime types are not allowed there. For a data processor and report it is the opposite.
STORED_OWNER_TYPES = {
    "Catalog", "Document", "DocumentJournal", "InformationRegister", "AccumulationRegister",
    "AccountingRegister", "CalculationRegister", "ChartOfAccounts", "ChartOfCharacteristicTypes",
    "ChartOfCalculationTypes", "ExchangePlan", "BusinessProcess", "Task", "Constant", "Table",
}
ATTR_TYPE_HOLDERS = {
    "Attribute", "Dimension", "Resource", "Column", "Field", "AddressingAttribute",
    "AccountingFlag", "ExtDimensionAccountingFlag",
}


def _is_storable_type(t):
    if t in KNOWN_XS_TYPES:
        return True
    if t in ("v8:ValueStorage", "v8:UUID", "v8:Null"):
        return True
    m = re.match(r"^(?:cfg|d\d+p\d+):(.+)$", t)
    if not m:
        return False
    name = m.group(1)
    base = name.split(".", 1)[0]
    if base in REF_META_TYPES:
        return True
    return base in ("DefinedType", "Characteristic", "ExternalDataSourceTableRef")


type_nodes_22 = root.findall(".//v8:Type", NS) + root.findall(".//v8:TypeSet", NS)
bad_grammar = {}
unknown_vocab = {}
not_storable = {}
types_seen = 0
for tn in type_nodes_22:
    t = (tn.text or "").strip()
    if not t:
        continue
    types_seen += 1
    if ":" not in t:
        bad_grammar[t] = True
        continue
    prefix, local = t.split(":", 1)
    if prefix == "xs":
        if t not in KNOWN_XS_TYPES:
            unknown_vocab[t] = True
    elif prefix == "v8":
        if local not in KNOWN_V8_TYPES:
            unknown_vocab[t] = True
    elif prefix == "cfg" or re.match(r"^d\d+p\d+$", prefix):
        # The configuration object name is checked by Check 16; here - only the form and the platform part.
        if "." not in local:
            if (local not in REF_META_TYPES and local not in CFG_BARE_NAMES
                    and not re.match(r"^[A-Za-z][A-Za-z0-9]*(Object|Manager|List|Selection|RecordSet|RecordKey|RecordManager)$", local)):
                unknown_vocab[t] = True
        elif not re.match(r"^[A-Za-z][A-Za-z0-9]*\.[^.]+(\.[^.]+)?$", local):
            bad_grammar[t] = True
    # Other namespaces (ent:, v8ui:, dcs*:, mxl: ...) - we do not impose a name form: they have their own dictionaries.

    if md_type in STORED_OWNER_TYPES:
        owner = tn.getparent()                                  # <Type>
        props = owner.getparent() if owner is not None else None   # <Properties>
        child = props.getparent() if props is not None else None   # <Attribute>/<Field>/…
        if child is not None and etree.QName(child).localname in ATTR_TYPE_HOLDERS and not _is_storable_type(t):
            not_storable[t] = etree.QName(child).localname

for bk in sorted(bad_grammar):
    report_error(f"22. Тип '{bk}' — не имя типа платформы: нет префикса пространства имён либо "
                 "неверна форма ссылочного типа. При загрузке — «Неизвестное имя типа»")
for nk in sorted(not_storable):
    report_warn(f"22. Тип '{nk}' у элемента {not_storable[nk]} объекта {md_type}: такие типы "
                "бывают у реквизитов обработок и отчётов, но не у хранимых в базе")
for uk in sorted(unknown_vocab):
    report_warn(f"22. Тип '{uk}' не в списке известных платформенных типов — проверьте написание "
                "(список пополняется с версиями платформы)")
if not bad_grammar and not not_storable and not unknown_vocab and types_seen:
    report_ok(f"22. Type names: {types_seen} checked")

# ── Check 23: type set where it is not accepted ──
# Three strictness levels, all measured by loading into a database on 8.3.24.1691:
#  ERROR - a set inside a defined type composition: the platform rejects the file entirely
#          ("ОпределяемыйТип.<Имя> - Недопустимый тип"), checked on ОпределяемыйТип,
#          Характеристика, ЛюбаяСсылка and bare references;
#  WARN  - a bare metatype in the value type of a ПВХ: loading succeeds, but Configurator does not
#          offer such a type (in the chooser tree it is a folder without a checkbox), and ЛюбаяСсылка in a dump
#          comes back as ЛюбаяСсылкаИБ;
#  WARN  - a defined type or characteristic as one of a composite: Configurator allows
#          choosing them only as the sole type (a characteristic - even with another characteristic). In the erp+acc corpus 6500 sole ones against 1 composite - and this one
#          lies in the typical ERP (Документ.НачислениеИСписаниеБонусныхБаллов.Баллы), so it is not an error.
dt_sets_seen = 0
dt_sets_bad = False
for tb in root.xpath("//md:Type | //md:ValueType", namespaces=NS):
    sets = tb.xpath("v8:TypeSet", namespaces=NS)
    if not sets:
        continue
    dt_sets_seen += 1
    members = len(tb.xpath("v8:Type", namespaces=NS)) + len(sets)
    owner = tb.getparent().getparent()
    owner_kind = etree.QName(owner.tag).localname if owner is not None else ""
    for st in sets:
        raw = re.sub(r'^(?:cfg|d\d+p\d+):', '', (st.text or "").strip())
        if owner_kind == "DefinedType":
            dt_sets_bad = True
            report_error(f"23. Определяемый тип '{obj_name}': в составе тип-множество '{raw}' — платформа не загрузит такой файл («Недопустимый тип»). Состав определяемого типа — только конкретные типы")
            continue
        if owner_kind == "ChartOfCharacteristicTypes" and not re.match(r'^DefinedType[.]', raw):
            dt_sets_bad = True
            report_warn(f"23. План видов характеристик '{obj_name}': тип значения '{raw}' Конфигуратор не предлагает (в дереве выбора это папка без флажка); ЛюбаяСсылка на выгрузке вернётся как ЛюбаяСсылкаИБ")
        if members > 1 and re.match(r'^(DefinedType|Characteristic)[.]', raw):
            dt_sets_bad = True
            report_warn(f"23. Составной тип содержит '{raw}' — Конфигуратор даёт выбрать определяемый тип и характеристику только единственным; платформа загрузит")
if dt_sets_seen and not dt_sets_bad:
    report_ok(f"23. Type sets: {dt_sets_seen} block(s) checked")

# ── Check 18: properties introduced in new format versions ──
# Registry "tag -> minimum format version". Serves two purposes: (1) catch a property in a file with
# too old a stamp - when assembled on an old platform it will be silently discarded (the platform
# reports success while the property is lost); (2) hint that a construct requires a newer
# format. Extended with one line per property - headroom for 2.21 (8.5) and later.
versioned_props = {
    "TypeReductionMode": "2.18",   # type reduction mode (standard attributes, information register dimensions)
    "LineNumberLength": "2.20",    # tabular section line number length (5..9)
    # 2.21 (8.5): confirmed by synthetic tests - same sources, dumps from 8.3.27 and 8.5.1.
    "Color": "2.21",                            # enum value color
    "AuxiliaryVariantForm": "2.21",             # auxiliary report variant form
    "UseInInterfaceCompatibilityMode": "2.21",  # use of a common form in interface compatibility mode
}

file_rank = version_rank
if file_rank > 0:
    for vp in sorted(versioned_props):
        nodes = find_all(root, f"//md:{vp} | //xr:{vp}")
        if nodes and file_rank < format_rank(versioned_props[vp]):
            report_error(f"18. <{vp}> появился в формате {versioned_props[vp]}, а файл объявлен как {version} — на платформе этой версии свойство будет отброшено при загрузке")

# ── Check 19: LineNumberLength - allowed range 5..9 ──
# Tabular section line number length: 5 (up to 99 999 lines) ... 9 (up to 999 999 999). Bounds are from the 1C documentation.
for lnl in find_all(root, "//md:LineNumberLength"):
    raw = inner_text(lnl).strip()
    if not re.match(r'^\d+$', raw):
        report_error(f"19. LineNumberLength='{raw}' — должно быть целое число 5..9")
    elif int(raw) < 5 or int(raw) > 9:
        report_error(f"19. LineNumberLength={raw} вне допустимого диапазона 5..9")

# ── Check 17: MDObjectRef form - a reference to a metadata OBJECT, not to a reference type ──
# Owners/BasedOn/RegisterRecords/RegisteredDocuments/References contain a path like "Catalog.Валюты".
# "CatalogRef.Валюты" is a common mistake (a reference type instead of an object): the platform responds
# "Неизвестный объект метаданных". A metadata kind ending in Ref does not exist -> ERROR.
# An unknown first segment without Ref - only WARN (the list of kinds may be incomplete).

md_ref_nodes = find_all(root, "//*[@xsi:type='xr:MDObjectRef']")
if md_ref_nodes:
    known_roots = tuple(valid_types) + tuple(structural_only_types)
    bad_ref_form = {}    # value -> True (reference form, guaranteed not to work)
    unknown_root = {}    # value -> root
    for rn in md_ref_nodes:
        rv = inner_text(rn).strip()
        if not rv:
            continue
        rroot = rv.split('.')[0]
        if rroot in known_roots:
            continue
        if rroot.endswith('Ref'):
            bad_ref_form[rv] = True
        else:
            unknown_root[rv] = rroot
    for bk in sorted(bad_ref_form):
        fixed = re.sub(r'^([A-Za-z]+)Ref\.', r'\1.', bk)
        report_error(f"17. MDObjectRef '{bk}' — ссылка на ТИП, а не на объект метаданных; нужно '{fixed}' (иначе «Неизвестный объект метаданных» при загрузке)")
    for uk in sorted(unknown_root):
        report_warn(f"17. MDObjectRef '{uk}' — неизвестный вид метаданных '{unknown_root[uk]}' (опечатка?)")
    if not bad_ref_form and not unknown_root:
        report_ok(f"17. MDObjectRef form: {len(md_ref_nodes)} checked")

# ── Check 20: Default*Form / Auxiliary*Form / ChoiceForm - reference to an existing form ──
# The platform rejects loading: "Неизвестный объект метаданных - Catalog.Товары.Form.НетТакойФормы".
# Two notation forms: "CommonForm.Имя" and "<Вид>.<Объект>.Form.<Форма>", and the object may be foreign
# (a document DefaultChoiceForm points to a document journal form). For its OWN object we check
# form registration in ChildObjects - works even on a single file; for a foreign object and a common form the
# configuration is needed. We skip adopted extension objects (ObjectBelonging=Adopted): their forms
# live in the main configuration, they are absent from the extension dump.
#
# The level is everywhere chosen by composition, not by file presence (see in_config_composition):
# not in ChildObjects - the platform will refuse both full and partial loading (ERROR);
# in the composition but no file in the dump - this is a partial dump fragment, and whether it loads
# depends on the DB configuration state, which the validator cannot see (WARN).

form_owner_dir_map = {
    "Catalog": "Catalogs", "Document": "Documents", "DocumentJournal": "DocumentJournals",
    "Enum": "Enums", "Report": "Reports", "DataProcessor": "DataProcessors",
    "InformationRegister": "InformationRegisters", "AccumulationRegister": "AccumulationRegisters",
    "AccountingRegister": "AccountingRegisters", "CalculationRegister": "CalculationRegisters",
    "ChartOfAccounts": "ChartsOfAccounts", "ChartOfCharacteristicTypes": "ChartsOfCharacteristicTypes",
    "ChartOfCalculationTypes": "ChartsOfCalculationTypes", "BusinessProcess": "BusinessProcesses",
    "Task": "Tasks", "ExchangePlan": "ExchangePlans", "SettingsStorage": "SettingsStorages",
    "FilterCriterion": "FilterCriteria", "ExternalDataSource": "ExternalDataSources",
}

_belonging_node = find(type_node, "md:Properties/md:ObjectBelonging")
is_adopted = _belonging_node is not None and inner_text(_belonging_node).strip() == "Adopted"

GUID_RE_20 = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
TAG_RE_20 = re.compile(r'^(Default|Auxiliary)[A-Za-z]*Form$')


def _form_file_exists_20(base_dir, form_name):
    forms_dir = os.path.join(base_dir, "Forms")
    return (os.path.exists(os.path.join(forms_dir, form_name + ".xml"))
            or os.path.exists(os.path.join(forms_dir, form_name, "Form.xml"))
            or os.path.exists(os.path.join(forms_dir, form_name, "Ext", "Form.xml")))


if not is_adopted:
    is_extension_20 = config_is_extension()

    # forms of its own object: names from ChildObjects (case-insensitive comparison, like in the platform)
    own_forms = {}
    if child_obj_node is not None:
        for child in child_obj_node:
            if isinstance(child.tag, str) and local_name(child) == "Form":
                fn = inner_text(child).strip()
                if fn:
                    own_forms[fn.lower()] = fn
    own_dir = os.path.join(os.path.dirname(resolved_path), obj_name)

    form_refs_checked = 0
    form_ref_bad = False
    for frn in root.iter():
        if not isinstance(frn.tag, str):
            continue
        tag = local_name(frn)
        # ChoiceForm - the attribute "choice form", a reference of the same kind as Default*Form.
        if not TAG_RE_20.match(tag) and tag != "ChoiceForm":
            continue
        ref = inner_text(frn).strip()
        if not ref:
            continue
        # The value is sometimes a GUID (erp: Report.СверкаДанныхОУиБУ, DefaultVariantForm) - it cannot
        # be checked without walking all forms; cf-validate (Check 9) skips these too.
        if GUID_RE_20.match(ref):
            continue
        parts = ref.split(".")
        form_refs_checked += 1

        if len(parts) == 2 and parts[0] == "CommonForm":
            if is_extension_20 or not config_dir:
                continue
            cf_dir = os.path.join(config_dir, "CommonForms", parts[1])
            cf_ok = (os.path.exists(cf_dir + ".xml")
                     or os.path.exists(os.path.join(cf_dir, "Ext", "Form.xml"))
                     or os.path.exists(os.path.join(cf_dir, "Form.xml")))
            if not cf_ok:
                if in_config_composition("CommonForm", parts[1]) is True:
                    report_warn(f"20. {tag} '{ref}' — общая форма есть в составе конфигурации, "
                                f"файла формы в выгрузке нет (CommonForms/{parts[1]})")
                else:
                    report_error(f"20. {tag} '{ref}' — общей формы нет в составе конфигурации "
                                 f"(CommonForms/{parts[1]}) — «Неизвестный объект метаданных» при загрузке")
                    form_ref_bad = True
            continue

        # The form reference of an external data source table is six-part:
        # ExternalDataSource.<Источник>.Table.<Таблица>.Form.<Форма>. We reduce it to four parts
        # (kind = Table, object = table name), then the check is common.
        if (len(parts) == 6 and parts[0] == "ExternalDataSource"
                and parts[2] == "Table" and parts[4] == "Form"):
            parts = ["Table", parts[3], "Form", parts[5]]

        if len(parts) != 4 or parts[2] != "Form":
            report_warn(f"20. {tag} '{ref}' — неожиданный вид ссылки на форму "
                        f"(ожидается 'CommonForm.Имя' или '<Вид>.<Объект>.Form.<Форма>')")
            continue

        ref_kind, ref_obj, ref_form = parts[0], parts[1], parts[3]

        if ref_kind.lower() == md_type.lower() and ref_obj.lower() == obj_name.lower():
            if ref_form.lower() not in own_forms:
                known = ", ".join(sorted(own_forms.values())) if own_forms else "нет форм"
                report_error(f"20. {tag} '{ref}' — форма '{ref_form}' не зарегистрирована в "
                             f"ChildObjects объекта (есть: {known}) — «Неизвестный объект метаданных» при загрузке")
                form_ref_bad = True
            elif os.path.isdir(own_dir) and not _form_file_exists_20(own_dir, ref_form):
                # The form is in the object composition, there is no file. For a tree claiming completeness
                # (Configuration.xml lies nearby) this is an integrity error - a full load will fail
                # on "Файл объекта не существует". For a partial dump fragment it is the norm:
                # such a file is loaded via -listFile merged with the DB configuration.
                if config_dir:
                    report_error(f"20. {tag} '{ref}' — форма зарегистрирована в ChildObjects, но файл "
                                 f"формы отсутствует ({obj_name}/Forms/{ref_form})")
                    form_ref_bad = True
                else:
                    report_warn(f"20. {tag} '{ref}' — форма есть в ChildObjects, файла формы "
                                f"в выгрузке нет ({obj_name}/Forms/{ref_form})")
            continue

        # a foreign object (e.g. a document journal) - the configuration is needed
        if is_extension_20 or not config_dir:
            continue
        ref_dir_20 = form_owner_dir_map.get(ref_kind)
        if not ref_dir_20:
            report_warn(f"20. {tag} '{ref}' — неизвестный вид метаданных '{ref_kind}' (опечатка?)")
            continue
        ref_obj_xml = os.path.join(config_dir, ref_dir_20, ref_obj + ".xml")
        if not os.path.exists(ref_obj_xml):
            obj_in_composition = in_config_composition(ref_kind, ref_obj)
            if obj_in_composition is False:
                report_error(f"20. {tag} '{ref}' — объекта '{ref_kind}.{ref_obj}' нет в составе "
                             f"конфигурации ({ref_dir_20}/) — «Неизвестный объект метаданных» при загрузке")
                form_ref_bad = True
            elif obj_in_composition is True:
                report_warn(f"20. {tag} '{ref}' — объект '{ref_kind}.{ref_obj}' есть в составе "
                            f"конфигурации, файла объекта в выгрузке нет ({ref_dir_20}/)")
            else:
                report_warn(f"20. {tag} '{ref}' — объект '{ref_kind}.{ref_obj}' не найден в конфигурации ({ref_dir_20}/)")
            continue
        if not _form_file_exists_20(os.path.join(config_dir, ref_dir_20, ref_obj), ref_form):
            report_error(f"20. {tag} '{ref}' — форма '{ref_form}' не найдена у объекта "
                         f"'{ref_kind}.{ref_obj}' — «Неизвестный объект метаданных» при загрузке")
            form_ref_bad = True

    if form_refs_checked > 0 and not form_ref_bad:
        report_ok(f"20. Form refs: {form_refs_checked} resolved")

# ── Check 21: external data source table - field references and key presence ──
# Table properties reference its own fields by full path. A typo in a field name gives
# "Неизвестный объект метаданных" on load, and finding it by eye in a six-part path is hard.
if md_type == "Table":
    field_names = set()
    if child_obj_node is not None:
        for f in find_all(child_obj_node, "md:Field/md:Properties/md:Name"):
            field_names.add(inner_text(f))
    eds_refs_checked = 0
    eds_refs_bad = False
    for tag, is_list in (("KeyFields", True), ("InputByString", True), ("DataLockFields", True),
                         ("PresentationField", False), ("ParentField", False), ("DataVersionField", False)):
        if is_list:
            refs = [inner_text(n) for n in find_all(props_node, f"md:{tag}/xr:Field")]
        else:
            n = find(props_node, f"md:{tag}")
            refs = [inner_text(n)] if n is not None and inner_text(n) else []
        for ref in refs:
            eds_refs_checked += 1
            parts = ref.split(".")
            # Expected: ExternalDataSource.<Источник>.Table.<Таблица>.Field.<Поле>
            if len(parts) != 6 or parts[0] != "ExternalDataSource" or parts[2] != "Table" or parts[4] != "Field":
                report_error(f"21. {tag} '{ref}' — ожидается ExternalDataSource.<Источник>.Table.<Таблица>.Field.<Поле>")
                eds_refs_bad = True
                continue
            if parts[3] != obj_name:
                report_error(f"21. {tag} '{ref}' — ссылка на поле ЧУЖОЙ таблицы (эта: {obj_name})")
                eds_refs_bad = True
                continue
            if parts[5] not in field_names:
                known = ", ".join(sorted(field_names)) if field_names else "полей нет"
                report_error(f"21. {tag} '{ref}' — поля '{parts[5]}' нет в таблице (есть: {known})")
                eds_refs_bad = True
    if eds_refs_checked > 0 and not eds_refs_bad:
        report_ok(f"21. Field refs: {eds_refs_checked} resolved")

    # Key: XML loading accepts a table without a key (verified on the platform), while Configurator
    # requires it interactively. Hence a warning, not an error: working configurations without a key exist.
    if not find_all(props_node, "md:KeyFields/xr:Field"):
        report_warn("21. KeyFields пуст — платформа такую таблицу загрузит, но форма записи и набор записей будут недоступны")


# ── Final output ──────────────────────────────────────────────

finalize()

if errors > 0:
    sys.exit(1)
sys.exit(0)
