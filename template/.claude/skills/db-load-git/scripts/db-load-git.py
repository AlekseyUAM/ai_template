#!/usr/bin/env python
# db-load-git v1.31 — Load Git changes into 1C database
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills

import argparse
import atexit
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

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



def _find_project_v8path(args):
    """Walk up from CWD to find .v8-project.json and read its v8path.

    The v8path of a database record is stronger than the root one: in one project databases
    live on different platform versions, and the dump format version is set by the platform
    that performs the dump.
    """
    db = find_project_database(args)
    if db and db.get("v8path"):
        return db["v8path"]
    d = os.getcwd()
    while True:
        pf = os.path.join(d, ".v8-project.json")
        if os.path.isfile(pf):
            try:
                with open(pf, encoding="utf-8-sig") as f:
                    data = json.load(f)
                v = data.get("v8path")
                if v:
                    return v
            except Exception:
                pass
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


# --- Additional platform arguments ---
V8_OWNED_KEYS = [
    "DESIGNER", "ENTERPRISE", "CREATEINFOBASE", "CONFIG",
    "/F", "/S", "/N", "/P", "/Out", "/DisableStartupDialogs",
    "/UseTemplate", "/AddToList", "/Execute", "/C", "/URL", "/UC",
    "/DumpIB", "/RestoreIB", "/DumpCfg", "/LoadCfg",
    "/DumpConfigToFiles", "/LoadConfigFromFiles", "/UpdateDBCfg",
    "/DumpExternalDataProcessorOrReportToFiles", "/LoadExternalDataProcessorOrReportFromFiles",
]
# Platform batch commands. In one command line DESIGNER runs ONLY THE LAST one,
# silently discarding the rest (checked on 8.3.24: /LoadConfigFromFiles together with
# /CheckCanApplyConfigurationExtensions exited with code 0 and an empty log, and the load did
# NOT happen). Such a command in extra arguments replaces the skill's operation, and the skill
# reports success. Extra arguments are options, not modes.
V8_BATCH_KEYS = [
    "/CheckConfig", "/CheckModules", "/CheckCanApplyConfigurationExtensions",
    "/DumpDBCfgList", "/DeleteCfg", "/UpdateCfg", "/CompareCfg", "/MergeCfg",
    "/ManageCfgSupport", "/RollbackCfg", "/ConvertFiles",
]

IBCMD_OWNED_KEYS = [
    "--db-path", "--data", "--out", "--file", "--load", "--restore",
    "--import", "--export", "--apply", "--force", "--create-database",
    "--user", "--password",
]
V8_SECRET_KEYS = ["/P", "/UC", "/WSP", "/AWSP", "/ConfigurationRepositoryP"]
IBCMD_SECRET_KEYS = ["--password", "--token", "--db-pwd"]


# --- Database record in .v8-project.json ---
# The model passes neither the platform path of a specific database nor the repository
# credentials: the script matches the connection parameters against a record in databases[]
# and takes them from there. The same technique as in cf-edit.py (matching by configSrc).
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

def same_path(a, b):
    if not a or not b:
        return False
    try:
        return os.path.abspath(a).rstrip("\\/").lower() == os.path.abspath(b).rstrip("\\/").lower()
    except Exception:
        return False


def find_project_database(args):
    """The database record in the registry matching the given connection. None if not found."""
    pf = _sg_find_v8project(os.getcwd())
    if not pf:
        return None
    try:
        with open(pf, encoding="utf-8-sig") as f:
            proj = json.load(f)
    except Exception:
        return None
    for db in proj.get("databases") or []:
        if args.InfoBasePath and db.get("path") and same_path(db["path"], args.InfoBasePath):
            return db
        if args.InfoBaseServer and args.InfoBaseRef and db.get("server") and db.get("ref"):
            if (db["server"].lower() == args.InfoBaseServer.lower()
                    and db["ref"].lower() == args.InfoBaseRef.lower()):
                return db
    return None


def resolve_repository_settings(args):
    """Returns a dict path/user/password/from_registry. Explicit -Repository* beats the registry."""
    db_rec = find_project_database(args)
    rec = None
    if db_rec:
        if args.Extension:
            # An extension has ITS OWN repository with its own path (checked): selected by the pair
            # /ConfigurationRepositoryF"<путь расширения>" + -Extension "<Имя>".
            for ext in db_rec.get("extensions") or []:
                if (ext.get("name") or "").lower() == args.Extension.lower():
                    rec = ext.get("repository")
                    break
        else:
            rec = db_rec.get("repository")
    path = args.RepositoryPath or ((rec or {}).get("path") or None)
    user = args.RepositoryUser or ((rec or {}).get("user") or None)
    # Empty password = absent: 1C requires omitting the key entirely, not passing an empty value.
    pwd = args.RepositoryPassword or ((rec or {}).get("password") or None)
    return {
        "path": path.strip().strip('"') if path else None,
        "user": user,
        "password": pwd,
        "from_registry": bool(rec and rec.get("path")),
    }


def repository_args(repo):
    """Repository access keys. The form is quotes INSIDE the token, as with /N and /P."""
    a = []
    if not repo or not repo.get("path"):
        return a
    a.append('/ConfigurationRepositoryF"%s"' % repo["path"])
    if repo.get("user"):
        a.append('/ConfigurationRepositoryN"%s"' % repo["user"])
    if repo.get("password"):
        a.append('/ConfigurationRepositoryP"%s"' % repo["password"])
    return a


