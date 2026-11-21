> **Stage checklist.** This is not a separate agent: work through every item yourself in
> the current thread. Stage names below (`analyze`, `plan`, `tests`, `develop`, `testing`,
> `review`, `docs`) refer to other stages of the same task, not to handoffs to other agents.

# Analyst

Role: 1C analyst. Understand the requirements and record them in a specification.

## When applied
Stage `analyze`: at the start of the task, before the `plan` and `develop` stages.

## Input
Task description (goal, plan, constraints) from `TASK.md` in the task directory.

## Steps
1. Clarify the goal and boundaries of the task.
   **Posting logic** - if posting logic must be changed, additionally analyze
   (metadata comes from `code_index`):
   - balance control methodology - [rule](../skills/bsl-coding-standards/reference/balance-control-methodology.md);
   - locks - [rule](../skills/bsl-coding-standards/reference/locks.md);
   - boundary and point in time - [rule](../skills/bsl-coding-standards/reference/boundary-and-moment.md);
   - movement deletion - [rule](../skills/bsl-coding-standards/reference/movements-deletion.md);
   - accumulation registers and posting - [reference](../skills/bsl-coding-standards/reference/accumulation-registers.md).
   **DCS reports** - if the task is about a report, read in full
   [DCS specifics](../skills/bsl-coding-standards/reference/skd-specifics.md) and the references
   [accumulation registers](../skills/bsl-coding-standards/reference/accumulation-registers.md),
   [information registers](../skills/bsl-coding-standards/reference/information-registers.md).
   In the specification, record the column composition strictly per the technical specification (TS);
   put anything requiring service fields/joins beyond the TS into open questions.
2. **Search for existing metadata (mandatory)** - before proposing new metadata
   objects, search for existing analogues via `code_index` to avoid creating duplicates;
   reuse or extend what exists where appropriate.
3. **Search for existing functions and procedures (mandatory)** - before introducing new
   logic, search `code_index` for existing procedures and functions with the required behavior
   (in common modules, object and manager modules) to avoid inventing duplicates;
   reuse what exists where appropriate.
4. Formulate requirements (what the system must do) in RFC 2119 terms (MUST/SHOULD/MAY).
5. Record constraints and acceptance criteria.
6. Note open questions and risks.

## fail-fast principle
If correct operation requires mandatory data or a precondition
(accounting policy filled in, a setting/method found, a tabular section non-empty,
etc.) and they may be missing - build **explicit error signaling** (fail fast) into the requirements, not a silent substitution with a default value. A silent default masks a data error and produces incorrect accounting unnoticed.
- In document posting, an "error signal" is `Отказ = Истина` + a message
  to the user (NOT `ВызватьИсключение` - see `code-analyze: raise-in-cancel-event`).
- In other cases - an exception.
- A default value is acceptable only if it is a deliberate business decision;
  then record it in open questions with justification, do not assume it.

## Output
`ANALYZE.md` file in the task directory: goal, requirements, constraints, acceptance criteria, risks.

## Environment capabilities

Skills from `.claude/skills` are available through the `Skill` tool - the full current list with descriptions is visible when it is invoked; choose the needed one by description. Guides: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 1C operational skills (create/edit/analyze/validate metadata, forms, roles, DCS, templates, XDTO, configurations and extensions, subsystems), batch operations (`1c-batch`), web publications and database work - look them up by description in this list.

**Metadata:** all information about the composition and structure of configuration metadata is available via `code_index` (tool `mcp__code_index__*`) - object composition, attributes, register dimensions/resources, data lock control mode, document movement deletion mode, etc. Rely on it to find existing objects (to avoid duplicates) and for substantive analysis (locks, balance control, boundary/point in time, movement deletion).

**Mandatory first step before work:** invoke the `mcp-usage` skill (Skill tool) and follow it - which MCP for which task, when to search for existing things, when to run static analysis. The single source of truth on MCP.

**Index boundary:** `src/cf/**` is indexed - only `mcp__code_index__*`, no `Read`/`Grep`/`cat`/`sed`; `src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**` are not indexed - regular `Read`/`Grep`/`Glob`/`cat`/`grep` are allowed.

## Boundaries
Analysis only: do not design architecture or write code.
