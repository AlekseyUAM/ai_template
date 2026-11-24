---
name: mcp-usage
description: When to use each connected 1C MCP server. Read before accessing metadata, static analysis, platform reference, complex questions or code search.
allowed-tools: []
---

# Using 1C MCP servers

The servers are listed below, each covers its own class of tasks. The general principle: **do not read raw XML/code by hand and do not guess** - ask the server that holds the needed fact in its index or reference.

> **Single-agent.** MCP tools are not always in the prompt of the main thread - load the needed one via `ToolSearch` (e.g., `code_index read_file`, `bsl_ls check`). If a tool is not loaded, do not repeat the call with a nonexistent name - find it via ToolSearch.

| Need | Server | Start |
|-------|--------|-------|
| Find where and how something is implemented in the configuration | `code_index` | `search_terms` |
| Structure/composition/links of a metadata object | `code_index` | `get_object_profile` / `get_object_structure` |
| Platform API reference (types, methods, properties, constructors) | `1c_platform` | `search` → `info` |
<!-- @if 1c-md -->
| Metadata of the current infobase (objects, structure, data) | `1c-md` | `list_metadata_objects` / `execute_query` |
| Validate query syntax against infobase metadata | `1c-md` | `validate_query` |
<!-- @endif -->
<!-- @if 1c_naparnic -->
| BSL compilation error or unclear method signature | `1c_naparnic` | `ask_1c_ai` |
<!-- @endif -->
| Static analysis of BSL (errors, standards) | `bsl_ls` | `check` |

**Golden rules:**
1. Before writing new code/an object - search for the existing one via `code_index` (`search_terms`, `get_object_structure`). Duplication is a reason to stop.
2. After BSL edits - run `bsl_ls check` (with the mandatory file `sha256`) and fix the findings until clean.
3. Do not guess platform syntax - `1c_platform`.
4. `code_index` requires the `repo` parameter (repository alias) in almost every tool. The repository alias of this project is **`{{CODE_INDEX_REPO}}`**, pass it: `repo="{{CODE_INDEX_REPO}}"`. If in the `get_stats` response or in an error text you see a LIST of aliases - there are several repositories, take the needed one from the list.
5. **Index boundary.** Only `src/cf/**` is indexed. For files inside it, `Read`, `Grep`, `Glob`, `cat`, `sed`, `grep` are forbidden - use `mcp__code_index__*`; get metadata object structure (attributes, tabular sections, dimensions, resources, forms, movements) via `get_object_structure`/`get_object_profile`, `meta-info`/`meta-decompile` or `cf-info`, not by grepping XML. If a raw fragment is needed - `code_index.read_file`. **Exception:** if `code_index` reports that a file/object is not in the index (created in this task) or the index is stale, read that exact path with native `Read`/`meta-info`. The guard allows it; do not build Python workarounds. Everything else (`src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**`) is **not indexed** - read with ordinary `Read`/`Grep`/`Glob`/`cat`/`grep`.
<!-- @if 1c_naparnic -->
6. For **any** BSL compilation error or unclear method signature - immediately
   `ask_1c_ai`, in parallel with `bsl_ls check` and `1c_platform`; do not guess
   from memory.
<!-- @endif -->
7. One `get_object_structure`/`get_object_profile`/`list_files` per object per
   task - reuse the result; repeat only if the object changed after a return to
   `develop`.

**Exact tool names** (an error in the name means the call will not go through):
- `mcp__1c-md__*` - **hyphen**, not `1c_md` (`mcp__1c_md__...` does not exist);
- `mcp__1c_platform__getMember`, `mcp__1c_platform__getMembers` (camelCase, not `get_member`);
- `mcp__code_index__*`; code-index has **no** `get_member` / `get_members`;
<!-- @if 1c_naparnic -->
- `mcp__1c_naparnic__*` - **underscore**, not `1c-naparnic`; the main
  tool is `ask_1c_ai`.
<!-- @endif -->
- there is no `Memory` tool - take skills and knowledge from files in `.claude/`.

---

## `code_index` - codebase search and navigation

An index of BSL + metadata + call/data graphs. The richest server; it gets a detailed breakdown.