# Platform messages about the configuration repository name the cause but not the action. We
# append the action ourselves: without it the model hits a refusal and does not know how to fix it.
def write_repository_hints(log_text):
    if not log_text:
        return
    if "текущая конфигурация помещена в хранилище" in log_text:
        print("[hint] полная загрузка в базу, подключённую к хранилищу, невозможна.")
        print("       Используйте -Mode Partial, предварительно захватив объекты: /db-repo lock")
    for m in re.finditer(r"объект метаданных (\S+) не захвачен в хранилище", log_text):
        obj = m.group(1)
        if obj == "Configuration":
            print("[hint] не захвачен корень конфигурации — он нужен, чтобы добавить или удалить объект:")
            print('       /db-repo lock <база> -Objects "Конфигурация"')
        else:
            print('[hint] объект не захвачен в хранилище: /db-repo lock <база> -Objects "%s"' % obj)
    if "Соединение с хранилищем конфигурации не установлено" in log_text:
        print("[hint] соединение с хранилищем не установлено. Две причины:")
        print('       реквизиты неизвестны — добавьте "repository" в запись базы в .v8-project.json (см. /db-list);')
        print("       либо хранилище недоступно — для сетевого проверьте сервер хранилища и порт.")


def arg_key_match(token, key):
    """Token matches a key when it equals it, or starts with it and the next character
    is not a letter — catches glued /N"user" and --password=x, while keeping
    /ClearCache distinct from /C."""
    if len(token) < len(key):
        return False
    if token[: len(key)].lower() != key.lower():
        return False
    if len(token) == len(key):
        return True
    return not token[len(key)].isalpha()


def project_extra_args(name):
    """v8args / ibcmdargs from .v8-project.json — same upward walk as v8path."""
    d = os.getcwd()
    while True:
        pf = os.path.join(d, ".v8-project.json")
        if os.path.isfile(pf):
            try:
                with open(pf, encoding="utf-8-sig") as f:
                    data = json.load(f)
                v = data.get(name)
                if v:
                    return [str(x) for x in v]
            except Exception:
                pass
            return []
        parent = os.path.dirname(d)
        if parent == d:
            return []
        d = parent


def assert_extra_args(extra, engine, hints):
    """The platform accepts only one batch operation, and a duplicate connection or
    output key fails with an opaque 1C error — reject what the skill owns itself."""
    param = "-AdditionalIbcmdArguments" if engine == "ibcmd" else "-AdditionalV8Arguments"
    owned = IBCMD_OWNED_KEYS if engine == "ibcmd" else V8_OWNED_KEYS
    for tok in extra:
        if engine == "ibcmd" and not tok.startswith("-"):
            print(
                f"Error: '{tok}' is a positional token — pass values as --key=value "
                f"({param} cannot extend the ibcmd command)",
            )
            sys.exit(1)
        if engine != "ibcmd":
            for b in V8_BATCH_KEYS:
                if arg_key_match(tok, b):
                    print(
                        f"Error: {b} is a batch command; passed via {param} it would replace "
                        f"the skill's own operation (a command line runs only its last batch command)",
                    )
                    sys.exit(1)
        for k in owned:
            if arg_key_match(tok, k):
                hint = f" (use {hints[k]})" if hints and k in hints else ""
                print(
                    f"Error: {k} is controlled by the skill and cannot be passed via {param}{hint}",
                )
                sys.exit(1)


def format_args_for_display(arglist, engine):
    """Redact values of secret-prone keys in glued, =-joined and separate forms.
    Matching here is a plain prefix (no letter rule): over-masking costs nothing,
    a leaked password does."""
    keys = IBCMD_SECRET_KEYS if engine == "ibcmd" else V8_SECRET_KEYS
    res = []
    mask_next = False
    for tok in arglist:
        if mask_next:
            res.append("***")
            mask_next = False
            continue
        hit = None
        for k in keys:
            if tok[: len(k)].lower() == k.lower():
                hit = k
                break
        if hit is None:
            res.append(tok)
        elif len(tok) == len(hit):
            res.append(tok)
            mask_next = True
        elif tok[len(hit)] == "=":
            res.append(hit + "=***")
        else:
            res.append(hit + "***")
    return res


def extract_extra_args(argv, known_opts):
    """argparse refuses values that start with '-' (every ibcmd key does), so pull the two
    escape-hatch lists out of argv by hand: after the flag, take everything up to the next
    declared skill option. Returns (remaining_argv, v8_extra, ibcmd_extra)."""
    rest, v8, ibcmd = [], [], []
    i = 0
    while i < len(argv):
        low = argv[i].lower()
        if low in ("-additionalv8arguments", "-additionalibcmdarguments"):
            target = v8 if low == "-additionalv8arguments" else ibcmd
            i += 1
            while i < len(argv) and argv[i].lower() not in known_opts:
                target.append(argv[i])
                i += 1
            continue
        rest.append(argv[i])
        i += 1
    return rest, v8, ibcmd


def resolve_extra_args(engine, v8_extra, ibcmd_extra, hints):
    """Pick the argument list for the selected engine and validate it. An explicitly
    passed parameter for the other engine is an error; the same keys coming from
    .v8-project.json simply do not apply — a project may describe both engines.

    Comma-separated elements are split apart: the documented invocation passes them
    as one comma-separated value. A value containing a comma is not supported."""
    v8_extra = [p for tok in v8_extra for p in str(tok).split(",") if p]
    ibcmd_extra = [p for tok in ibcmd_extra for p in str(tok).split(",") if p]
    if engine == "ibcmd" and v8_extra:
        print(
            "Error: -AdditionalV8Arguments applies to 1cv8 only; the selected engine is ibcmd "
            "(use -AdditionalIbcmdArguments)",
        )
        sys.exit(1)
    if engine != "ibcmd" and ibcmd_extra:
        print(
            "Error: -AdditionalIbcmdArguments applies to ibcmd only; the selected engine is 1cv8 "
            "(use -AdditionalV8Arguments)",
        )
        sys.exit(1)
    if engine == "ibcmd":
        extra = project_extra_args("ibcmdargs") + list(ibcmd_extra)
    else:
        extra = project_extra_args("v8args") + list(v8_extra)
    if extra:
        assert_extra_args(extra, engine, hints)
    return extra


