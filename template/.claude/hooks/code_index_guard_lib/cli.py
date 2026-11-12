"""CLI-контракт хука. Решения подключаются в Task 8."""
import json
import sys

from .config import indexed_paths, load_guard_config
from .context import GuardContext
from . import tools


def build_context() -> GuardContext:
    from .paths import default_case_insensitive
    ci = default_case_insensitive()
    cfg = load_guard_config()
    return GuardContext(cfg, indexed_paths(cfg, case_insensitive=ci), ci)


def parse_args(argv):
    list_roots = False
    prefix = None
    i = 0
    while i < len(argv):
        if argv[i] == "--list-roots":
            list_roots = True
        elif argv[i] == "--mcp-prefix" and i + 1 < len(argv):
            i += 1
            prefix = argv[i]
        i += 1
    return list_roots, prefix


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    list_roots, prefix = parse_args(args)
    try:
        ctx = build_context()
        tools.set_prefix(prefix or ctx.config.mcp_prefix)
        if list_roots:
            return  # режим v1 не реализован: пустой stdout
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return
        # dispatch появится в Task 8; сейчас хук ничего не решает
    except Exception:
        return