### 0. Mandatory preamble
- The project repository alias is `{{CODE_INDEX_REPO}}`: **pass `repo="{{CODE_INDEX_REPO}}"`** in all tools where it is required. Usually there is one repository - no need to call `get_stats` for the alias. If you see a list of aliases in the response, there are several repositories - choose the needed one from the list.
- `get_stats` (no parameters) - index statistics / list of connected repos. Useful for controlling index size, not as a mandatory preamble.
- `health` - liveness of the server and the indexing daemon, if results seem empty/outdated.
- **Index freshness.** With a working file watcher the index updates in seconds
  (debounce 1.5 s + batch 2 s). On Windows bind mounts watcher events may be
  missing: if `health`/`stat_file` disagree or a new object is not found, treat
  the index as stale and use the native fallback in golden rule 5 (native `Read`/`meta-info`
  for that exact path). In the benchmark, the native deployment updates the
  index within seconds; if in doubt, use the native fallback.
- **First exploration call** for `src/cf` is
  `list_files(repo="...", path_prefix="...")`; `ls`/`find`/`grep` are denied
  by the code-index guard.

### 1. Searching "where is feature X implemented" (main entry)
- **`search_terms`** - the FIRST choice for BSL. Searches procedures by *meaning*, not exact spelling: procedure name (CamelCase is split: `УточнитьДанныеПоШтрихкоду` → `уточнить данные по штрихкоду`), name+synonym of the owner object, comment above the procedure. Query 1-3 word roots: `штрихкод`, `резерв склад`, `расчет цен`. Word forms/substrings from 3 characters, case and ё/е do not matter. Returns `proc_key = '<путь>::<имя>'` - get the body later via `get_function`.
- **`search_function`** / **`search_class`** - fuzzy FTS by words (bm25), output without bodies (locations/signatures). For functions of any language; on BSL it often loses to `search_terms`.
- **`search_text`** - FTS over text files (md/txt/yaml/toml).

### 2. Exact name known → navigation and bodies
- **`find_symbol`** (exact name) - WHERE the symbol is defined, without bodies. For common names (standard handlers) always set `path_glob`, otherwise hundreds of locations.
- **`get_function`** / **`get_class`** - the BODY by exact name (with source). Support mass mode via `names: [...]`. A non-unique name → bodies are omitted, locations are returned + a hint to narrow `path_glob`.
- **`get_file_summary`** - a file table of contents without bodies (signatures, line ranges, imports). Safe on large modules.
- **`read_file`** (`repo`+`path`, optional `line_start`/`line_end`) - file content from the index (both text and code via zstd). `path` is relative to the repository root (`src/cf`), e.g. `Documents/Анкета.xml` or `CommonModules/Х/Ext/Module.bsl`; do not repeat the metadata type (`Documents/Анкета/Documents/Анкета.xml` is wrong). `stat_file` - file metadata (size, lines, language). `list_files` (`pattern`/`path_prefix`/`language`) - file list.
- **Sign of a stale `read_file`.** If `lines_total` disagrees with `stat_file`,
  the content does not contain the expected fragment or looks like a previous version - this is
  a stale `serve` cache. Compare lines, not bytes: `file_size` may be counted in
  bytes, while content size is in characters (Cyrillic in BSL). Do not conclude "the module
  is empty": take `get_file_summary`/`get_function`
  (structured index data) and retry `read_file` in a few seconds.
  If the discrepancy persists for more than a minute - report an environment error (the `serve`
  cache is not invalidated).

### 3. Regex search over code
- **`grep_code`** - regex over the WHOLE text of code files (module-level + bodies: `Перем` declarations, routing tables, literals, comments). A superset of `grep_body`. `path_glob` OR `language` is desirable (full-scan is expensive).
- **`grep_body`** - only function/class bodies, but shows in WHICH function it was found. Take it when "which procedure" matters.
- **`grep_text`** - regex over text files.
- Pattern parameter: `regex` (synonym `query`); `grep_body` also has `pattern` (LIKE substring). `context_lines` - surrounding lines.

### 4. Object metadata (structure/forms/modules/links)
- **`get_object_profile`** - the FULL object profile in ONE call: `structure` + `forms` (with handlers) + `modules` (with UUIDs) + `data_links`. Singular name: `Document.РеализацияТоваровУслуг`. `sections=['structure']` - narrow and cheapen. Replaces the series of three calls below.
- **`get_object_structure`** - structure only: attributes/tabular sections/dimensions/resources, `enum_values`, `predefined`, `owners`, `properties` (periodicity, posting), `commands`. `name_like` + `meta_type` - structures of ALL topic objects in one call. Mass mode (`[mcp].mass_mode_tools` in `daemon.toml`) is enabled by the generated `daemon.toml`; with it `get_object_structure` accepts `full_names: [...]` - structures of several objects in one call. If the server returned `-32602` for `full_names`, mass mode is off (the server is not in the whitelist) - call one object at a time. Batch only when the whole set is certainly needed (the result of one object will not cancel the need for the others); when selecting candidates - one at a time, stopping along the way. **This is the only source of structure: object XML is NOT indexed as text - do not search it via `grep_text`/`list_files`.**
- **`get_form_handlers`** (`owner_full_name` + `form_name`) - event→form handler pairs.

