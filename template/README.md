# template/ - deployable environment template

This holds the content of the Claude agent environment that is deployed into the project's `.claude/`:

- `checklists/` - task stage checklists (analyst, architect, developer-tests, developer,
  reviewer, technical-writer). These are not subagents: the task runs in a single thread,
  the checklist is read and worked through by the executor. The `testing` stage has no
  separate checklist - the executor runs it per the `single-agent-workflow` rule.
- `skills/` - agent skills (each in its own subdirectory with its own `SKILL.md`)
- `rules/` - working rules; the main one is `single-agent-workflow.md` (stages, git,
  infobase load, tests, cycles)
- `hooks/` - hooks:
  - `bsl_nudge.py` - hints when editing BSL;
  - `route_to_checklists.py` - UserPromptSubmit hook: enables single-agent mode and
    lists the task's enabled stages as checklists (respecting `TASK_STAGE`);
  - `code_index_guard.py` - PreToolUse hook: redirects native
    Read/Grep/Glob/Bash/PowerShell on indexed directories to the `code_index` tools.
    The `code-index-guard.toml` config is generated during environment deployment;
    without it the hook is inert. `max_denies` (default 2) limits
    the number of consecutive denials for a single call - after they run out the native call
    is allowed so the local model does not loop. Rollback - delete the `PreToolUse` block
    from `.claude/settings.json`; an environment update will write it back,
    for a permanent disable remove the code-index MCP from the project.
- `tools/` - helper tools (for example, `task_status.py`)
- `CLAUDE.md` - brief single-agent mode protocol (deployed to the project root)
- `settings.local.json.example` - example local LLM profile (context limits,
  deny on Agent/Task, `claudeMdExcludes`). Copy it to `.claude/settings.local.json`
  and fill in the address/token/model; the file is not tracked by git.

Deployment is performed by the `content.deploy_content` function from the `agentmon.env` package.
All environment content edits are made here - in one obvious place.

## Migrating an old project (agents -> checklists)

Since version `1.1.0` the template uses single-agent mode: instead of
`.claude/agents/`, `.claude/checklists/` is deployed, and the
`task-orchestration` skill is removed. An environment update does not delete obsolete files,
so in an old project remove them manually once:

- `.claude/agents/` (or move your edits to `.claude/checklists/`);
- `.claude/skills/task-orchestration/`;
- `.claude/hooks/route_to_orchestrator.py`.

After that update the environment from AgentMon - `CLAUDE.md`,
`checklists/` and the new `route_to_checklists.py` hook will appear.
