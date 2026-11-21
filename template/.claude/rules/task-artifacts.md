---
name: task-artifacts
description: The stage executor leaves the result in the task directory.
---

# Task artifacts

When a stage completes, its executor:
1. Writes the result to the stage file in the task directory
   (`ANALYZE.md`, `ARCHITECT.md`, `TESTS.md`, `DEVELOP.md`, `TESTING.md`, `REVIEW.md`, `DOCS.md`).
   Stage artifacts are written by the executor (in single-agent mode - you yourself); `TESTING.md` - also
   you, the `testing` stage has no separate executor.
2. Specifies the status and the list of changed files.

This ensures context transfer between stages and transparency of the task progress.