### 5. Link graphs (impact analysis, "what will break")
- **`find_references`** - the object's "impact map" in one call: `data_refs` (structural refs) + `code_usages` (references in .bsl) + `role_rights` (which roles grant rights). The main tool before modifying an object.
- **`get_data_links`** (`direction` out/in/both, `depth` ≤4) - ref links by attributes/dimensions.
- **`find_data_path`** (`from`→`to`) - whether there is a path via refs between objects.
- **`get_register_writers`** - register recorders / document movements (from the declarative composition, more accurate than analyzing posting code). Works both ways.
- **`get_event_subscriptions`** (filters `event`/`source`/`handler_module`) - event subscriptions; `event` accepts Russian/English.

### 6. BSL call graphs
- **`get_callers`** / **`get_callees`** (`function_name`) - who calls / what it calls.
- **`get_call_tree`** (`root`, `direction` callees/callers, `max_depth`≤10) - call tree.
- **`find_path_bsl`** (`from`→`to`, keys `<rel_path>::<name>`) - a path in the BSL graph with `call_type`. Universal analogue - `find_path`.

### 7. Long tail - `bsl_sql`
Arbitrary **read-only** SQL (SELECT/WITH) over index tables when there is no named tool: filters, joins, aggregations. There is NO need to filter the `repo` column (in each DB it is `'default'`). Key tables: `metadata_objects`, `metadata_modules`, `metadata_forms`, `event_subscriptions`, `proc_call_graph`, `data_links`, `role_rights`, `metadata_code_usages`. Writes/PRAGMA are rejected.

`functions` has no `path` column: join `files` (`functions.file_id = files.id`) and filter `files.path`. On a column error the response contains `query_tables_columns` and `did_you_mean` - use them instead of guessing.

---

## `1c_platform` - platform API reference

For syntax, signatures and available type members. **Do not guess - ask here.**

- **`search`** (`query`, `type` method/property/type/null, `limit`) - API search by specific 1C terms. The entry point when the exact name is unknown.
- **`info`** (`name`, `type` method/property/type) - a detailed card of the item by exact name.
- **`getMembers`** (`typeName`) - the FULL list of methods and properties of a type (`СправочникСсылка`, `Запрос`, `ТаблицаЗначений`).
- **`getMember`** (`typeName`, `memberName`) - one method/property of a type.
- **`getConstructors`** (`typeName`) - ways to create an object of the type.

Route: you do not know the name → `search`; you know the type and need the whole API → `getMembers`; you know the item → `info`/`getMember`; you create an object → `getConstructors`.
<!-- @if 1c-md -->

## `1c-md` - metadata and platform query validation

A 1C extension with the `mcp_APIBackend` HTTP service on the infobase web publication. Unlike
`code_index`, it works not with XML sources but with the **current infobase
metadata**.

- **`list_metadata_objects`** (`metaType` - required, e.g. `Catalogs`, `Documents`,
  `InformationRegisters`; `nameMask` - substring in name or synonym; `maxItems` -
  100 by default) - metadata objects with full names and synonyms. This tool does
  **not** exist in `code_index`: `mcp__code_index__list_metadata_objects` will fail.
  There the object list is `get_object_structure(name_like=...)` or `bsl_sql`.
- **`get_metadata_structure`** (`metaType`, `name` without the type prefix) -
  attributes, tabular sections, register dimensions/resources with their types.
  Use it before building a query.
- **`execute_query`** (`queryText`, `parameters`, `limit` up to 1000) - executes a
  SELECT and returns data; reference fields come as `{_objectRef,
  УникальныйИдентификатор, ТипОбъекта, Представление}` and can be passed to the next
  query. The call may be disabled by the access policy (benchmark deny-list) - then
  use `code_index.bsl_sql`.
- **`validate_query`** (`queryText` - query text) - syntax validation
  by the platform (`СхемаЗапроса.УстановитьТекстЗапроса`), without execution and without
  accessing data. Returns `valid` and `message`. This is the most accurate layer of
  syntax and name validation: the platform itself validates against the current infobase composition.
