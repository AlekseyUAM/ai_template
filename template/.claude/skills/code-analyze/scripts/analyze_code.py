# analyze_code.py — прогон реестра правил по BSL-модулю (.bsl).
import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import rules


def _analyze_text(text):
    ctx = rules.ModuleContext(text)
    findings = rules.run_all(ctx)
    findings.sort(key=lambda f: (f.line, f.code))
    return findings


def _print_findings(findings, detailed):
    for f in findings:
        print(f"{f.severity} | {f.code} | строка {f.line} | {f.message}")
    if detailed:
        hit = {f.code for f in findings}
        for r in rules.RULES:
            if r.code not in hit:
                print(f"ok | {r.code} | — | {r.title}")
    if not findings and not detailed:
        print("Нарушений не найдено.")


def _iter_bsl_files(path):
    for root, _dirs, files in os.walk(path):
        for name in sorted(files):
            if name.lower().endswith(".bsl"):
                yield os.path.join(root, name)


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("source", help="путь к .bsl-файлу, каталогу или '-' для stdin")
    parser.add_argument("-Detailed", action="store_true", help="показывать и пройденные правила")
    parser.add_argument("-NoFail", action="store_true", help="не возвращать код ≠0 при error")
    args = parser.parse_args(argv)

    has_error = False

    if args.source == "-":
        findings = _analyze_text(sys.stdin.read())
        _print_findings(findings, args.Detailed)
        has_error = any(f.severity == "error" for f in findings)
    elif os.path.isdir(args.source):
        any_file = False
        for fp in _iter_bsl_files(args.source):
            any_file = True
            with open(fp, encoding="utf-8") as fh:
                findings = _analyze_text(fh.read())
            print(f"# {fp}")
            _print_findings(findings, args.Detailed)
            print("--- 8< ---")
            if any(f.severity == "error" for f in findings):
                has_error = True
        if not any_file:
            print("Не найдено .bsl-файлов.", file=sys.stderr)
    else:
        with open(args.source, encoding="utf-8") as fh:
            findings = _analyze_text(fh.read())
        _print_findings(findings, args.Detailed)
        has_error = any(f.severity == "error" for f in findings)

    return 0 if args.NoFail else (1 if has_error else 0)


if __name__ == "__main__":
    raise SystemExit(main())
