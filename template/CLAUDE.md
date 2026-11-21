# Single-agent mode

- The whole task runs in this thread. **Do not call Agent/Task/SendMessage.**
- The task is only `tasks/task#<id>/TASK.md`: changes in `src/cf/**` and the stage
  artifact. `.claude/**` - tools and checklists: read only, do not change.
- `task.json` - list of stages. For each `enabled` stage read
  `.claude/checklists/<subagent>.md` as a **checklist** and work through it.
- For each stage: complete the items, write the artifact (`DEVELOP.md` etc.),
  update status via `.claude/tools/task_status.py`.
- Do the infobase load and the tests yourself if they are enabled in `task.json`.
- There is no `task-orchestration` skill. Follow the `single-agent-workflow` rule.
- Run all Python commands with the project `.venv` interpreter; do not use system `python` or
  `pip install`: dependencies are already in the venv.
- Metadata creation: `meta-compile`; subsystem - `subsystem-compile`;
  role - `role-compile`. The `meta-add`/`subsystem-add` skills do not exist.
- Tool call first, text after. A plan without action is an error.
- Small steps: 1 file per `Write`, 2-3 tools per step; details go to files,
  no more than 10 lines in chat.
- On "Output token limit hit" continue from the same place without retelling.
