---
name: verify-with-syntax-checker
description: After BSL edits, run static analysis.
---

# Verification with static analysis

After every change run **all mandatory layers**. A run without one of them is not a
completed check and blocks the handover to review:

- every changed `.bsl` - `bsl_ls` MCP check **and all** scripts of the
  `code-analyze` skill: `analyze_code.py` + `check_event_handlers.py`;
- every changed metadata XML (`meta-compile`/`meta-edit`) -
  `check_metadata_names.py --changed`;
- every changed query text - **all** steps of `query-analyze`:
  `extract_queries.py` + `analyze_query.py`, plus `validate_query` when available.

`check_metadata_names.py` checks only reserved metadata names and is not a substitute
for `analyze_code.py`/`check_event_handlers.py`.

## bsl_ls

Run static analysis via the `bsl_ls` MCP (tool `mcp__bsl_ls__check`, with `config`
from `.bsl-language-server.json`) and eliminate the found errors before moving to the
next step. Do not call the `bsl-language-server` binary directly. Do not consider the
task done until static analysis is clean.

Before the call compute the file's sha256 (`sha256sum <файл>` or
`shasum -a 256 <файл>`) and pass it to `check`. Without `sha256` the tool
will reject the call. Do not retype the module manually.

**BOM:** the server strips the leading UTF-8 BOM itself before analysis (BSL LS crashes on
it with `ParseError`). Both the `sha256` of the file with a BOM (`sha256sum`) and of the
normalized text without a BOM are accepted - stripping the BOM manually is not required.
