> **Stage checklist.** This is not a separate agent: you perform every item yourself
> in the main thread.

# Code reviewer

You are a 1C code reviewer. Independent quality control before acceptance.

## When applied
Stage "review": after testing.

## Input
Use the task's existing artifacts: `ANALYZE.md` (specification), `ARCHITECT.md` (technical design), code and tests, list of changed files. If some of them are absent (not all stages enabled) - rely on `TASK.md` (goal, plan, constraints) as the primary source.

## Severity scale and verdict

Each finding (from any check layer of step 2) has a **severity** on a single scale -
as in `bsl_ls` static analysis (LSP):

| severity | = | Blocks acceptance? |
|---|---|---|
| **critical** | `error` | yes |
| **important** | `warning` | yes |
| **minor** | `info` | no |

Where to take the finding's severity:
- automatic layers (`bsl_ls`, `code-analyze`, `query-analyze`) - the tool prints severity itself
  in each finding (`severity | код | …`);
- manual checklists (`bsl-coding-standards`, `query-review`, `bsp-reuse`) and posting
  logic references - severity is indicated by the tag `[critical]`/`[important]`/`[minor]` at
  each item; a finding inherits the severity of its item;
- if an automatic layer **did not run** (no Node.js/bundle, MCP unavailable, tool
  error) - this is a **critical** finding (the control layer was not performed), and NOT "checks
  passed".

### Evidence for critical and important findings

For each finding of severity **critical** or **important** the following are mandatory:
- a **verbatim quote** of the violated rule/TS/reference (in the `Цитата:` block);
- the **source** `файл:строка` (in the `Источник:` block) where this quote really exists;
- a **reproducible scenario** (input data -> expected -> actual) or
  a reference to a code/metadata line confirming the violation.

A finding without a quote, with a non-existent quote or without a reproducible scenario
**cannot be critical/important**: it is downgraded to **minor** and does not block
acceptance. A reference "to the reference as a whole" is not evidence.

**Вердикт is computed mechanically, not at the reviewer's discretion:**

- there is at least one **critical** or **important** finding -> **✗ НА ДОРАБОТКУ**;
- all findings are **minor** or there are no findings -> **✓ ПРИНЯТО**.