- **`parse_nav_link`** (`navLink`) and **`get_nav_link`** (`objectDescription`) -
  convert an `e1cib/data/...` navigation link to an object description and back.

**Text format:** `queryText` is the concatenated query text **without leading
`|`** and without outer quotes; the tool is not a 1C literal parser. A literal
with `|` prefixes will fail with a syntax error.

**Important: `validate_query` knows only metadata loaded into the DB.** If in the
course of development metadata was changed in XML sources and not yet loaded into the
infobase, the tool does not know about them: a query with new attributes,
tabular sections or objects gets a "not found" error, although it is correct in the
sources. Then:

1. verify the new names against the XML sources (the `meta-info`, `code_index` skills);
2. do not rewrite a correct query for an outdated DB;
3. after loading changes into the infobase, retry `validate_query` - the error goes away.

`validate_query` does not replace `query-analyze`: it does not check query style and
optimization standards.
<!-- @endif -->

<!-- @if 1c_naparnic -->

---

## `1c_naparnic` - 1C questions (external AI assistant)

An MCP wrapper over 1C:Напарник. The server is shared and talks to the external
`code.1c.ai` service (internet is required); the token is configured on the server side.

- **`ask_1c_ai`** - a 1C question: compilation errors, unclear method
  signatures, platform and BSP behavior.
- **`explain_1c_syntax`** - explanation of a language construct.

**Policy:** on any compilation or signature error call
`ask_1c_ai` **immediately**, in parallel with `bsl_ls check` and `1c_platform`; do not
guess from memory. If the answer disagrees with local tools, decide in favor of the
verifiable source: the platform version - from `1c_platform`, code - from
`code_index`.

**Confidentiality:** the request and code fragments go to the external 1C service -
do not send secrets, passwords and personal data without necessity. An authorization
error means a wrong/expired token on the Напарник server.

`check_1c_code` is not used - use `bsl_ls` for code validation.

<!-- @endif -->

---

## `bsl_ls` - BSL static analysis

- **`check`** (`sha256` is **mandatory**; exactly one source: `code` - module text or `file_path`; optional `config`, `filename`). Returns errors/warnings by standards and raw `counts` (`Error`/`Warning`/`Information`/`Hint`).
- **`sha256` is mandatory.** Compute it for the file (`sha256sum Module.bsl` or `shasum -a 256 Module.bsl`) and pass it together with `code`. Without `sha256` the call is rejected, and on a hash mismatch java is not started. **Do not retype the module manually** - pass the exact file text. `file_path` works only if the server sees the path (in the standard Docker deployment the project is not mounted - use `code`+`sha256`).
- **BOM:** the server strips the leading UTF-8 BOM before analysis (otherwise BSL LS gives `ParseError`). It accepts the `sha256` of either a file with BOM (`sha256sum`) or text without BOM; the response has `bom_removed: true` and `raw_sha256`.
- **Before the call, read `.bsl-language-server.json` in the project root and pass it in `config`** (as a JSON string or an object) so that checks follow the project rules. If the file is absent - do not pass `config` (default rules apply).
- Run after every BSL change and bring to clean before the next step.

---

## Recipes for frequent tasks

- **"Where is X implemented?"** → `search_terms "X"` (with `repo="{{CODE_INDEX_REPO}}"`) → `get_function(proc_key)`.
- **"Study an object before rework"** → `get_object_profile('Document.X')`; for a list of topic objects → `get_object_structure(name_like='…')`.
- **"What breaks if I change the object?"** → `find_references('Catalog.X')` (+ `get_register_writers` for documents/registers).
- **"Who calls this procedure?"** → `get_callers` / `get_call_tree(direction=callers)`.
- **"Am I reinventing the wheel?"** (search-before-write) → `search_terms` + `get_object_structure(name_like=…)` (or `bsl_sql` over `metadata_objects`).
- **"How do I call the platform method correctly?"** → `1c_platform search` → `info`/`getMembers`.
<!-- @if 1c-md -->
- **"Validate query syntax"** → `1c-md validate_query` (against infobase metadata; if metadata is not loaded yet - errors about new names are expected), then `query-analyze` for style rules.
<!-- @endif -->
<!-- @if 1c_naparnic -->
- **"Compilation or signature error"** → `bsl_ls check` + immediately `ask_1c_ai`;
  for validating the code itself - `bsl_ls`, for explanation - `ask_1c_ai`.
<!-- @endif -->
- **"Validate written code"** → `bsl_ls check` (file `sha256` + `code`, with `config` from the project), then `code-analyze` and `query-analyze` over changed modules/queries.
