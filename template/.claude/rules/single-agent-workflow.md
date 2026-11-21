---
name: single-agent-workflow
description: Single-agent task execution according to task.json - stages as checklists, without subagents.
---

# Single-agent workflow

## Source
`tasks/task#<id>/task.json`: `stages` - list of stages. A stage with `enabled: true` is a
checklist; `subagent` - the file name in `.claude/checklists/`, `artifact` - the result file.
Order: `analyze → plan → tests → develop → testing → review → docs`.

## Stage-scoped process
If `TASK_STAGE` is set in the environment (each stage is started as a separate process),
perform **only this stage**. Read `TASK.md` and the required artifacts, work through
the stage checklist, write the artifact and update the status to `done`, then stop.
Do not start the next stages - the runner will start them in a new process with a clean
context.

The `tests` stage (writing tests) - no more than 30 minutes. `Information` diagnostics of
`bsl_ls` are not blocking; if the `validate_query` call fails (transport/server) consider the
query valid and do not loop.

## Stage
1. Read `.claude/checklists/<subagent>.md` as a **checklist**.
2. Work through the checklist's "Steps". Everything it says about the orchestrator or
   subagent, you perform yourself in this same thread.
3. Write the `artifact` to the task directory.
4. Update the status:
   `python .claude/tools/task_status.py tasks/task#<id> <этап> running`
   and after completion - `... <этап> done --files <файлы>`.

## Environment
- `.claude/**` - tools and checklists: read only, do not change.
- Run all Python commands with the project `.venv` interpreter (in the deployed environment
  `python` calls are already replaced with the absolute path); do not use system `python` or
  `pip install` - dependencies are already in the venv.
- Object creation: `meta-compile`; subsystem: `subsystem-compile`; role:
  `role-compile`. There are no `meta-add`/`subsystem-add` skills.
- The task is `TASK.md` and `src/cf/**`; artifacts go to the task directory.
- `src/cf/**` is indexed: for reading and search use `code_index`
  (load the tool via `ToolSearch` if it is not in the list); `Read` -
  only the required range (`offset`/`limit`). `src/cfe/**`, `tasks/**`, `logs/**`,
  `tmp/**`, `configs/**`, `docs/**` are not indexed - use ordinary
  `Read`/`Grep`/`Glob` there.

## Git
1. Before the first stage - a baseline commit: `git add -A && git commit -m "baseline before task#<id>"`.
2. Do not make commits during the task.
3. After successful completion of all enabled stages - one final commit.

## Infobase load (`update_db: true`)
After `develop` edits (before `done`):
1. `python .claude/tools/task_status.py tasks/task#<id> db-update start`
2. `mkdir -p "logs/task#<id>"`
3. `python .claude/tools/load-config-optimized.py --state "logs/task#<id>/load-state.json" > "logs/task#<id>/load-config.log" 2>&1`
4. If there is an error - read `logs/task#<id>/load-config.log` and `logs/load-config_*.log`,
   fix the sources and retry. `develop` stays `running` until the load succeeds.
5. `... task_status.py tasks/task#<id> db-update done`
6. `... task_status.py tasks/task#<id> develop done --files <файлы>`

## Long operations and 1C processes
Configuration load into the IB and a full test run are long operations. Start them
**synchronously** with ordinary Bash (without `run_in_background`) with all output
redirected to a log in `logs/task#<id>/` and an explicit `timeout` up to 600000 ms (for `run-tests.py` - up to
2 000 000 ms: it has three budgets of 600 s). In non-interactive `claude -p` the turn
ends on `end_turn`, and the harness kills the background process - the operation is lost.
While the command runs, no tokens are spent; after it returns read the log and the
return code. `Monitor` is only for waiting, not for launching.

- **Do not kill processes by a broad substring.** `pkill -f "1cv8 ENTERPRISE"` matches
  its own command line and kills its own shell. Linux/macOS: `pkill -f '[1]cv8'`
  or `pgrep -f '[1]cv8'` + targeted `kill <pid>`. Windows: `Get-Process`/
  `Stop-Process -Id` (PowerShell) or `taskkill /PID <pid>`; not `taskkill /IM 1cv8.exe`.
- Prefer `run-tests.py`/`1c-batch`: they kill only their own process tree
  on timeout.
- `sleep` is blocked by a hook. Wait via `Monitor`.

## Compact develop checklist (after compaction)
Do not reread `developer.md` in full; for the stage it is enough:
1. Input: `TASK.md`, `ANALYZE.md`, `ARCHITECT.md`, tests; existing code - via `code_index`.
2. Metadata - `meta-compile`/`subsystem-compile`/`role-compile`, edits - `meta-edit`; files - by real `src/cf/**` paths.
3. Accumulation registers: check the registrars (documents with `RegisterRecords`, the register's `<Registrars>`) before the infobase load.
4. Compilation checks: **mandatory** `check-modules --thin-client --server` (not in the background, `timeout: 600000` - 10 min); fix client-context errors in code or by clearing the «Клиент» flag on the common module.
5. Metadata names: `check_metadata_names.py --changed` - fix reserved system names before the infobase load.
6. Tests: skeleton -> one scenario at a time; `Write`/`Edit` <=150 lines; check after each; full `check-modules` once at the end.
7. Infobase load - per the section above; after success `db-update done`.
8. Checks after the load: `check` with sha256, `code-analyze`, `validate_query`
   on the static query text (one call); for new objects the check
   is postponed. `validate_query: valid` - the text is accepted; `valid: false` -
   a defect in the text, fix it and check again; absence of the `valid` field
   (transport/server) - one retry and record it in `DEVELOP.md`.
   `Information` diagnostics of `bsl_ls` are not blocking.
9. Test run: `.claude/tools/run-tests.py configs/task#<id>/test.json`;
   fix red scenarios in the application code; the goal is all scenarios green
   within the stage limit. The run result and `validate_query: valid` go to `DEVELOP.md`.
10. `DEVELOP.md`: changes, checks, waivers, postponed checks; then
    `develop done --files <файлы>`.
11. Do not read `Configuration.xml` and `ConfigDumpInfo.xml` in full - only the required range or `meta-info`/`cf-info`.

## Tests (`testing: true`)
Run `.claude/tools/run-tests.py` (see the `run-unit-tests` rule), log in
`logs/task#<id>/`. On failure determine the culprit from `result.json` and the registration
log: code or test. Record the verdict and the log in `TESTING.md`; code and tests are
left unchanged in this stage - fixes are done by the corresponding stage.
The stage ends with the `testing done` call; do not change the `develop` status in this stage.
Stage guideline - 10 minutes.

## Review (`review: true`)
Work through `.claude/checklists/reviewer.md` as a checklist over the diff and artifacts; findings go to
`REVIEW.md`. Critical and important findings block acceptance: fix and repeat.
In single-agent mode the reviewer is you; rely on the spec, automatic checks and quotes.

## Cycles
When returning for rework do not reread the whole task: take the current artifact,
verdict, log and the changed module. Fix in the same thread; new subagents are not needed.

## Boundaries
- Do not call Agent/Task/SendMessage. The `task-orchestration` skill no longer exists -
  this rule performs its role.
- For `src/cf/**` use `code_index`; `Read` - only the required range
  (`offset`/`limit`). A PreToolUse hook may redirect a native call to
  `code_index`; after the denial limit is exhausted the hook allows the native call
  so it does not loop.
