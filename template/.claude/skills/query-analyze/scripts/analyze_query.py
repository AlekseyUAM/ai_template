# analyze_query.py - run the rule registry against query text.
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import rules

# Rule codes that work on text only (no AST model); all others require the model.
_TEXT_ONLY_CODES = frozenset({"keyword-lowercase", "query-one-line", "order-after-totals"})
_SEPARATOR = "--- 8< ---"


def split_extracted(text: str) -> list[tuple[str | None, str]]:
    """Split extract_queries.py output into blocks (header, query text).

    extract_queries.py prints `# <path>:<line>` before the query text and
    separates queries with the `--- 8< ---` line. Plain query text without headers
    is returned as a single block with header=None.
    """
    text = text.replace("\r\n", "\n")
    if not text.strip():
        return []
    first = text.lstrip("\n").splitlines()[0]
    is_extracted = (_SEPARATOR in text
                    or (first.startswith("# ") and ":" in first))
    if not is_extracted:
        return [(None, text.strip("\n"))]
    blocks: list[tuple[str | None, str]] = []
    for raw in text.split(_SEPARATOR):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        lines = raw.splitlines()
        header = None
        if lines and lines[0].startswith("# "):
            header = lines[0][2:].strip()
            raw = "\n".join(lines[1:])
        blocks.append((header, raw))
    return blocks


def analyze_text(text: str):
    """Analyze one query text; return (ctx, findings)."""
    ctx = rules.QueryContext(text)
    findings = rules.run_all(ctx)
    # Force access to the model to capture model_error
    # (run_all could skip all AST rules without touching ctx.model
    # if the model has not been requested yet).
    _ = ctx.model
    findings.sort(key=lambda f: (f.line, f.code))
    return ctx, findings


def _print_findings(findings) -> None:
    for f in findings:
        print(f"{f.severity} | {f.code} | строка {f.line} | {f.message}")


def _print_detailed(ctx, findings) -> None:
    hit = {f.code for f in findings}
    for r in rules.RULES:
        if r.code in hit:
            continue
        is_text_only = r.code in _TEXT_ONLY_CODES
        if ctx.model_error and not is_text_only:
            print(f"skip | {r.code} | — | структурная проверка пропущена (AST недоступен)")
        else:
            print(f"ok | {r.code} | — | {r.title}")


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("source", help="путь к файлу с текстом запроса или '-' для stdin")
    parser.add_argument("-Detailed", action="store_true")
    parser.add_argument("-NoFail", action="store_true", help="не возвращать код ≠0 при error")
    args = parser.parse_args(argv)

    if args.source == "-":
        text = sys.stdin.read()
    else:
        with open(args.source, encoding="utf-8") as fh:
            text = fh.read()

    blocks = split_extracted(text)
    if not blocks:
        print("Нарушений не найдено.")
        return 0

    analyzed = []
    for header, query in blocks:
        ctx, findings = analyze_text(query)
        analyzed.append((header, ctx, findings))

    # Infrastructure layer skip (no node/bundle, launch failure) - warn.
    # A syntax parse error (ctx.parse_error) is not a skip but the
    # query-not-parseable finding - do not duplicate it with a warning.
    seen_errors = []
    for _header, ctx, _findings in analyzed:
        if ctx.model_error and not ctx.parse_error and ctx.model_error not in seen_errors:
            seen_errors.append(ctx.model_error)
    for model_error in seen_errors:
        print(
            f"ВНИМАНИЕ: структурные (AST) проверки ПРОПУЩЕНЫ — {model_error}. "
            "Проверены только текстовые правила. "
            "Отсутствие находок НЕ означает, что запрос корректен.",
            file=sys.stderr,
        )

    has_error = False
    for header, ctx, findings in analyzed:
        if header:
            print(f"# {header}")
        _print_findings(findings)
        if args.Detailed:
            _print_detailed(ctx, findings)
        if not findings:
            if ctx.model_error:
                print(
                    "Нарушений по текстовым правилам не найдено "
                    "(структурные проверки пропущены — см. предупреждение выше)."
                )
            else:
                print("Нарушений не найдено.")
        has_error = has_error or any(f.severity == "error" for f in findings)

    return 0 if args.NoFail else (1 if has_error else 0)


if __name__ == "__main__":
    raise SystemExit(main())