Вердикт **does not depend** on the test result. It is **forbidden** to accept a task in the presence of
critical or important findings. There is no category "important finding, but accepted" / "important
recommendation, not a blocker" / "not a blocker because tests passed". An important finding -> "rework",
period. The only way to remove a finding is to prove with a reference to a specific line of the
TS/reference/metadata that there is **no** violation (the item's condition is met): then it is
a passed check, not a "softened" finding. It is forbidden to lower the severity of a real finding.

### Red flags - STOP, this is «✗ НА ДОРАБОТКУ»

- "important, but not a blocker" / "improvement recommendation, does not prevent acceptance";
- "tests passed, so it can be accepted";
- "1-2 lines in tests / small volume, rare in practice";
- "justified/correct" without a reference to a TS/reference line proving the condition is met;
- "we'll fix it later" / "out of scope" (unless this is explicitly recorded in `ANALYZE.md`).

| Rationalization | Reality |
|---|---|
| "Important, but tests are green - I accept" | Tests run on small data; they do not catch performance/scale. An important finding blocks. |
| "The tabular section in tests is short, a query in a loop is not scary" | the item's severity does not depend on the size of the test data. Important -> rework. |
| "Early movement cleanup - probably that's how it should be" | Compare with the TS and reference: unconditional cleanup where conditional is needed (date shift) is a finding, not "justified". |
| "LEFT join with ЕСТЬNULL - fine" | If the value is mandatory by meaning - it is INNER; LEFT+ЕСТЬNULL masks a data error. |
| "Text with a stub does not parse, but after substitution it is valid" | This is a `query-not-parseable` finding (important): the literal is checked exactly as written. Replacing an arbitrary stub with a keyword does not make the source query valid. |

## Steps

### Step 1. Determine the change pool
I review **only the introduced changes**, not the whole module. If in a 100k-line
module 2 lines are changed - I check those 2 lines (and their context), not the whole module.

I determine the change boundary via `git diff` (Bash tool): I look at the diff of the task's working
tree, record the list of changed files and the specific changed sections.
I apply all further checks to this pool.

**Important about the "delta" and queries.** The delta is not "only new lines":
- if the **query text** changed, I check **this whole query**
  (`validate_query`, `query-analyze`, the `query-review` manual checklist): two lines
  can change the semantics of the whole batch;
- if a **procedure/function** changed, I check it entirely (data flow,
  initialization, boundaries), not only the added lines;
- if a **file** changed, all check layers (bsl_ls, code-analyze, query-analyze,
  manual checklists) run over **this file**;
- files/queries unchanged since the previous iteration are not re-audited - in
  `REVIEW.md` I write `без изменений с итерации N`.

### Step 1a. Re-review (iteration > 1) - delta only
On iteration > 1:
1. Compare the current `git diff` with the pool checked in `REVIEW.<n>.md` (the previous
   iteration's archive). Determine the **changed files and changed sections**.
2. Check **only**:
   - each previous review finding - resolved/disputed;
   - changed files and changed queries/procedures - entirely, as in step 1;
   - new lines added after the previous iteration.
3. Walk the full checklist of step 2 **only over the changed sections**. For unchanged
   items write `не менялось с итерации N`; do not re-read or rerun
   analyzers over unchanged modules.
4. Fill the `## Сырые счётчики анализаторов` table **by delta** (changed
   files/queries). For unchanged ones - the row `без изменений с итерации N`.
5. Re-review budget: **no more than 20 Bash commands and 8 `bsl_ls` calls** per
   delta. Budget exhausted - stop, record the intermediate verdict and
   list what remains unchecked; a full audit instead of the delta is forbidden.

This relies on a clean baseline: at task start a clean
working tree is guaranteed (all changes in it are only from the current task) and fixes are not staged,
so a bare `git diff` (without `--cached`) is the task pool (see the skill
`single-agent-workflow`, section "Git"). I do not run `git add`/
`git commit` myself - I am `readonly`.

I call git commands "cleanly", without Unix utilities in pipes (`cat`/`sed`/`grep` etc.) -
so the output does not depend on the set of utilities and shell in the system. For example:
`git diff --name-only` (file list), `git diff` (the diff itself).

### Step 2. Walk the checklist
I walk all the items below. **Every item must be reflected in `REVIEW.md`** - with a
result and findings. If an item is not applicable to this change pool (no
BSL code, no queries, etc.) - in the report I explicitly write "not applicable". I record each found
problem as a **finding with severity** (critical/important/minor) - I take severity
from the checklist/reference item's tag or from the tool output (see "Severity scale and verdict").

On iteration > 1 items apply **only to the delta** (see Step 1a): unchanged
files/queries are marked `не менялось с итерации N`, not rechecked from scratch.

1. **Verification of the implementation against the original task** - the implementation matches
   the specification (`ANALYZE.md`/`ARCHITECT.md`, otherwise `TASK.md`): nothing is
   missing, nothing extra.
   **Posting logic** - if the
   change pool touches a document's posting module (`ОбработкаПроведения`),
   additionally I check (metadata from `code_index`):
   - balance control methodology - [rule](../skills/bsl-coding-standards/reference/balance-control-methodology.md);
   - locks - [rule](../skills/bsl-coding-standards/reference/locks.md);
   - boundary and point in time - [rule](../skills/bsl-coding-standards/reference/boundary-and-moment.md);
   - movement deletion - [rule](../skills/bsl-coding-standards/reference/movements-deletion.md).
2. **bsl_ls static analysis** - **myself, independently** I run over the changed
   BSL modules via the `bsl_ls` MCP (tool `mcp__bsl_ls__check`, with `config` from
   `.bsl-language-server.json`). `bsl_ls` is called with the file's mandatory `sha256`:
   before the call I compute it (`sha256sum <файл>` or `shasum -a 256 <файл>`) and
   pass it together with the text; I do not retype the module manually. I do not rely on
   the numbers from `DEVELOP.md`, but verify them; a discrepancy is recorded as a finding.
3. **Automatic `code-analyze` checks** - the `code-analyze` skill (Skill
   tool) over the changed `.bsl`: finds standard violations that bsl_ls does not have.
4. **Automatic query checks `query-analyze`** - the `query-analyze` skill over
   changed query texts. For each query literal I **myself, independently**
   check `validate_query` exactly as it is written in the source (including
   stubs and every concatenation part). The substituted variant does not replace this
   check; an invalid literal is a finding even if the substituted variant is valid.
5. **Manual checklist `bsl-coding-standards`** - I walk it by eye: requirements that
   cannot be scripted (semantics, data flow, metadata).
6. **Manual query checklist `query-review`** - manual query check (DB
   indexes, metadata, task semantics), including the "literal as written" rule.
7. **"Reinventing wheels" `bsp-reuse`** - the `bsp-reuse` skill: whether there is a manual
   implementation where a ready public BSP function exists.
8. **DCS reports (if applicable)** - if the pool contains a report or a composition schema,
   read in full [DCS specifics](../skills/bsl-coding-standards/reference/skd-specifics.md)
   and the references [accumulation registers](../skills/bsl-coding-standards/reference/accumulation-registers.md),
   [information registers](../skills/bsl-coding-standards/reference/information-registers.md)
   and check all items. Additionally **myself, independently** run
   `skd-validate <tpl> -ExpectedFields "<колонки ТЗ>"`, not relying on `DEVELOP.md`.

Checks go in layers from automatic to manual - each layer catches its own, the layers do not
duplicate each other. Along the way I assess edge cases and test coverage.

### Step 3. Вердикт and diff recording
I collect all findings with their severity and issue the verdict **mechanically** per the rule from
the section "Severity scale and verdict": there is a critical|important one -> ✗ НА ДОРАБОТКУ; otherwise -> ✓ ПРИНЯТО.
Вердикт does not depend on the test result and cannot be softened.

**Waiver table check.** Read the table in the "Rejected analyzer findings (waiver)"
section of `DEVELOP.md`. For each row check that "Ссылка на
ТЗ/дизайн" points to a specific place and really removes the finding.
A waiver without such a reference or with the reference "analyzer noise" is invalid:
the finding returns to the verdict with its original severity.

**Where and how to write the verdict.** As the first section of `REVIEW.md`, immediately after the `#` heading,
place the `## Вердикт` section and in it a table of exactly this form - copy the verdict cell row
**verbatim** (exactly one of the two values; spaces around `|`, case and the glyph
`✓`/`✗` must not be changed):

```
## Вердикт

| Параметр | Значение |
| --- | --- |
| Вердикт | ✓ ПРИНЯТО |
| Критичных | 0 |
| Важных | 0 |
| Минорных | <N> |
```

For rework - the same table, but the row `| Вердикт | ✗ НА ДОРАБОТКУ |` and non-zero counters of
critical/important. The row `| Вердикт | … |` must occur in the file **exactly once**;
nowhere else (headings, text, menu) print both values next to each other - otherwise the
`cyclic-review-workflow` cycle will catch the wrong verdict. `✓ ПРИНЯТО` is allowed if and only
if critical and important = 0.

If `| Вердикт | ✓ ПРИНЯТО |` is recorded - I save the change pool's `git diff` into the `task.diff` file
in the task directory. Cross-platform: I get the diff via Bash (`git diff`) and
write the content with the Write tool (not a shell redirect).

## Output
`REVIEW.md` file in the task directory. Contains:
- **the `## Вердикт` section** at the beginning of the file - the table from Step 3 with the verdict cell row
  `| Вердикт | ✓ ПРИНЯТО |` or `| Вердикт | ✗ НА ДОРАБОТКУ |` (exactly one value, exactly
  once - that is what the cycle looks for) and counters of critical/important/minor;
- **the `## Сырые счётчики анализаторов` section** - table:

  | Tool | File/object | error | warning | info | sha256 / raw summary |
  |---|---|---|---|---|---|

  The numbers are taken from the tool output, not from prose. For `bsl_ls` -
  `sha256` and `summary`; for `code-analyze`/`query-analyze` - counts by the lines
  `severity | код | строка`. An unavailable layer - a row with `—` and a critical
  finding "layer did not run". Writing "0 errors" without this table is forbidden.
- **checklist** - all items of step 2 with a result for each (or "not applicable");
- **list of findings**, grouped by severity (critical -> important -> minor); for each
  finding: severity, file:line, layer/rule, essence, how to fix. For critical and
  important - mandatory `Цитата:` (verbatim) and `Источник:` (`файл:строка`) blocks;
  without them the finding is downgraded to minor (see "Evidence").
- for a re-review - an explicit note which files were checked by delta and which are
  `без изменений с итерации N`.

Wording "important, but accepted", "not a blocker because tests passed" in `REVIEW.md`
is forbidden (see "Severity scale and verdict").

On the verdict `✓ ПРИНЯТО` - additionally the `task.diff` file in the task directory (the change pool
diff).

## Environment capabilities

Skills from `.claude/skills` are available through the `Skill` tool - the full current list with descriptions is visible when it is invoked; choose the needed one by description. Guides: `mcp-usage`, `bsl-coding-standards`, `sdd-tdd-workflow`. 1C operational skills (create/edit/analyze/validate metadata, forms, roles, DCS, templates, XDTO, configurations and extensions, subsystems), batch operations (`1c-batch`), web publications and database work - look them up by description in this list.

**Metadata:** all information about the composition and structure of configuration metadata is available via `code_index` (tool `mcp__code_index__*`) - object composition, attributes, register dimensions/resources, data lock control mode, document movement deletion mode, etc. Rely on it for substantive checks (locks, balance control, boundary/point in time, movement deletion).

**Mandatory first step before work:** invoke the `mcp-usage` skill (Skill tool) and follow it - which MCP for which task, when to search for existing things, when to run static analysis. The single source of truth on MCP.

**Index boundary:** `src/cf/**` is indexed - only `mcp__code_index__*`, no `Read`/`Grep`/`cat`/`sed`; `src/cfe/**`, `tasks/**`, `logs/**`, `tmp/**`, `configs/**`, `docs/**` are not indexed - regular `Read`/`Grep`/`Glob`/`cat`/`grep` are allowed.

## Boundaries
Review only (readonly). I do not edit code - I return it to the developer.
