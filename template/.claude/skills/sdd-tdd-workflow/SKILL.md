---
name: sdd-tdd-workflow
description: Development methodology through specification and tests (SDD+TDD). Read when planning task stages.
allowed-tools: []
---

# SDD + TDD

## Specification before code (SDD)
For new functionality and significant changes, first the spec (goal, requirements,
acceptance criteria), then the technical design, and only then the code.

## Tests before implementation (TDD)
1. **Red** - per the `developer-tests` checklist the executor writes unit tests with the tools accepted in the project, by the acceptance criteria; they fail (the "writing tests" stage).
2. **Green** - per the `developer` checklist the executor writes minimal code and brings the tests to passing.
3. **Check** - at the "testing" stage the executor runs the tests and gives the verdict (there is no separate tester checklist); on failure they return the task to development, where per the `developer` checklist they analyze the run log and fix the code.

## Test layers
- The choice of test runner is at the discretion of the project/task.
- Run static analysis (the `bsl_ls` MCP, the `mcp__bsl_ls__check` tool) at every step.

## Task cycle
analysis → plan → writing tests → development → testing → review → documentation.
