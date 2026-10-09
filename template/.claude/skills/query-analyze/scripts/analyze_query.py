# analyze_query.py — прогон реестра правил по тексту запроса.
import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import rules

# Коды правил, работающих только по тексту (без AST-модели); все остальные требуют модель.
_TEXT_ONLY_CODES = frozenset({"keyword-lowercase", "query-one-line"})


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
    ctx = rules.QueryContext(text)
    findings = rules.run_all(ctx)
    findings.sort(key=lambda f: (f.line, f.code))

    # Принудительно обращаемся к модели, чтобы зафиксировать model_error
    # (run_all мог пропустить все AST-правила без обращения к ctx.model,
    # если модель ещё не была запрошена).
    _ = ctx.model
    if ctx.model_error:
        print(
            f"ВНИМАНИЕ: структурные (AST) проверки ПРОПУЩЕНЫ — {ctx.model_error}. "
            "Проверены только текстовые правила. "
            "Отсутствие находок НЕ означает, что запрос корректен.",
            file=sys.stderr,
        )

    for f in findings:
        print(f"{f.severity} | {f.code} | строка {f.line} | {f.message}")

    if args.Detailed:
        hit = {f.code for f in findings}
        for r in rules.RULES:
            if r.code not in hit:
                is_text_only = r.code in _TEXT_ONLY_CODES
                if ctx.model_error and not is_text_only:
                    print(f"skip | {r.code} | — | структурная проверка пропущена (AST недоступен)")
                else:
                    print(f"ok | {r.code} | — | {r.title}")

    if not findings:
        if ctx.model_error:
            print(
                "Нарушений по текстовым правилам не найдено "
                "(структурные проверки пропущены — см. предупреждение выше)."
            )
        else:
            print("Нарушений не найдено.")

    has_error = any(f.severity == "error" for f in findings)
    return 0 if args.NoFail else (1 if has_error else 0)


if __name__ == "__main__":
    raise SystemExit(main())
