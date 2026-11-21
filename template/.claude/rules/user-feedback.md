---
name: user-feedback
description: Take the user's feedback from USER_FEEDBACK.md into account before each task stage.
---

# User feedback

If the task directory `tasks/task#<id>/` contains the file `USER_FEEDBACK.md` - this is
user feedback left via Telegram. Before performing each
stage:

1. Read `USER_FEEDBACK.md` in full.
2. Address the open feedback in the current and subsequent stages (analysis,
   plan, tests, implementation, review) - it takes priority over guesses.
3. In the stage artifact briefly note which feedback was taken into account.

The file is maintained by the application (append-only). Do not delete or rewrite it yourself.
