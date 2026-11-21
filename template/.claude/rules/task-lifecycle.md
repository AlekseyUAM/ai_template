---
name: task-lifecycle
description: Work on a task follows task.json with status and artifact updates.
---

# Task lifecycle

When working on a task from `tasks/task#<id>`:
1. Read `task.json` and respect `enabled` of each stage.
2. The stage executor (in single-agent mode - you yourself) writes the stage artifact (`ANALYZE.md`,
   `ARCHITECT.md`, `TESTS.md`, `DEVELOP.md`, `TESTING.md`, `REVIEW.md`, `DOCS.md`)
   to the task directory.
3. The stage status and the list of changed files are updated via
   `.claude/tools/task_status.py` (see the `single-agent-workflow` rule). `done` -
   only from `running`; for a repeated run - `restart`.

Do not create a separate git branch for the task - only one task is executed in the project
at a time, work goes in the project's current branch.