def _version_dir(p):
    """Version dir for both Windows (.../1cv8/<ver>/bin/1cv8.exe) and *nix (.../1cv8/<ver>/1cv8)."""
    parent = os.path.dirname(p)
    if os.path.basename(parent).lower() == "bin":
        parent = os.path.dirname(parent)
    return os.path.basename(parent)


def _version_key(p):
    """Numeric sort key from version dir name."""
    return [int(x) for x in re.findall(r"\d+", _version_dir(p))]


def resolve_v8path(v8path, args):
    """Resolve path to a 1C executable (1cv8; ibcmd only when given explicitly)."""
    if not v8path:
        v8path = _find_project_v8path(args)
    if not v8path:
        if os.name == "nt":
            candidates = (
                glob.glob(r"C:\Program Files\1cv8\*\bin\1cv8.exe")
                + glob.glob(r"C:\Program Files (x86)\1cv8\*\bin\1cv8.exe")
            )
        else:
            # *nix layout of 1C platform installation paths.
            candidates = glob.glob("/opt/1cv8/*/1cv8")
        if candidates:
            v8path = max(candidates, key=_version_key)
            print(f"Auto-selected platform {_version_dir(v8path)}: {v8path}")
        else:
            print("Error: 1C executable not found. Specify -V8Path")
            sys.exit(1)
    if os.path.isdir(v8path):
        # PY-only: on *nix the executable is named "1cv8" (no .exe); ibcmd - only by explicit path.
        exe = "1cv8.exe" if os.name == "nt" else "1cv8"
        v8path = os.path.join(v8path, exe)
    if not os.path.isfile(v8path):
        print(f"Error: 1C executable not found at {v8path}")
        sys.exit(1)
    return v8path


IBCMD_NOUSER_HINT = (
    "[ibcmd] No -UserName/-Password given; the infobase may require authentication. "
    "On Windows ibcmd reads credentials from the console (stdin is ignored), so this "
    "call may block instead of failing. If it does not return promptly, abort and "
    "re-run with -UserName and -Password.\n"
)


