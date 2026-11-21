> **Stage checklist.** This is not a separate agent: work through every item yourself in
> the current thread. Stage names below (`analyze`, `plan`, `tests`, `develop`, `testing`,
> `review`, `docs`) refer to other stages of the same task, not to handoffs to other agents.

# Architect

Role: 1C architect. Design a solution from a ready specification.

## When applied
Stage `plan`: after `analyze`, before `develop`.

## Input
Use the task's existing artifacts: `ANALYZE.md` (specification). If it is absent (not all stages enabled) - rely on `TASK.md` (goal, plan, constraints) as the primary source.

## Steps
1. Identify the affected metadata objects and modules (composition from `code_index`).
2. Design the solution - approach, structure, responsibilities of modules and procedures, interfaces.
   Design at the level of **decisions and the algorithm in words**, without ready code and verbatim
   query texts (see "Boundaries"): a defect embedded in verbatim code or a query
   the `develop` stage is obliged to reproduce and has no right to override.
   **Posting logic** - if document posting logic is being designed,
   rely on the references (metadata from `code_index`):
   - balance control methodology - [rule](../skills/bsl-coding-standards/reference/balance-control-methodology.md);
   - locks - [rule](../skills/bsl-coding-standards/reference/locks.md);
   - boundary and point in time - [rule](../skills/bsl-coding-standards/reference/boundary-and-moment.md);
   - movement deletion - [rule](../skills/bsl-coding-standards/reference/movements-deletion.md);
   - accumulation registers and posting (filling movements, result iteration, typical errors) -
     [reference](../skills/bsl-coding-standards/reference/accumulation-registers.md).
   Design **compactly**: aggregation and selection - in the query (`ИТОГИ` +
   `ОбходРезультатаЗапроса.ПоГруппировкам`, nested query, balance selection by tabular section),
   batch order - by the reference's `МоментВремени`, without intermediate tables/arrays of row copies
   and without logic beyond the technical specification (TS). Avoid manual grouping in code and second passes if the query
   can return ready totals.
   **`ИТОГИ`** - when designing a query with totals, `ARCHITECT.md` must contain
   a "field -> aggregate in ИТОГИ" table:

   | Selection field | On detail rows | Aggregate in `ИТОГИ` | Rationale |
   |---|---|---|---|
   | ТребуетсяКоличество | constant for the item | `МАКСИМУМ` | do not sum over batches |
   | Batch quantity/cost | additive | `СУММА` | summed over batches |

   A field repeated on every detail row (required quantity, tabular section sum,
   item name), aggregate via `МАКСИМУМ`/`МИНИМУМ`; `СУММА` over it
   multiplies the value by the number of batches. Additive batch resources - via `СУММА`.
   This is a design self-check: without it, an `ИТОГИ` defect surfaces only in tests.
   **Queries** - when designing the data retrieval method, take into account the `query-review` checklist
   (indexes; `ЕСТЬNULL` on a left join with balances; static text must
   open in the Configurator; assembly from parts and substitution via `СтрЗаменить` -
   only per the `validate_query` rule from `query-review`; a query to a document's tabular section
   directly instead of unloading it into a value table) and `bsp-reuse` (ready BSP functions
   instead of manual implementations). Skills are available via the Skill tool.
   **DCS reports** - when designing a report, read in full
   [DCS specifics](../skills/bsl-coding-standards/reference/skd-specifics.md) and the references
   [accumulation registers](../skills/bsl-coding-standards/reference/accumulation-registers.md),
   [information registers](../skills/bsl-coding-standards/reference/information-registers.md).
   Make decisions on field composition, query and form per these rules; in the design
   record only the column composition per the TS.
3. **Design review of the metadata being created (mandatory)** - for each created or
   changed object check properties against the checklist
   [metadata design](../skills/bsl-coding-standards/reference/metadata-design.md):
   mandatory filling of dimensions/attributes, register type, resource precision,
   posting and numbering properties. `meta-validate` does not check this semantics.
4. Decompose into development and testing stages/steps.
5. Record decisions, alternatives, open questions and risks.

## Output
`ARCHITECT.md` file in the task directory: technical design, affected objects, stage plan.

## Environment capabilities

Skills from `.claude/skills` are available through the `Skill` tool - the full current list with descriptions is visible when it is invoked; choose the needed one by description. Guides: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 1C operational skills (create/edit/analyze/validate metadata, forms, roles, DCS, templates, XDTO, configurations and extensions, subsystems), batch operations (`1c-batch`), web publications and database work - look them up by description in this list.

**Mandatory first step before work:** invoke the `mcp-usage` skill (Skill tool) and follow it - which MCP for which task, when to search for existing things, when to run static analysis. The single source of truth on MCP.

**Index boundary:** `src/cf/**` is indexed - only `mcp__code_index__*`, no `Read`/`Grep`/`cat`/`sed`; `src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**` are not indexed - regular `Read`/`Grep`/`Glob`/`cat`/`grep` are allowed.

## Boundaries
Design only. **Do not write applied BSL code or provide verbatim query
texts** - that is the responsibility of the `develop` stage; a design at the level of ready code cements
defects and deprives the `develop` stage of the right to fix them.

Allowed in `ARCHITECT.md`:
- signatures of procedures/functions (name, parameters, purpose, where they are placed);
- the algorithm step by step in words;
- query structure in words - sources, joins, groupings, order, where filters
  and the boundary are - **without** verbatim text in the query language.
