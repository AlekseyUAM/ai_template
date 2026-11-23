#!/usr/bin/env python3
"""Проверка объявлений стандартных обработчиков событий 1С.

Скрипт определяет вид модуля и объект метаданных по пути в выгрузке
(`src/cf/Documents/Заказ/Ext/ObjectModule.bsl` → `Document.Заказ`,
`Document.ObjectModule`) и сверяет обработчики с контрактами платформы из
снимка `event_handlers.json` (генерируется tools/update_event_handlers.py).

Проверки:
  event-handler-exported    warning  стандартный обработчик объявлен Экспорт
  event-handler-params      error    число параметров не совпадает с контрактом
  event-handler-param-name  info     параметр назван не как в контракте
  event-handler-wrong-module warning имя — событие другого вида модуля

В каждом сообщении печатается правильная сигнатура вида
`Процедура ОбработкаПроведения(Отказ, РежимПроведения)`, чтобы обработчик
можно было исправить без догадок.

    python check_event_handlers.py src/cf/Documents/Заказ/Ext/ObjectModule.bsl
    python check_event_handlers.py src/cf
    python check_event_handlers.py --module-type Document.ObjectModule -
    python check_event_handlers.py --list-module-types
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bsl_model  # noqa: E402

DATA_PATH = Path(__file__).with_name("event_handlers.json")

TYPE_DIRS = {
    "Catalogs": "Catalog", "Documents": "Document",
    "DocumentJournals": "DocumentJournal", "Enums": "Enum",
    "Constants": "Constant", "InformationRegisters": "InformationRegister",
    "AccumulationRegisters": "AccumulationRegister",
    "AccountingRegisters": "AccountingRegister",
    "CalculationRegisters": "CalculationRegister",
    "BusinessProcesses": "BusinessProcess", "Tasks": "Task",
    "ChartsOfAccounts": "ChartOfAccounts",
    "ChartsOfCalculationTypes": "ChartOfCalculationTypes",
    "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes",
    "ExchangePlans": "ExchangePlan", "Sequences": "Sequence",
    "Recalculations": "Recalculation", "FilterCriteria": "FilterCriterion",
    "SettingsStorages": "SettingsStorage",
    "DataProcessors": "DataProcessor", "Reports": "Report",
    "CommonModules": "CommonModule", "CommonCommands": "CommonCommand",
    "CommonForms": "CommonForm", "HTTPServices": "HTTPService",
    "WebServices": "WebService", "WebSocketClients": "WebSocketClient",
    "Bots": "Bot", "IntegrationServices": "IntegrationService",
    "ExternalDataSources": "ExternalDataSource",
}

MODULE_FILES = {
    "ObjectModule.bsl": "ObjectModule",
    "ManagerModule.bsl": "ManagerModule",
    "RecordSetModule.bsl": "RecordSetModule",
    "ValueManagerModule.bsl": "ValueManagerModule",
    "Module.bsl": "Module",
    "CommandModule.bsl": "CommandModule",
}

APP_MODULES = {
    "ManagedApplicationModule.bsl": "Configuration.ManagedApplicationModule",
    "OrdinaryApplicationModule.bsl": "Configuration.OrdinaryApplicationModule",
    "ExternalConnectionModule.bsl": "Configuration.ExternalConnectionModule",
    "SessionModule.bsl": "Configuration.SessionModule",
}

KEYWORD_RU = {"procedure": "Процедура", "function": "Функция"}
KEYWORD_EN = {"procedure": "Procedure", "function": "Function"}


@dataclass
class Finding:
    code: str
    severity: str
    line: int
    message: str


def load_data() -> dict:
    try:
        with DATA_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"Не удалось прочитать {DATA_PATH}: {exc}", file=sys.stderr)
        raise SystemExit(2)


def infer_module_key(path: str):
    """Return (module_key, object_name, skip_reason)."""
    parts = path.replace("\\", "/").split("/")
    if not parts:
        return None, None, "пустой путь"
    base = parts[-1]
    lower = [p.lower() for p in parts]

    if "forms" in lower or "commonforms" in lower:
        return None, None, "модуль формы (в v1 не проверяется)"
    if base in APP_MODULES:
        return APP_MODULES[base], None, ""
    for i, part in enumerate(lower):
        if part in ("epf", "erf") and base == "ObjectModule.bsl":
            name = parts[i + 1] if i + 1 < len(parts) else None
            meta = "ExternalDataProcessor" if part == "epf" else "ExternalReport"
            return f"{meta}.ObjectModule", name, ""

    found = None
    for i, part in enumerate(parts):
        if part in TYPE_DIRS:
            found = i
    if found is None:
        return None, None, "вид модуля не определяется по пути"
    meta = TYPE_DIRS[parts[found]]
    obj = parts[found + 1] if found + 1 < len(parts) else None

    if "Commands" in parts[found + 2:]:
        if base == "CommandModule.bsl":
            return "Command.CommandModule", obj, ""
        return None, obj, "модуль команды: не CommandModule.bsl"
    if meta == "CommonModule":
        if base == "Module.bsl":
            return "CommonModule.Module", obj, ""
        return None, obj, "общий модуль: не Module.bsl"
    if meta == "CommonForm":
        return None, obj, "модуль формы (в v1 не проверяется)"
    if "Ext" in parts[found + 2:]:
        kind = MODULE_FILES.get(base)
        if kind:
            return f"{meta}.{kind}", obj, ""
    return None, obj, "модуль вне Ext/<...Module>.bsl"


class EventIndex:
    """Event lookup for one module and the global wrong-module index."""

    def __init__(self, data: dict):
        self.modules = data.get("modules") or {}
        self.global_index: dict[str, set[str]] = {}
        for key, mod in self.modules.items():
            if mod.get("handler_name_arbitrary"):
                continue
            for ru, event in (mod.get("events") or {}).items():
                names = {ru.casefold()}
                en = event.get("name_en")
                if en:
                    names.add(en.casefold())
                for name in names:
                    self.global_index.setdefault(name, set()).add(key)

    def label(self, key: str) -> str:
        mod = self.modules.get(key)
        return (mod or {}).get("title_ru") or key

    def find_event(self, key: str, method_name: str):
        mod = self.modules.get(key)
        if not mod or not method_name:
            return None
        folded = method_name.casefold()
        for ru, event in (mod.get("events") or {}).items():
            if ru.casefold() == folded:
                return ru, event
            en = event.get("name_en")
            if en and en.casefold() == folded:
                return ru, event
        return None

    @staticmethod
    def _param_names(signature: dict, index: int) -> list[str]:
        names = []
        ru = signature.get("params_ru") or []
        en = signature.get("params_en") or []
        if index < len(ru):
            names.append(ru[index])
        if index < len(en):
            names.append(en[index])
        return names

    @classmethod
    def _matches(cls, got: str, signature: dict, index: int) -> bool:
        return any(got.casefold() == name.casefold()
                   for name in cls._param_names(signature, index))

    @staticmethod
    def _total(signature: dict) -> int:
        return len(signature.get("params_ru") or signature.get("params_en") or [])

    @classmethod
    def _fits(cls, signature: dict, declared: int) -> bool:
        """Handler may omit only optional trailing parameters."""
        total = cls._total(signature)
        if declared > total:
            return False
        optional = signature.get("optional") or [False] * total
        if len(optional) < total:
            optional = list(optional) + [False] * (total - len(optional))
        return all(optional[i] for i in range(declared, total))

    @staticmethod
    def _sig_line(ru_name: str, event: dict, signature: dict) -> str:
        kind = event.get("kind") or "procedure"
        ru_params = signature.get("params_ru") or signature.get("params_en") or []
        ru_line = (f"{KEYWORD_RU.get(kind, 'Процедура')} {ru_name}"
                   f"({', '.join(ru_params)})")
        en_name = event.get("name_en")
        en_params = signature.get("params_en")
        if en_name and en_params:
            en_line = (f"{KEYWORD_EN.get(kind, 'Procedure')} {en_name}"
                       f"({', '.join(en_params)})")
            if en_line != ru_line:
                return f"{ru_line} / {en_line}"
        return ru_line

    @classmethod
    def signatures_text(cls, ru_name: str, event: dict) -> str:
        lines = [cls._sig_line(ru_name, event, sig)
                 for sig in (event.get("signatures") or [])]
        if not lines:
            return "контракт события пуст"
        if len(lines) == 1:
            return f"правильная сигнатура: {lines[0]}"
        return "правильные сигнатуры: " + "; ".join(lines)

    def check_method(self, key: str, method) -> list[Finding]:
        if key not in self.modules:
            return []
        found = self.find_event(key, method.name)
        if found:
            return self._check_event(key, method, *found)

        mod = self.modules.get(key) or {}
        if (mod.get("handler_name_arbitrary")
                or key.startswith("CommonModule.")
                or key.startswith("Configuration.")):
            return []
        # Экспортная процедура с именем события другого модуля — скорее
        # публичный метод объекта, а не попытка объявить обработчик.
        if method.is_export or not method.name:
            return []
        owners = sorted(self.global_index.get(method.name.casefold(), set()) - {key})
        if not owners:
            return []
        first = owners[0]
        other = self.find_event(first, method.name)
        suffix = ""
        if other:
            suffix = "; " + self.signatures_text(*other)
        labels = ", ".join(self.label(k) for k in owners[:3])
        if len(owners) > 3:
            labels += " и др."
        return [Finding(
            "event-handler-wrong-module", "warning", method.header_line,
            f"«{method.name}» — событие модуля {labels}, а не {self.label(key)}"
            f"{suffix}")]

    def _check_event(self, key: str, method, ru: str, event: dict) -> list[Finding]:
        findings: list[Finding] = []
        if method.is_export:
            findings.append(Finding(
                "event-handler-exported", "warning", method.header_line,
                f"{ru}: стандартный обработчик не должен быть экспортным; "
                f"{self.signatures_text(ru, event)}"))

        signatures = event.get("signatures") or []
        if not signatures:
            return findings
        declared = len(method.params)
        same = [sig for sig in signatures if self._fits(sig, declared)]
        if not same:
            names = ", ".join(method.params) or "—"
            findings.append(Finding(
                "event-handler-params", "error", method.header_line,
                f"{ru}: объявлено параметров: {declared} ({names}); "
                f"{self.signatures_text(ru, event)}"))
            return findings
        best = min(
            same,
            key=lambda sig: sum(1 for i, param in enumerate(method.params)
                                if not self._matches(param, sig, i)))
        mismatches = []
        for i, param in enumerate(method.params):
            if not self._matches(param, best, i):
                expected = " / ".join(self._param_names(best, i)) or "?"
                mismatches.append(f"параметр {i + 1} «{param}» вместо «{expected}»")
        if mismatches:
            findings.append(Finding(
                "event-handler-param-name", "info", method.header_line,
                f"{ru}: " + "; ".join(mismatches)
                + f"; {self.signatures_text(ru, event)}"))
        return findings


def context_line(key: str | None, obj: str | None, index: EventIndex) -> str:
    if not key:
        return ""
    mod = index.modules.get(key)
    label = index.label(key)
    obj_part = f"{obj} — " if obj else ""
    if mod is None:
        return f"# Контекст: {obj_part}{label} [{key}]: стандартных событий нет"
    if mod.get("handler_name_arbitrary"):
        return (f"# Контекст: {obj_part}{label} [{key}]: имена обработчиков "
                f"задаются в метаданных, проверка подписей не выполняется")
    return f"# Контекст: {obj_part}{label} [{key}], событий: {len(mod.get('events') or {})}"


def analyze_text(text: str, key: str, index: EventIndex) -> list[Finding]:
    model = bsl_model.Module(text)
    findings: list[Finding] = []
    for method in model.methods:
        if not method.name:
            continue
        findings.extend(index.check_method(key, method))
    findings.sort(key=lambda f: (f.line, f.code))
    return findings


def print_findings(findings: list[Finding], detailed: bool, context: str = "",
                   passed: bool = False):
    if detailed and context:
        print(context)
    for finding in findings:
        print(f"{finding.severity} | {finding.code} | строка {finding.line} | "
              f"{finding.message}")
    if detailed and passed and not findings:
        print("ok | event-handlers | — | нарушений нет")
    if not findings and not detailed:
        print("Нарушений не найдено.")


def iter_bsl(path: Path):
    for root, _dirs, files in os.walk(path):
        for name in sorted(files):
            if name.lower().endswith(".bsl"):
                yield Path(root) / name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("source", nargs="?",
                        help="путь к .bsl-файлу, каталогу или '-' для stdin")
    parser.add_argument("--module-type", dest="module_type",
                        help="вид модуля, если по пути не определяется, "
                             "например Document.ObjectModule")
    parser.add_argument("--object-name", dest="object_name",
                        help="имя объекта метаданных для сообщений")
    parser.add_argument("--list-module-types", action="store_true",
                        help="показать известные виды модулей и выйти")
    parser.add_argument("-Detailed", action="store_true",
                        help="показывать контекст и пройденные проверки")
    parser.add_argument("-NoFail", action="store_true",
                        help="не возвращать код ≠0 при error")
    args = parser.parse_args(argv)

    data = load_data()
    index = EventIndex(data)

    if args.list_module_types:
        for key in sorted(index.modules):
            mod = index.modules[key]
            count = len(mod.get("events") or {})
            suffix = " (имена обработчиков задаются в метаданных)" \
                if mod.get("handler_name_arbitrary") else ""
            print(f"{key}: событий {count}{suffix}")
        return 0

    if not args.source:
        parser.error("укажите файл, каталог или '-'")

    if args.module_type and args.module_type not in index.modules \
            and not args.module_type.startswith("CommonModule."):
        available = ", ".join(sorted(index.modules))
        parser.error(f"неизвестный вид модуля {args.module_type!r}. "
                     f"Доступны: {available}")

    has_error = False

    def report(findings, detailed, context, passed):
        nonlocal has_error
        print_findings(findings, detailed, context, passed)
        if any(f.severity == "error" for f in findings):
            has_error = True

    if args.source == "-":
        if not args.module_type:
            parser.error("для stdin обязателен --module-type")
        text = sys.stdin.read()
        findings = analyze_text(text, args.module_type, index)
        context = context_line(args.module_type, args.object_name, index)
        report(findings, args.Detailed, context, True)
        return 0 if args.NoFail or not has_error else 1

    source = Path(args.source)
    if source.is_dir():
        if args.module_type:
            parser.error("--module-type допустим только для одного файла/stdin")
        skipped = 0
        any_file = False
        for path in iter_bsl(source):
            key, obj, reason = infer_module_key(str(path))
            if key is None:
                skipped += 1
                if args.Detailed:
                    print(f"# {path}: пропущен — {reason}")
                    print("--- 8< ---")
                continue
            any_file = True
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            findings = analyze_text(text, key, index)
            print(f"# {path}")
            report(findings, args.Detailed, context_line(key, obj, index), True)
            print("--- 8< ---")
        if not any_file and not skipped:
            print("Не найдено .bsl-файлов.", file=sys.stderr)
        if skipped:
            print(f"Пропущено файлов: {skipped} (вид модуля не определён).",
                  file=sys.stderr)
        return 0 if args.NoFail or not has_error else 1

    if not source.is_file():
        print(f"Файл не найден: {source}", file=sys.stderr)
        return 2

    if args.module_type:
        key = args.module_type
        obj = args.object_name
        reason = ""
    else:
        key, obj, reason = infer_module_key(str(source))
        if args.object_name:
            obj = args.object_name
    if key is None:
        print(f"Не удалось определить вид модуля: {reason}. "
              f"Укажите --module-type (см. --list-module-types).",
              file=sys.stderr)
        return 2

    text = source.read_text(encoding="utf-8-sig", errors="replace")
    findings = analyze_text(text, key, index)
    report(findings, args.Detailed, context_line(key, obj, index), True)
    return 0 if args.NoFail or not has_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