def decode_platform_bytes(data):
    """ibcmd writes UTF-8 (checked on 8.3.24, 8.3.27, 8.5), a crashing 1cv8 may still emit
    OEM text. Decode strictly as UTF-8 and fall back to cp866 on invalid bytes — the locale
    code page (what text=True uses) mangles both."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp866", errors="replace")


def assert_infobase_exists(path):
    """These skills work on a ready infobase. Saying so up front beats the platform's
    "Неверные или отсутствующие параметры соединения" after a launch."""
    if not path:
        return
    if not os.path.isfile(os.path.join(path, "1Cv8.1CD")):
        print(f"Error: information base not found at {path} (no 1Cv8.1CD)")
        sys.exit(1)


def clean_path(value, param=""):
    """Forgive what is unambiguous in a path the caller passed: surrounding whitespace,
    surrounding quotes that survived shell parsing, a trailing separator. A quote left
    inside afterwards cannot be part of a real path — reject it by name instead of letting
    1C answer with its opaque "Неверные или отсутствующие параметры соединения"."""
    if not value:
        return value
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1].strip()
    if len(v) > 3 and v[-1] in "\\/":
        v = v[:-1]
    if '"' in v:
        print(f"Error: {param or 'path'} contains a quote character: {value}")
        sys.exit(1)
    return v


def quote_if_needed(token):
    """Extra arguments come from the caller unquoted; the 1cv8 command line is joined
    verbatim, so a token with a space needs quotes of its own."""
    if token and (" " in token or "\t" in token) and '"' not in token:
        return f'"{token}"'
    return token


def run_v8(v8path, arguments):
    """Run 1cv8 in batch mode and capture its console output.

    The arguments carry their own quotes inside the value (File="C:\\a b") — that is where
    1C's parser expects them, on Windows and on *nix alike. Windows list2cmdline would
    escape those quotes, so there the command line is handed over ready-made.

    On POSIX the arguments go as a LIST, and the quotes needed for joining on Windows would
    become part of the value: the platform does not find a path with a space («Неопределена
    информационная база»), and a multi-word -comment silently loses. Therefore ONE layer of
    surrounding quotes is stripped here. Glued keys (/N"user", /ConfigurationRepositoryF"путь",
    File="…") are untouched: their quotes are inside the token, not on the edges.
    """
    if os.name == "nt":
        cmd = '"' + v8path + '" ' + " ".join(arguments)
    else:
        def strip_framing_quotes(a):
            # The quotes we wrap values with for joining on Windows become PART OF the
            # value on POSIX. Checked on darwin: a path with a space as a separate
            # token gives «Неопределена информационная база», and the glued
            # /ConfigurationRepositoryF"путь с пробелом" - «завершилось с ошибкой»;
            # without quotes both forms work.
            if len(a) > 1 and a[0] == '"' and a[-1] == '"':
                return a[1:-1]                       # "value" as a separate token
            if a[0:1] == "/" and a[-1:] == '"' and '"' in a[:-1]:
                i = a.index('"')
                return a[:i] + a[i + 1:-1]           # /N"имя" -> /Nимя
            return a                                 # File="…" left untouched: there the quotes
                                                     # are part of the connection string syntax,
                                                     # and with them everything works on POSIX
        cmd = [v8path] + [strip_framing_quotes(a) for a in arguments]
    r = subprocess.run(cmd, input=b"", capture_output=True)
    r.stdout = decode_platform_bytes(r.stdout)
    r.stderr = decode_platform_bytes(r.stderr)
    return r


def print_platform_output(result):
    """Print what the platform wrote to the console as its own labelled block. Silence stays
    silent: in batch mode 1cv8 reports through /Out and prints nothing here."""
    text = ((result.stdout or "") + (result.stderr or "")).rstrip()
    if not text:
        return
    limit = 65536
    if len(text) > limit:
        text = f"[... обрезано, показаны последние {limit} символов ...]\n" + text[-limit:]
    print("--- Вывод платформы ---")
    print(text)
    print("--- End ---")


def find_silent_rejections(log_text):
    """Log lines the platform reports WITHOUT raising the exit code.

    Metadata was discarded or the configuration is not working, yet the operation is considered
    "successful". Returns the matching lines.

    A copy of this function exists in every skill that reads the load /Out log (skills are
    self-contained). Keeping the copies identical is deliberate: diverged copies defeat
    the whole point.
    """
    patterns = [
        "Неверное свойство объекта метаданных",
        "не входит в состав объекта метаданных",
        "Неизвестное имя типа",
        "Неизвестный объект метаданных",
        "Ни один из документов не является регистратором для регистра",
        "Неверное значение перечисления",
        "не может быть приведен к типу",
        # Compatibility mode higher than the platform: objects do not get into the database,
        # the refusal comes at runtime. Truncated to the invariant part - the specific version in the message changes.
        "Для работы с конфигурацией необходима версия платформы не меньше",
    ]
    found = []
    if log_text:
        for line in log_text.splitlines():
            for pat in patterns:
                if pat in line:
                    found.append(line.strip())
                    break
    return found


def run_apply_check(exe, conn_args, extension, extra_args):
    """Extension applicability postcondition: the platform reports success even for an extension
    it will not apply - the refusal surfaces lazily, on the first method call, as an event log
    entry.

    The run MUST be separate. This command cannot be appended to the operation line: in one
    command line DESIGNER runs only the LAST batch command and silently discards the rest -
    checked on 8.3.24, /LoadConfigFromFiles together with
    /CheckCanApplyConfigurationExtensions exited with code 0 and an empty log, and the load did
    not happen.

    Only 1cv8 can do this check; if the skill worked via ibcmd, take the neighboring file.
    """
    exe_dir = os.path.dirname(exe)
    leaf = os.path.basename(exe)
    if leaf.lower().startswith("ibcmd"):
        v8 = os.path.join(exe_dir, "1cv8" + os.path.splitext(leaf)[1])
    else:
        v8 = exe
    if not os.path.isfile(v8):
        return {"skipped": True, "reason": f"1cv8 not found at {v8}", "exit": 0, "lines": []}
    temp_dir = tempfile.mkdtemp(prefix="apply_check_")
    try:
        a = ["DESIGNER"] + list(conn_args) + ["/CheckCanApplyConfigurationExtensions"]
        if extension:
            a += ["-Extension", f'"{extension}"']
        out_file = os.path.join(temp_dir, "check_log.txt")
        a += ["/Out", f'"{out_file}"', "/DisableStartupDialogs"]
        a += list(extra_args)
        r = run_v8(v8, a)
        lines = []
        if os.path.isfile(out_file):
            with open(out_file, encoding="utf-8-sig", errors="replace") as f:
                lines = [x.strip() for x in f.read().splitlines() if x.strip()]
        return {"skipped": False, "reason": "", "exit": r.returncode, "lines": lines}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def apply_check_report(exe, conn_args, extension, extra_args):
    """Check and print. True if the platform will not apply the extension - the caller decides
    whether to raise the exit code (strict mode)."""
    ac = run_apply_check(exe, conn_args, extension, extra_args)
    if ac["skipped"]:
        print(f"[note] applicability check skipped: {ac['reason']}")
        return False
    if ac["exit"] != 0 or ac["lines"]:
        print("[warning] the extension is loaded, but the platform will not apply it:")
        for line in ac["lines"]:
            print(f"  {line}")
        return True
    return False


def apply_check_enabled(disabled):
    """Whether to check applicability: -NoApplyCheck beats the project setting."""
    if disabled:
        return False
    pf = _sg_find_v8project(os.getcwd())
    if pf:
        try:
            with open(pf, encoding="utf-8-sig") as f:
                proj = json.load(f)
            if proj.get("extensionApplyCheck") is not None:
                return bool(proj.get("extensionApplyCheck"))
        except Exception:
            pass
    return True


def run_ibcmd(cmd, has_username=False, warn_no_user=True):
    """Run an ibcmd command non-interactively.

    input="" closes stdin (EOF) so ibcmd's auth prompt fast-fails instead of hanging.
    On Windows without -UserName ibcmd reads the console directly and may still block —
    that residual case is flagged via IBCMD_NOUSER_HINT (model-facing).
    """
    if warn_no_user and os.name == "nt" and not has_username:
        sys.stdout.write(IBCMD_NOUSER_HINT)
        sys.stderr.flush()
    r = subprocess.run(cmd, input=b"", capture_output=True)
    r.stdout = decode_platform_bytes(r.stdout)
    r.stderr = decode_platform_bytes(r.stderr)
    return r


def get_object_xml_from_subfile(relative_path):
    """Map sub-file path (BSL, HTML, etc.) to object XML path."""
    parts = re.split(r"[\\/]", relative_path)
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}.xml"
    return None


# Top-level object dump directories -> element in the configuration's <ChildObjects>.
TYPE_DIR_TAG = {
    "Languages": "Language", "Subsystems": "Subsystem", "StyleItems": "StyleItem", "Styles": "Style",
    "CommonPictures": "CommonPicture", "SessionParameters": "SessionParameter", "Roles": "Role",
    "CommonTemplates": "CommonTemplate", "FilterCriteria": "FilterCriterion", "CommonModules": "CommonModule",
    "Bots": "Bot", "PaletteColors": "PaletteColor", "CommonAttributes": "CommonAttribute",
    "ExchangePlans": "ExchangePlan", "XDTOPackages": "XDTOPackage", "WebServices": "WebService",
    "HTTPServices": "HTTPService", "WSReferences": "WSReference", "EventSubscriptions": "EventSubscription",
    "ScheduledJobs": "ScheduledJob", "SettingsStorages": "SettingsStorage", "FunctionalOptions": "FunctionalOption",
    "FunctionalOptionsParameters": "FunctionalOptionsParameter", "DefinedTypes": "DefinedType",
    "CommonCommands": "CommonCommand", "CommandGroups": "CommandGroup", "Constants": "Constant",
    "CommonForms": "CommonForm", "Catalogs": "Catalog", "Documents": "Document",
    "DocumentNumerators": "DocumentNumerator", "Sequences": "Sequence", "DocumentJournals": "DocumentJournal",
    "Enums": "Enum", "Reports": "Report", "DataProcessors": "DataProcessor",
    "InformationRegisters": "InformationRegister", "AccumulationRegisters": "AccumulationRegister",
    "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes", "ChartsOfAccounts": "ChartOfAccounts",
    "AccountingRegisters": "AccountingRegister", "ChartsOfCalculationTypes": "ChartOfCalculationTypes",
    "CalculationRegisters": "CalculationRegister", "BusinessProcesses": "BusinessProcess", "Tasks": "Task",
    "ExternalDataSources": "ExternalDataSource", "IntegrationServices": "IntegrationService",
}
_TYPE_DIR_TAG_CI = {k.lower(): v for k, v in TYPE_DIR_TAG.items()}


def get_deletion_verdicts(deleted, loaded, root, fmt):
    """What a partial load will do with paths deleted in git. A deleted OBJECT (its XML description)
    disappears from the database only if its owner is in the list and the object is no longer
    in the owner's composition (ChildObjects). A deleted PART of an object (module, Ext/ files)
    is never deleted by a partial load - the platform silently skips a missing file, even if
    listed explicitly. Paths outside object directories (README, docs/…) are not configuration,
    their deletion is not evaluated. Returns a verdict for each deletion: {path, applied, reason}."""
    ours = [d for d in deleted if len(d.split("/")) >= 2 and d.split("/")[0].lower() in _TYPE_DIR_TAG_CI]
    if fmt == "Plain":
        return [{"path": d, "applied": False,
                 "reason": "формат Plain — удаление загрузкой частями не применяется"} for d in ours]
    deleted_set = {d.lower() for d in deleted}
    loaded_set = {x.lower() for x in loaded}
    result = []
    for d in ours:
        segs = d.split("/")
        ext_idx = segs.index("Ext") if "Ext" in segs else -1
        if ext_idx < 0 and d.lower().endswith(".xml") and (len(segs) == 2 or len(segs) >= 4):
            # Object description: the owner is Configuration.xml or the object description two levels up.
            # Composition element - by directory: Catalogs -> Catalog, Forms -> Form.
            if len(segs) == 2:
                owner = "Configuration.xml"
                tag = _TYPE_DIR_TAG_CI[segs[0].lower()]
            else:
                owner = "/".join(segs[:-2]) + ".xml"
                tag = re.sub(r"s$", "", segs[-2])
            if owner.lower() in deleted_set:
                continue
            name = os.path.splitext(segs[-1])[0]
            if owner.lower() not in loaded_set:
                result.append({"path": d, "applied": False,
                               "reason": f"владелец {owner} не изменён — состав в базе прежний"})
                continue
            with open(os.path.join(root, owner), encoding="utf-8-sig") as f:
                owner_text = f.read()
            m = re.search(r"<ChildObjects>.*</ChildObjects>", owner_text, re.S)
            pattern = r"(?m)^\s*<" + tag + ">" + re.escape(name) + "</" + tag + r">\s*$"
            if m and re.search(pattern, m.group(0)):
                result.append({"path": d, "applied": False,
                               "reason": f"{owner} всё ещё содержит объект в составе"})
            else:
                result.append({"path": d, "applied": True, "reason": f"через {owner}"})
            continue
        if ext_idx < 0:
            continue
        # Part of an object: the object itself is the segments before Ext. Deleted together with the object - the object's fate.
        if ("/".join(segs[:ext_idx]) + ".xml").lower() in deleted_set:
            continue
        result.append({"path": d, "applied": False,
                       "reason": "часть объекта — загрузка частями файлы не удаляет "
                                 "(пустой файл вместо удаления очистит модуль)"})
    return result


def run_git(config_dir, git_args):
    """Run a git command in config_dir and return output lines on success.
    diff is called with --no-renames: on a rename otherwise only the new path is visible, while the old one
    is a deletion that must be warned about."""
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false"] + git_args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=config_dir,
    )
    if result.returncode == 0:
        return [line for line in result.stdout.splitlines() if line.strip()]
    return []


def describe_exit(code):
    """Annotate an abnormal process exit code so a crash isn't reported as a bare number.
    Batch 1C in a broken/headless environment (no GUI session, no license) can crash mid-run
    instead of returning a clean error, possibly leaving the infobase locked or half-mutated."""
    if code is None:
        return ""
    win = {
        3221225477: "0xC0000005 (access violation)", -1073741819: "0xC0000005 (access violation)",
        3221225781: "0xC0000135 (missing DLL)", -1073741515: "0xC0000135 (missing DLL)",
        3221226505: "0xC0000409 (stack overrun)", -1073740791: "0xC0000409 (stack overrun)",
    }
    if code in win:
        return f" — abnormal termination, exception {win[code]}; the infobase may be left in an inconsistent state; verify it before retrying"
    if -64 <= code < 0:
        try:
            import signal
            name = signal.Signals(-code).name
        except (ValueError, AttributeError):
            name = f"signal {-code}"
        return (f" — process terminated by {name} (abnormal termination, not a normal exit); "
                "the infobase may be left in an inconsistent state; verify it before retrying")
    return ""


def _redact(text, *secrets):
    """Redact literal secret values (password, user) from a display string —
    precise, never touches lookalike paths."""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Load Git changes into 1C database",
        allow_abbrev=False,
    )
    parser.add_argument("-V8Path", default="", help="Path to 1cv8.exe or its bin directory")
    parser.add_argument("-InfoBasePath", default="", help="Path to file infobase")
    parser.add_argument("-InfoBaseServer", default="", help="1C server (for server infobase)")
    parser.add_argument("-InfoBaseRef", default="", help="Infobase name on server")
    parser.add_argument("-UserName", default="", help="1C user name")
    parser.add_argument("-Password", default="", help="1C user password")
    parser.add_argument("-RepositoryPath", default="")
    parser.add_argument("-RepositoryUser", default="")
    parser.add_argument("-RepositoryPassword", default="")
    parser.add_argument("-ConfigDir", required=True, help="Directory with XML configuration (git repo)")
    parser.add_argument(
        "-Source",
        default="All",
        choices=["All", "Staged", "Unstaged", "Commit"],
        help="Change source (default: All)",
    )
    parser.add_argument("-CommitRange", default="", help="Commit range (for Source=Commit), e.g. HEAD~3..HEAD")
    parser.add_argument("-Extension", default="", help="Extension name to load")
    parser.add_argument("-AllExtensions", action="store_true", help="Not supported: partial load goes one extension at a time")
    parser.add_argument(
        "-Format",
        default="Hierarchical",
        choices=["Hierarchical", "Plain"],
        help="File format (default: Hierarchical)",
    )
    parser.add_argument("-DryRun", action="store_true", help="Only show what would be loaded (no actual load)")
    parser.add_argument("-UpdateDB", action="store_true", help="Also update database configuration after load")
    # A key for regressions and snapshot verification, not for everyday use: deliberately not
    # exposed in SKILL.md. Raises the exit code if the platform reported success,
    # but the log contains rejections.
    parser.add_argument("-StrictLog", action="store_true")
    # Skip the extension applicability check after loading.
    parser.add_argument("-NoApplyCheck", action="store_true")
    parser.add_argument("-AdditionalV8Arguments", nargs="*", default=[],
                        help="Extra 1cv8 arguments, e.g. /UseHwLicenses+")
    parser.add_argument("-AdditionalIbcmdArguments", nargs="*", default=[],
                        help="Extra ibcmd arguments in --key=value form")
    known_opts = {s.lower() for a in parser._actions for s in a.option_strings}
    argv, v8_extra, ibcmd_extra = extract_extra_args(sys.argv[1:], known_opts)
    args = ci_parse_args(parser, argv)

    args.V8Path = clean_path(args.V8Path, "-V8Path")
    args.InfoBasePath = clean_path(args.InfoBasePath, "-InfoBasePath")
    assert_infobase_exists(args.InfoBasePath)
    args.ConfigDir = clean_path(args.ConfigDir, "-ConfigDir")

    # --- Resolve V8Path (skip if DryRun) ---
    v8path = None
    if not args.DryRun:
        v8path = resolve_v8path(args.V8Path, args)

    # --- Detect engine + validate connection (skip if DryRun) ---
    engine = "1cv8"
    if not args.DryRun:
        engine = "ibcmd" if os.path.basename(v8path).lower().startswith("ibcmd") else "1cv8"
        if engine == "ibcmd":
            if not args.InfoBasePath:
                print("Error: ibcmd supports file infobases only (use -InfoBasePath)")
                sys.exit(1)
        elif not args.InfoBasePath and (not args.InfoBaseServer or not args.InfoBaseRef):
            print("Error: specify -InfoBasePath or -InfoBaseServer + -InfoBaseRef")
            sys.exit(1)

    # --- Resolve additional arguments for the selected engine ---
    arg_hints = {
        "/F": "-InfoBasePath",
        "/S": "-InfoBaseServer + -InfoBaseRef",
        "/N": "-UserName",
        "/P": "-Password",
        "--db-path": "-InfoBasePath",
        "--user": "-UserName",
        "--password": "-Password",
    }
    extra_args = resolve_extra_args(engine, v8_extra, ibcmd_extra, arg_hints)

    # --- Validate config dir ---
    if not os.path.exists(args.ConfigDir):
        print(f"Error: config directory not found: {args.ConfigDir}")
        sys.exit(1)

    # --- Validate Commit mode ---
    if args.Source == "Commit" and not args.CommitRange:
        print("Error: -CommitRange required for Source=Commit")
        sys.exit(1)

    # --- -AllExtensions: a partial load goes one extension at a time ---
    # Configurator rejects -AllExtensions combined with -listFile itself, ibcmd does not support it.
    if args.AllExtensions:
        print("Error: -AllExtensions cannot be combined with a partial load")
        print("  Загружайте расширения по одному: -Extension <имя>, -ConfigDir — каталог этого расширения.")
        sys.exit(1)

    # --- Check git ---
    try:
        subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: git not found in PATH")
        sys.exit(1)

    # --- Get changed files from Git ---
    changed_files = []

    if args.Source == "Staged":
        print("Getting staged changes...")
        changed_files += run_git(args.ConfigDir, ["diff", "--cached", "--name-only", "--no-renames", "--relative"])
    elif args.Source == "Unstaged":
        print("Getting unstaged changes...")
        changed_files += run_git(args.ConfigDir, ["diff", "--name-only", "--no-renames", "--relative"])
        changed_files += run_git(args.ConfigDir, ["ls-files", "--others", "--exclude-standard"])
    elif args.Source == "Commit":
        print(f"Getting changes from {args.CommitRange}...")
        changed_files += run_git(args.ConfigDir, ["diff", "--name-only", "--no-renames", "--relative", args.CommitRange])
    elif args.Source == "All":
        print("Getting all uncommitted changes...")
        changed_files += run_git(args.ConfigDir, ["diff", "--cached", "--name-only", "--no-renames", "--relative"])
        changed_files += run_git(args.ConfigDir, ["diff", "--name-only", "--no-renames", "--relative"])
        changed_files += run_git(args.ConfigDir, ["ls-files", "--others", "--exclude-standard"])

    # Deduplicate and filter blanks
    changed_files = list(dict.fromkeys(f for f in changed_files if f.strip()))

    if len(changed_files) == 0:
        print("No changes found")
        sys.exit(0)

    print(f"Git changes detected: {len(changed_files)} files")

    # --- Filter and map to config files ---
    config_files = []
    support_skipped = []
    deleted_files = []

    for file in changed_files:
        file = file.strip().replace("\\", "/")
        if not file:
            continue

        # Skip service files (not partially loadable). Support-state files are
        # tracked to warn: support changes apply only via a full load.
        if file.endswith("ParentConfigurations.bin"):
            support_skipped.append(file)
            continue
        if file == "ConfigDumpInfo.xml" or file.endswith("/ConfigDumpInfo.xml"):
            continue

        full_path = os.path.join(args.ConfigDir, file)
        if not os.path.exists(full_path):
            deleted_files.append(file)

        if file.endswith(".xml"):
            # XML file — add directly if exists
            if os.path.exists(full_path):
                if file not in config_files:
                    config_files.append(file)
        else:
            # Non-XML (BSL, HTML, etc.) — map to parent object XML + include all Ext/ files
            object_xml = get_object_xml_from_subfile(file)
            if object_xml:
                full_xml_path = os.path.join(args.ConfigDir, object_xml)
                if os.path.exists(full_xml_path):
                    if object_xml not in config_files:
                        config_files.append(object_xml)
                    if os.path.exists(full_path) and file not in config_files:
                        config_files.append(file)

                    # Add all files from Ext/ directory of the object
                    parts = re.split(r"[\\/]", file)
                    if len(parts) >= 2:
                        ext_dir = os.path.join(args.ConfigDir, parts[0], parts[1], "Ext")
                        if os.path.isdir(ext_dir):
                            for root, dirs, files in os.walk(ext_dir):
                                for fname in files:
                                    abs_path = os.path.join(root, fname)
                                    rel_path = os.path.relpath(abs_path, args.ConfigDir).replace("\\", "/")
                                    if rel_path not in config_files:
                                        config_files.append(rel_path)

    if support_skipped:
        print("[ВНИМАНИЕ] Состояние поддержки изменено в коммите, но частично не загружается (исключено):")
        for sf in support_skipped:
            print(f"  - {sf}")
        print("  Смена состояния поддержки применяется только полной загрузкой (db-load-xml -Mode Full).")

    verdicts = get_deletion_verdicts(deleted_files, config_files, args.ConfigDir, args.Format)
    unapplied = [v for v in verdicts if not v["applied"]]
    for v in verdicts:
        if v["applied"]:
            print(f"[note] удаление применится {v['reason']}: {v['path']}")
    if unapplied:
        print("[ВНИМАНИЕ] Удаления, которые загрузка частями НЕ применит — в базе они останутся:")
        for u in unapplied:
            print(f"  - {u['path']}: {u['reason']}")
        print("  Применить их можно полной загрузкой (db-load-xml -Mode Full).")

    if len(config_files) == 0:
        if unapplied:
            print("Error: changes found, but none of them can be applied by a partial load (see above)")
            sys.exit(1)
        print("No configuration files found in changes")
        sys.exit(0)

    # The root Configuration.xml is the «Конфигурация» object: along with the object the platform loads
    # its child objects, and for the configuration that is the whole composition. It gets into the
    # list from the diff by itself, so we warn - the user did not choose it.
    if any(x.replace("\\", "/").lower() == "configuration.xml" for x in config_files):
        print("[ВНИМАНИЕ] В изменениях есть Configuration.xml: платформа выполнит ПОЛНУЮ загрузку")
        print("  конфигурации, а не только изменённых объектов.")

    print(f"Files for loading: {len(config_files)}")
    for f in config_files:
        print(f"  {f}")

    # --- DryRun: stop here ---
    if args.DryRun:
        print("")
        print("DryRun mode - no changes applied")
        sys.exit(0)

    # --- Temp dir ---
    temp_dir = os.path.join(tempfile.gettempdir(), f"db_load_git_{random.randint(0, 999999)}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        if engine == "ibcmd":
            # --- ibcmd branch (file infobase only; import specific files) ---
            if args.Format == "Plain":
                print("Error: ibcmd config import supports hierarchical format only (use -Format Hierarchical or 1cv8)")
                sys.exit(1)
            arguments = ["infobase", "config", "import", "files"] + config_files
            arguments += [f"--base-dir={args.ConfigDir}", f"--db-path={args.InfoBasePath}"]
            if args.Extension:
                arguments.append(f"--extension={args.Extension}")
            ib_data = tempfile.mkdtemp(prefix="ibcmd_data_")
            atexit.register(shutil.rmtree, ib_data, ignore_errors=True)
            if args.UserName:
                arguments.append(f"--user={args.UserName}")
            if args.Password:
                arguments.append(f"--password={args.Password}")
            arguments.append(f"--data={ib_data}")
            arguments.extend(extra_args)
            print(f"Running: ibcmd {_redact(' '.join(format_args_for_display(arguments, engine)), args.Password, args.UserName)}")
            result = run_ibcmd([v8path] + arguments, bool(args.UserName))
            if result.returncode != 0:
                print(f"Error loading changes (code: {result.returncode}){describe_exit(result.returncode)}")
                sys.exit(result.returncode)
            print(f"Changes loaded successfully ({len(config_files)} files)")
            exit_code = 0
            if args.UpdateDB:
                apply_args = ["infobase", "config", "apply", f"--db-path={args.InfoBasePath}", "--force"]
                if args.UserName:
                    apply_args.append(f"--user={args.UserName}")
                if args.Password:
                    apply_args.append(f"--password={args.Password}")
                apply_args.append(f"--data={ib_data}")
                apply_args.extend(extra_args)
                print(f"Running: ibcmd {_redact(' '.join(format_args_for_display(apply_args, engine)), args.Password, args.UserName)}")
                ar = run_ibcmd([v8path] + apply_args, bool(args.UserName))
                exit_code = ar.returncode
                if exit_code == 0:
                    print("Database configuration updated successfully")
                else:
                    print(f"Error updating database configuration (code: {exit_code}){describe_exit(exit_code)}")
                print_platform_output(ar)
            # Only 1cv8 can do the applicability check - we build the connection for it in its form.
            if (exit_code == 0 and args.Extension
                    and apply_check_enabled(args.NoApplyCheck)):
                ac_conn = ["/F", f'"{args.InfoBasePath}"']
                if args.UserName:
                    ac_conn.append(f'/N"{args.UserName}"')
                if args.Password:
                    ac_conn.append(f'/P"{args.Password}"')
                if apply_check_report(v8path, ac_conn, args.Extension, []) and args.StrictLog:
                    exit_code = 1

            sys.exit(exit_code)

        # --- Write list file (UTF-8 with BOM) ---
        list_file = os.path.join(temp_dir, "load_list.txt")
        with open(list_file, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(config_files))

        # --- Build arguments ---
        # Connection arguments are built separately: the applicability check will use the same set.
        conn_args = []

        if args.InfoBaseServer and args.InfoBaseRef:
            conn_args += ["/S", f'"{args.InfoBaseServer}/{args.InfoBaseRef}"']
        else:
            conn_args += ["/F", f'"{args.InfoBasePath}"']

        if args.UserName:
            conn_args.append(f'/N"{args.UserName}"')
        if args.Password:
            conn_args.append(f'/P"{args.Password}"')

        # A database under a repository will not accept ANY Configurator operation without these
        # credentials, while for a database outside a repository they are harmless - so we always
        # substitute them when known.
        repo = resolve_repository_settings(args)
        conn_args.extend(repository_args(repo))

        arguments = ["DESIGNER"] + conn_args

        arguments += ["/LoadConfigFromFiles", f'"{args.ConfigDir}"']
        arguments += ["-listFile", f'"{list_file}"']
        arguments += ["-Format", args.Format]
        arguments.append("-partial")
        arguments.append("-updateConfigDumpInfo")

        # --- Extensions ---
        if args.Extension:
            arguments += ["-Extension", f'"{args.Extension}"']

        # --- UpdateDB ---
        if args.UpdateDB:
            arguments.append("/UpdateDBCfg")

        # --- Output ---
        out_file = os.path.join(temp_dir, "load_log.txt")
        arguments += ["/Out", f'"{out_file}"']
        arguments.append("/DisableStartupDialogs")
        arguments.extend(quote_if_needed(a) for a in extra_args)

        # --- Execute ---
        print("")
        print("Executing partial configuration load...")
        print(f"Running: 1cv8.exe {_redact(' '.join(format_args_for_display(arguments, engine)), args.Password, args.UserName, repo['password'])}")

        result = run_v8(v8path, arguments)
        exit_code = result.returncode

        # --- Result ---
        print("")
        if exit_code == 0:
            print("Load completed successfully")
        else:
            print(f"Error loading configuration (code: {exit_code}){describe_exit(exit_code)}")

        log_content = ""
        if os.path.isfile(out_file):
            try:
                with open(out_file, "r", encoding="utf-8-sig") as f:
                    log_content = f.read()
                if log_content:
                    print("--- Log ---")
                    print(log_content)
                    print("--- End ---")
            except Exception:
                pass

        print_platform_output(result)
        write_repository_hints(log_content)

        # We do not name the cause: the log lines are printed next and speak for themselves, and
        # the class of problem differs - from a discarded property to a configuration that does
        # not work on this platform. We do not hint at -StrictLog: the operation has already run,
        # no point repeating it for the same text.
        silent_failures = find_silent_rejections(log_content)
        # Only on success: on failure the log is already printed in full, and the block would
        # repeat its lines under the "reported success" heading - a lie next to "Error … (code: N)".
        if exit_code == 0 and silent_failures:
            print(
                f"[warning] platform reported success, but the log contains "
                f"{len(silent_failures)} problem(s):"
            )
            for line in silent_failures:
                print(f"  {line}")
            if args.StrictLog:
                exit_code = 1

        # The extension could load "successfully" and remain inapplicable - we ask the platform.
        if (exit_code == 0 and args.Extension
                and apply_check_enabled(args.NoApplyCheck)):
            if apply_check_report(v8path, conn_args, args.Extension, extra_args) and args.StrictLog:
                exit_code = 1

        sys.exit(exit_code)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
